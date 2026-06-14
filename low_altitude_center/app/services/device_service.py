from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Device, MaintenanceRecord, FlightEvent, Task, FlightPosition
from ..schemas.schemas import (
    DeviceCreate,
    DeviceUpdate,
    MaintenanceRecordCreate,
    UtilizationStat,
    TaskFlightSummary,
    DailyFlightSummary,
    DailyTaskBreakdown,
)


async def create_device(db: AsyncSession, data: DeviceCreate) -> Device:
    device = Device(**data.model_dump(), status="offline")
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def get_device(db: AsyncSession, device_id: int) -> Optional[Device]:
    result = await db.execute(select(Device).where(Device.id == device_id))
    return result.scalars().first()


async def list_devices(
    db: AsyncSession,
    device_type: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = select(Device)
    count_query = select(func.count()).select_from(Device)

    if device_type is not None:
        query = query.where(Device.device_type == device_type)
        count_query = count_query.where(Device.device_type == device_type)
    if status is not None:
        query = query.where(Device.status == status)
        count_query = count_query.where(Device.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(Device.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_device(
    db: AsyncSession, device_id: int, data: DeviceUpdate
) -> Optional[Device]:
    device = await get_device(db, device_id)
    if device is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)
    await db.commit()
    await db.refresh(device)
    return device


async def add_maintenance_record(
    db: AsyncSession, device_id: int, data: MaintenanceRecordCreate
) -> MaintenanceRecord:
    record = MaintenanceRecord(device_id=device_id, **data.model_dump())
    db.add(record)

    device = await get_device(db, device_id)
    device.last_maintenance = record.performed_at
    if data.next_maintenance_date is not None:
        device.next_maintenance = data.next_maintenance_date

    await db.commit()
    await db.refresh(record)
    return record


async def get_maintenance_records(
    db: AsyncSession, device_id: int
) -> list[MaintenanceRecord]:
    result = await db.execute(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.device_id == device_id)
        .order_by(MaintenanceRecord.performed_at.desc())
    )
    return list(result.scalars().all())


async def _compute_flight_stats(
    db: AsyncSession, device_id: int, start: datetime, end: datetime
) -> tuple[int, float]:
    start_naive = start.replace(tzinfo=None) if start.tzinfo else start
    end_naive = end.replace(tzinfo=None) if end.tzinfo else end

    takeoff_count_result = await db.execute(
        select(func.count()).select_from(FlightEvent).where(
            and_(
                FlightEvent.device_id == device_id,
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start_naive,
                FlightEvent.timestamp < end_naive,
            )
        )
    )
    flight_count = takeoff_count_result.scalar_one()

    takeoffs_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.device_id == device_id,
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start_naive,
                FlightEvent.timestamp < end_naive,
            )
        )
        .order_by(FlightEvent.timestamp.asc())
    )
    takeoffs = list(takeoffs_result.scalars().all())

    landings_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.device_id == device_id,
                FlightEvent.event_type.in_(["landing", "return_home"]),
                FlightEvent.timestamp >= start_naive,
                FlightEvent.timestamp < end_naive,
            )
        )
        .order_by(FlightEvent.timestamp.asc())
    )
    landings = list(landings_result.scalars().all())

    total_hours = 0.0
    pairs = min(len(takeoffs), len(landings))
    for i in range(pairs):
        duration = (landings[i].timestamp - takeoffs[i].timestamp).total_seconds()
        if duration > 0:
            total_hours += duration / 3600.0

    return flight_count, round(total_hours, 4)


async def get_utilization_stats(
    db: AsyncSession,
    device_id: int = None,
    start_date: datetime = None,
    end_date: datetime = None,
) -> list[UtilizationStat]:
    now = datetime.now(timezone.utc)
    if start_date is None:
        start_date = now - timedelta(days=30)
    if end_date is None:
        end_date = now

    hours_in_period = (end_date - start_date).total_seconds() / 3600

    query = select(Device)
    if device_id is not None:
        query = query.where(Device.id == device_id)

    result = await db.execute(query)
    devices = list(result.scalars().all())

    stats = []
    for device in devices:
        flight_count, total_flight_hours = await _compute_flight_stats(
            db, device.id, start_date, end_date
        )

        if hours_in_period > 0:
            utilization_rate = round(total_flight_hours / hours_in_period * 100, 2)
        else:
            utilization_rate = 0.0

        stats.append(
            UtilizationStat(
                device_id=device.id,
                device_name=device.name,
                total_flight_hours=total_flight_hours,
                total_flight_count=flight_count,
                utilization_rate=utilization_rate,
                period_start=start_date,
                period_end=end_date,
            )
        )

    return stats


