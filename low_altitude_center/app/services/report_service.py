import json
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
    query = query.offset(offset).limit(page_size)
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
    query = query.offset(offset).limit(page_size)
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
        takeoff_query = select(func.count()).select_from(FlightEvent).where(
            and_(
                FlightEvent.device_id == device.id,
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
            )
        )
        takeoff_count_result = await db.execute(takeoff_query)
        flight_count = takeoff_count_result.scalar_one()

        landing_query = (
            select(FlightEvent)
            .where(
                and_(
                    FlightEvent.device_id == device.id,
                    FlightEvent.event_type == "landing",
                    FlightEvent.timestamp >= start,
                    FlightEvent.timestamp < end,
                )
            )
            .order_by(FlightEvent.timestamp.asc())
        )
        landing_result = await db.execute(landing_query)
        landings = list(landing_result.scalars().all())

        takeoff_events_query = (
            select(FlightEvent)
            .where(
                and_(
                    FlightEvent.device_id == device.id,
                    FlightEvent.event_type == "takeoff",
                    FlightEvent.timestamp >= start,
                    FlightEvent.timestamp < end,
                )
            )
            .order_by(FlightEvent.timestamp.asc())
        )
        takeoff_events_result = await db.execute(takeoff_events_query)
        takeoffs = list(takeoff_events_result.scalars().all())

        total_hours = 0.0
        pairs = min(len(takeoffs), len(landings))
        for i in range(pairs):
            duration = (landings[i].timestamp - takeoffs[i].timestamp).total_seconds()
            if duration > 0:
                total_hours += duration / 3600.0

        summaries.append(
            {
                "device_id": device.id,
                "name": device.name,
                "flight_count": flight_count,
                "flight_hours": round(total_hours, 2),
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

    start = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(day=start.day + 1)

    takeoff_count_result = await db.execute(
        select(func.count()).select_from(FlightEvent).where(
            and_(
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
            )
        )
    )
    total_flights = takeoff_count_result.scalar_one()

    takeoffs_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
            )
        )
        .order_by(FlightEvent.timestamp.asc())
    )
    takeoffs = list(takeoffs_result.scalars().all())

    landings_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.event_type == "landing",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
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

    alerts_count_result = await db.execute(
        select(func.count()).select_from(Alert).where(
            and_(
                Alert.created_at >= start,
                Alert.created_at < end,
            )
        )
    )
    alerts_count = alerts_count_result.scalar_one()

    anomaly_count_result = await db.execute(
        select(func.count()).select_from(AnomalyPoint).where(
            and_(
                AnomalyPoint.created_at >= start,
                AnomalyPoint.created_at < end,
            )
        )
    )
    anomaly_count = anomaly_count_result.scalar_one()

    device_summaries = await _build_device_summaries(db, start, end, device_id)

    return {
        "date": start.isoformat(),
        "total_flights": total_flights,
        "total_flight_hours": round(total_flight_hours, 2),
        "alerts_count": alerts_count,
        "anomaly_count": anomaly_count,
        "device_summaries": device_summaries,
    }


async def generate_monthly_report(
    db: AsyncSession,
    year: int,
    month: int,
    device_id: int = None,
) -> dict:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    takeoff_count_result = await db.execute(
        select(func.count()).select_from(FlightEvent).where(
            and_(
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
            )
        )
    )
    total_flights = takeoff_count_result.scalar_one()

    takeoffs_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.event_type == "takeoff",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
            )
        )
        .order_by(FlightEvent.timestamp.asc())
    )
    takeoffs = list(takeoffs_result.scalars().all())

    landings_result = await db.execute(
        select(FlightEvent)
        .where(
            and_(
                FlightEvent.event_type == "landing",
                FlightEvent.timestamp >= start,
                FlightEvent.timestamp < end,
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

    alerts_count_result = await db.execute(
        select(func.count()).select_from(Alert).where(
            and_(
                Alert.created_at >= start,
                Alert.created_at < end,
            )
        )
    )
    alerts_count = alerts_count_result.scalar_one()

    anomaly_count_result = await db.execute(
        select(func.count()).select_from(AnomalyPoint).where(
            and_(
                AnomalyPoint.created_at >= start,
                AnomalyPoint.created_at < end,
            )
        )
    )
    anomaly_count = anomaly_count_result.scalar_one()

    device_summaries = await _build_device_summaries(db, start, end, device_id)

    return {
        "year": year,
        "month": month,
        "total_flights": total_flights,
        "total_flight_hours": round(total_flight_hours, 2),
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
