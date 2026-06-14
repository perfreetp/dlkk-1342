import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import FlightPosition, FlightEvent, Device, Task
from ..schemas.schemas import (
    FlightPositionCreate,
    FlightPositionOut,
    FlightEventCreate,
    FlightEventOut,
    TrajectoryPoint,
)


async def report_position(db: AsyncSession, data: FlightPositionCreate) -> FlightPosition:
    position = FlightPosition(**data.model_dump())
    db.add(position)

    result = await db.execute(select(Device).where(Device.id == data.device_id))
    device = result.scalars().first()
    if device is not None:
        device.current_latitude = data.latitude
        device.current_longitude = data.longitude
        device.current_altitude = data.altitude
        if data.battery_percent is not None:
            device.current_battery = data.battery_percent

    await db.commit()
    await db.refresh(position)
    return position


async def get_trajectory(
    db: AsyncSession,
    device_id: int,
    start_time: datetime = None,
    end_time: datetime = None,
) -> list[TrajectoryPoint]:
    query = (
        select(FlightPosition)
        .where(FlightPosition.device_id == device_id)
        .order_by(FlightPosition.timestamp.asc())
    )
    if start_time is not None:
        query = query.where(FlightPosition.timestamp >= start_time)
    if end_time is not None:
        query = query.where(FlightPosition.timestamp <= end_time)

    result = await db.execute(query)
    positions = result.scalars().all()

    return [
        TrajectoryPoint(
            latitude=p.latitude,
            longitude=p.longitude,
            altitude=p.altitude,
            speed=p.speed,
            battery_percent=p.battery_percent,
            timestamp=p.timestamp,
        )
        for p in positions
    ]


async def record_event(db: AsyncSession, data: FlightEventCreate) -> FlightEvent:
    event = FlightEvent(
        task_id=data.task_id,
        device_id=data.device_id,
        event_type=data.event_type,
        latitude=data.latitude,
        longitude=data.longitude,
        altitude=data.altitude,
        details_json=json.dumps(data.details),
    )
    db.add(event)

    now = datetime.now(timezone.utc)
    if data.event_type == "takeoff" and data.task_id is not None:
        result = await db.execute(select(Task).where(Task.id == data.task_id))
        task = result.scalars().first()
        if task is not None:
            task.actual_start = now
    elif data.event_type in ("landing", "return_home") and data.task_id is not None:
        result = await db.execute(select(Task).where(Task.id == data.task_id))
        task = result.scalars().first()
        if task is not None:
            task.actual_end = now

    await db.commit()
    await db.refresh(event)
    return event


async def get_flight_events(
    db: AsyncSession,
    task_id: int = None,
    device_id: int = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list, int]:
    query = select(FlightEvent)
    count_query = select(func.count()).select_from(FlightEvent)

    if task_id is not None:
        query = query.where(FlightEvent.task_id == task_id)
        count_query = count_query.where(FlightEvent.task_id == task_id)
    if device_id is not None:
        query = query.where(FlightEvent.device_id == device_id)
        count_query = count_query.where(FlightEvent.device_id == device_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(FlightEvent.timestamp.desc())
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total
