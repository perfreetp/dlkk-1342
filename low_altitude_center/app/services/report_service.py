import json
from calendar import monthrange
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import MediaFile, AnomalyPoint, FlightEvent, Alert, Device
from ..schemas.schemas import (
    MediaFileCreate,
    MediaFileOut,
    AnomalyPointCreate,
    AnomalyPointOut,
    ReportQuery,
    UtilizationStat,
)
from . import device_service


def _strip_tz(dt):
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


async def upload_media(db: AsyncSession, data: MediaFileCreate) -> MediaFile:
    media = MediaFile(**data.model_dump())
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return media


async def list_media(
    db: AsyncSession,
    task_id: int = None,
    file_type: str = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = select(MediaFile)
    count_query = select(func.count()).select_from(MediaFile)

    if task_id is not None:
        query = query.where(MediaFile.task_id == task_id)
        count_query = count_query.where(MediaFile.task_id == task_id)
    if file_type is not None:
        query = query.where(MediaFile.file_type == file_type)
        count_query = count_query.where(MediaFile.file_type == file_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(MediaFile.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def create_anomaly(db: AsyncSession, data: AnomalyPointCreate) -> AnomalyPoint:
    dump = data.model_dump()
    dump["media_file_ids_json"] = json.dumps(dump.pop("media_file_ids", []))
    anomaly = AnomalyPoint(**dump)
    db.add(anomaly)
    await db.commit()
    await db.refresh(anomaly)
    return anomaly


async def list_anomalies(
    db: AsyncSession,
    task_id: int = None,
    severity: str = None,
    is_resolved: int = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = select(AnomalyPoint)
    count_query = select(func.count()).select_from(AnomalyPoint)

    if task_id is not None:
        query = query.where(AnomalyPoint.task_id == task_id)
        count_query = count_query.where(AnomalyPoint.task_id == task_id)
    if severity is not None:
        query = query.where(AnomalyPoint.severity == severity)
        count_query = count_query.where(AnomalyPoint.severity == severity)
    if is_resolved is not None:
        query = query.where(AnomalyPoint.is_resolved == is_resolved)
        count_query = count_query.where(AnomalyPoint.is_resolved == is_resolved)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(AnomalyPoint.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def resolve_anomaly(
    db: AsyncSession, anomaly_id: int
) -> Optional[AnomalyPoint]:
    result = await db.execute(
        select(AnomalyPoint).where(AnomalyPoint.id == anomaly_id)
    )
    anomaly = result.scalars().first()
    if anomaly is None:
        return None
    anomaly.is_resolved = 1
    await db.commit()
    await db.refresh(anomaly)
    return anomaly


async def _compute_period_flight_stats(
    db: AsyncSession, start: datetime, end: datetime, device_id: int = None
) -> tuple[int, float]:
    start_naive = start.replace(tzinfo=None) if start.tzinfo else start
    end_naive = end.replace(tzinfo=None) if end.tzinfo else end
    device_filter = (
        FlightEvent.device_id == device_id if device_id is not None else True
    )

    takeoff_count_result = await db.execute(
        select(func.count()).select_from(FlightEvent).where(
            and_(
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start_naive,
                FlightEvent.timestamp < end_naive,
                device_filter,
            )
        )
    )
    total_flights = takeoff_count_result.scalar_one()

    takeoffs_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start_naive,
                FlightEvent.timestamp < end_naive,
                device_filter,
            )
        )
        .order_by(FlightEvent.timestamp.asc())
    )
    takeoffs = list(takeoffs_result.scalars().all())

    landings_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.event_type.in_(["landing", "return_home"]),
                FlightEvent.timestamp >= start_naive,
                FlightEvent.timestamp < end_naive,
                device_filter,
            )
        )
        .order_by(FlightEvent.timestamp.asc())
    )
    landings = list(landings_result.scalars().all())

    total_flight_hours = 0.0
    pairs = min(len(takeoffs), len(landings))
    for i in range(pairs):
        duration = (landings[i].timestamp - takeoffs[i].timestamp).total_seconds()
        if duration > 0:
            total_flight_hours += duration / 3600.0

    return total_flights, round(total_flight_hours, 4)