async def get_task_flight_summaries(
    db: AsyncSession,
    device_id: int = None,
    task_id: int = None,
) -> list[TaskFlightSummary]:
    query = (
        select(
            FlightEvent.task_id,
            FlightEvent.device_id,
            Task.name.label("task_name"),
            Device.name.label("device_name"),
            func.count(FlightEvent.id).label("event_count"),
            func.min(FlightEvent.timestamp).label("first_ts"),
            func.max(FlightEvent.timestamp).label("last_ts"),
        )
        .join(Task, FlightEvent.task_id == Task.id, isouter=True)
        .join(Device, FlightEvent.device_id == Device.id)
        .where(FlightEvent.event_type == "takeoff")
        .group_by(FlightEvent.task_id, FlightEvent.device_id)
    )

    if device_id is not None:
        query = query.where(FlightEvent.device_id == device_id)
    if task_id is not None:
        query = query.where(FlightEvent.task_id == task_id)

    result = await db.execute(query)
    rows = result.all()

    summaries = []
    for row in rows:
        tid = row.task_id
        did = row.device_id
        flight_count = row.event_count

        takeoffs_q = await db.execute(
            select(FlightEvent)
            .where(
                and_(
                    FlightEvent.device_id == did,
                    FlightEvent.task_id == tid,
                    FlightEvent.event_type == "takeoff",
                )
            )
            .order_by(FlightEvent.timestamp.asc())
        )
        takeoffs = list(takeoffs_q.scalars().all())

        landings_q = await db.execute(
            select(FlightEvent)
            .where(
                and_(
                    FlightEvent.device_id == did,
                    FlightEvent.task_id == tid,
                    FlightEvent.event_type.in_(["landing", "return_home"]),
                )
            )
            .order_by(FlightEvent.timestamp.asc())
        )
        landings = list(landings_q.scalars().all())

        total_hours = 0.0
        pairs = min(len(takeoffs), len(landings))
        for i in range(pairs):
            dur = (landings[i].timestamp - takeoffs[i].timestamp).total_seconds()
            if dur > 0:
                total_hours += dur / 3600.0

        pos_q = await db.execute(
            select(
                func.count(FlightPosition.id).label("pos_count"),
                func.min(FlightPosition.latitude).label("min_lat"),
                func.max(FlightPosition.latitude).label("max_lat"),
                func.min(FlightPosition.longitude).label("min_lon"),
                func.max(FlightPosition.longitude).label("max_lon"),
            ).where(
                and_(
                    FlightPosition.device_id == did,
                    FlightPosition.task_id == tid,
                )
            )
        )
        pos_data = pos_q.first()
        pos_count = pos_data.pos_count if pos_data else 0

        first_flight = None
        last_flight = None
        if takeoffs:
            first_flight = takeoffs[0].timestamp
        if landings:
            last_flight = landings[-1].timestamp
        elif takeoffs:
            last_flight = takeoffs[-1].timestamp

        summaries.append(
            TaskFlightSummary(
                task_id=tid or 0,
                task_name=row.task_name or "",
                device_id=did,
                device_name=row.device_name,
                flight_count=flight_count,
                total_flight_hours=round(total_hours, 4),
                first_flight_time=first_flight,
                last_flight_time=last_flight,
                position_count=pos_count,
                min_latitude=pos_data.min_lat if pos_data and pos_data.min_lat else None,
                max_latitude=pos_data.max_lat if pos_data and pos_data.max_lat else None,
                min_longitude=pos_data.min_lon if pos_data and pos_data.min_lon else None,
                max_longitude=pos_data.max_lon if pos_data and pos_data.max_lon else None,
            )
        )

    return summaries