async def _build_device_summaries(
    db: AsyncSession, start: datetime, end: datetime, device_id: int = None
) -> list[dict]:
    device_query = select(Device)
    if device_id is not None:
        device_query = device_query.where(Device.id == device_id)
    device_result = await db.execute(device_query)
    devices = list(device_result.scalars().all())

    summaries = []
    for device in devices:
        flight_count, flight_hours = await device_service._compute_flight_stats(
            db, device.id, start, end
        )
        summaries.append(
            {
                "device_id": device.id,
                "name": device.name,
                "flight_count": flight_count,
                "flight_hours": flight_hours,
            }
        )

    return summaries


async def generate_daily_report(
    db: AsyncSession,
    report_date: datetime = None,
    device_id: int = None,
) -> dict:
    if report_date is None:
        report_date = datetime.now(timezone.utc)

    start = report_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    _, days_in_month = monthrange(start.year, start.month)
    if start.day < days_in_month:
        end = start.replace(day=start.day + 1)
    else:
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1)
        else:
            end = start.replace(month=start.month + 1, day=1)

    total_flights, total_flight_hours = await _compute_period_flight_stats(
        db, start, end, device_id
    )

    alerts_count_result = await db.execute(
        select(func.count()).select_from(Alert).where(
            and_(
                Alert.created_at >= _strip_tz(start),
                Alert.created_at < _strip_tz(end),
            )
        )
    )
    alerts_count = alerts_count_result.scalar_one()

    anomaly_count_result = await db.execute(
        select(func.count()).select_from(AnomalyPoint).where(
            and_(
                AnomalyPoint.created_at >= _strip_tz(start),
                AnomalyPoint.created_at < _strip_tz(end),
            )
        )
    )
    anomaly_count = anomaly_count_result.scalar_one()

    device_summaries = await _build_device_summaries(db, start, end, device_id)

    return {
        "date": start.isoformat(),
        "total_flights": total_flights,
        "total_flight_hours": total_flight_hours,
        "alerts_count": alerts_count,
        "anomaly_count": anomaly_count,
        "device_summaries": device_summaries,
    }


async def generate_monthly_report(
    db: AsyncSession,
    year: int = None,
    month: int = None,
    device_id: int = None,
) -> dict:
    now = datetime.now(timezone.utc)
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    if month < 1 or month > 12:
        return {
            "year": year,
            "month": month,
            "total_flights": 0,
            "total_flight_hours": 0.0,
            "alerts_count": 0,
            "anomaly_count": 0,
            "device_summaries": [],
            "error": "Invalid month, must be 1-12",
        }

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    total_flights, total_flight_hours = await _compute_period_flight_stats(
        db, start, end, device_id
    )

    alerts_count_result = await db.execute(
        select(func.count()).select_from(Alert).where(
            and_(
                Alert.created_at >= _strip_tz(start),
                Alert.created_at < _strip_tz(end),
            )
        )
    )
    alerts_count = alerts_count_result.scalar_one()

    anomaly_count_result = await db.execute(
        select(func.count()).select_from(AnomalyPoint).where(
            and_(
                AnomalyPoint.created_at >= _strip_tz(start),
                AnomalyPoint.created_at < _strip_tz(end),
            )
        )
    )
    anomaly_count = anomaly_count_result.scalar_one()

    device_summaries = await _build_device_summaries(db, start, end, device_id)

    return {
        "year": year,
        "month": month,
        "total_flights": total_flights,
        "total_flight_hours": total_flight_hours,
        "alerts_count": alerts_count,
        "anomaly_count": anomaly_count,
        "device_summaries": device_summaries,
    }


async def get_utilization_stats(
    db: AsyncSession,
    device_id: int = None,
    start_date: datetime = None,
    end_date: datetime = None,
) -> list[UtilizationStat]:
    return await device_service.get_utilization_stats(
        db, device_id=device_id, start_date=start_date, end_date=end_date
    )