async def get_daily_flight_summaries(
    db: AsyncSession,
    device_id: int = None,
    start_date: datetime = None,
    end_date: datetime = None,
) -> list[DailyFlightSummary]:
    now = datetime.now(timezone.utc)
    if start_date is None:
        start_date = now - timedelta(days=7)
    if end_date is None:
        end_date = now

    start_naive = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
    end_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date

    device_query = select(Device)
    if device_id is not None:
        device_query = device_query.where(Device.id == device_id)
    device_result = await db.execute(device_query)
    devices = list(device_result.scalars().all())

    summaries = []
    for device in devices:
        daily_data = {}

        takeoffs_q = await db.execute(
            select(FlightEvent)
            .where(
                and_(
                    FlightEvent.device_id == device.id,
                    FlightEvent.event_type == "takeoff",
                    FlightEvent.timestamp >= start_naive,
                    FlightEvent.timestamp < end_naive,
                )
            )
            .order_by(FlightEvent.timestamp.asc())
        )
        takeoffs = list(takeoffs_q.scalars().all())

        landings_q = await db.execute(
            select(FlightEvent)
            .where(
                and_(
                    FlightEvent.device_id == device.id,
                    FlightEvent.event_type.in_(["landing", "return_home"]),
                    FlightEvent.timestamp >= start_naive,
                    FlightEvent.timestamp < end_naive,
                )
            )
            .order_by(FlightEvent.timestamp.asc())
        )
        landings = list(landings_q.scalars().all())

        pairs = min(len(takeoffs), len(landings))
        for i in range(pairs):
            tk = takeoffs[i]
            ld = landings[i]
            day_key = tk.timestamp.strftime("%Y-%m-%d")
            dur_hours = (ld.timestamp - tk.timestamp).total_seconds() / 3600.0
            if dur_hours < 0:
                dur_hours = 0
            if day_key not in daily_data:
                daily_data[day_key] = {
                    "flight_count": 0,
                    "total_hours": 0.0,
                    "tasks": {},
                }
            daily_data[day_key]["flight_count"] += 1
            daily_data[day_key]["total_hours"] += dur_hours

            task_id = tk.task_id or 0
            task_key = str(task_id)
            if task_key not in daily_data[day_key]["tasks"]:
                daily_data[day_key]["tasks"][task_key] = {
                    "task_id": task_id,
                    "task_name": "",
                    "flight_count": 0,
                    "total_hours": 0.0,
                }
            daily_data[day_key]["tasks"][task_key]["flight_count"] += 1
            daily_data[day_key]["tasks"][task_key]["total_hours"] += dur_hours

        pos_q = await db.execute(
            select(
                func.date(FlightPosition.timestamp).label("day"),
                func.min(FlightPosition.latitude).label("min_lat"),
                func.max(FlightPosition.latitude).label("max_lat"),
                func.min(FlightPosition.longitude).label("min_lon"),
                func.max(FlightPosition.longitude).label("max_lon"),
            )
            .where(
                and_(
                    FlightPosition.device_id == device.id,
                    FlightPosition.timestamp >= start_naive,
                    FlightPosition.timestamp < end_naive,
                )
            )
            .group_by(func.date(FlightPosition.timestamp))
        )
        pos_bounds = {row.day: row for row in pos_q.all()}

        task_name_cache = {}

        for day_key in sorted(daily_data.keys()):
            day_data = daily_data[day_key]
            bounds = pos_bounds.get(day_key)

            task_breakdown = []
            for task_key, task_info in day_data["tasks"].items():
                task_id = task_info["task_id"]
                task_name = ""
                if task_id and task_id not in task_name_cache:
                    t_result = await db.execute(
                        select(Task).where(Task.id == task_id)
                    )
                    task_obj = t_result.scalars().first()
                    task_name_cache[task_id] = task_obj.name if task_obj else ""
                if task_id:
                    task_name = task_name_cache.get(task_id, "")

                task_breakdown.append(
                    DailyTaskBreakdown(
                        task_id=task_id or 0,
                        task_name=task_name,
                        flight_count=task_info["flight_count"],
                        total_flight_hours=round(task_info["total_hours"], 4),
                    )
                )

            summaries.append(
                DailyFlightSummary(
                    date=day_key,
                    device_id=device.id,
                    device_name=device.name,
                    flight_count=day_data["flight_count"],
                    total_flight_hours=round(day_data["total_hours"], 4),
                    min_latitude=bounds.min_lat if bounds and bounds.min_lat else None,
                    max_latitude=bounds.max_lat if bounds and bounds.max_lat else None,
                    min_longitude=bounds.min_lon if bounds and bounds.min_lon else None,
                    max_longitude=bounds.max_lon if bounds and bounds.max_lon else None,
                    task_breakdown=task_breakdown,
                )
            )

    return summaries
