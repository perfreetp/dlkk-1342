import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import FlightPosition, FlightEvent, Device, Task, Alert, Route
from ..schemas.schemas import (
    FlightPositionCreate,
    FlightPositionOut,
    FlightEventCreate,
    FlightEventOut,
    TrajectoryPoint,
)
from ..core.events import publish_event
from ..services.task_service import _transition_status


LOW_BATTERY_THRESHOLD = 20.0


async def _check_and_create_alerts(db: AsyncSession, device: Device, data: FlightPositionCreate):
    alerts_created = []

    if data.battery_percent is not None and data.battery_percent < LOW_BATTERY_THRESHOLD:
        alert = Alert(
            device_id=device.id,
            task_id=data.task_id,
            alert_type="low_battery",
            severity="warning" if data.battery_percent >= 10 else "critical",
            message=f"Device {device.name} battery at {data.battery_percent:.1f}%",
            latitude=data.latitude,
            longitude=data.longitude,
            details_json=json.dumps({"battery_percent": data.battery_percent}),
        )
        db.add(alert)
        alerts_created.append(alert)

    if data.task_id is not None:
        task_result = await db.execute(select(Task).where(Task.id == data.task_id))
        task = task_result.scalars().first()
        if task is not None and task.route_id is not None:
            route_result = await db.execute(select(Route).where(Route.id == task.route_id))
            route = route_result.scalars().first()
            if route is not None:
                in_violation = False
                reasons = []

                if route.max_altitude is not None and data.altitude > route.max_altitude:
                    in_violation = True
                    reasons.append(f"Altitude {data.altitude:.1f}m exceeds route max {route.max_altitude:.1f}m")

                if route.area_polygon_json:
                    try:
                        polygon = json.loads(route.area_polygon_json)
                        if polygon and not _point_in_polygon(data.latitude, data.longitude, polygon):
                            in_violation = True
                            reasons.append("Position outside route area polygon")
                    except (json.JSONDecodeError, TypeError):
                        pass

                if in_violation:
                    alert = Alert(
                        device_id=device.id,
                        task_id=data.task_id,
                        alert_type="boundary_violation",
                        severity="critical",
                        message=f"Device {device.name} boundary violation: {'; '.join(reasons)}",
                        latitude=data.latitude,
                        longitude=data.longitude,
                        details_json=json.dumps({"reasons": reasons}),
                    )
                    db.add(alert)
                    alerts_created.append(alert)

    await db.flush()

    for alert in alerts_created:
        await db.refresh(alert)
        await publish_event(
            event_type=f"alert.{alert.alert_type}",
            payload={
                "id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "device_id": alert.device_id,
                "task_id": alert.task_id,
            },
        )


def _point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    n = len(polygon)
    if n < 3:
        return True
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


async def report_position(db: AsyncSession, data: FlightPositionCreate) -> FlightPosition:
    device_result = await db.execute(select(Device).where(Device.id == data.device_id))
    device = device_result.scalars().first()
    if device is None:
        raise ValueError(f"Device with id {data.device_id} not found")
    if device.status in ("disabled", "maintenance"):
        raise ValueError(
            f"Device '{device.name}' (id={data.device_id}) is currently '{device.status}' "
            "and cannot report flight data"
        )

    task = None
    if data.task_id is not None:
        task_result = await db.execute(select(Task).where(Task.id == data.task_id))
        task = task_result.scalars().first()
        if task is None:
            raise ValueError(f"Task with id {data.task_id} not found")

    position = FlightPosition(**data.model_dump())
    db.add(position)

    device.current_latitude = data.latitude
    device.current_longitude = data.longitude
    device.current_altitude = data.altitude
    if data.battery_percent is not None:
        device.current_battery = data.battery_percent

    await _check_and_create_alerts(db, device, data)

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
    device_result = await db.execute(select(Device).where(Device.id == data.device_id))
    device = device_result.scalars().first()
    if device is None:
        raise ValueError(f"Device with id {data.device_id} not found")
    if device.status in ("disabled", "maintenance"):
        raise ValueError(
            f"Device '{device.name}' (id={data.device_id}) is currently '{device.status}' "
            "and cannot report flight events"
        )

    task = None
    if data.task_id is not None:
        task_result = await db.execute(select(Task).where(Task.id == data.task_id))
        task = task_result.scalars().first()
        if task is None:
            raise ValueError(f"Task with id {data.task_id} not found")

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
    if data.event_type == "takeoff" and task is not None:
        task.actual_start = now
        if task.status in ("draft", "planned", "approved"):
            try:
                if task.status == "draft":
                    await _transition_status(db, task, "planned")
                if task.status == "planned":
                    await _transition_status(db, task, "approved")
                if task.status == "approved":
                    await _transition_status(db, task, "in_progress")
            except ValueError:
                pass
    elif data.event_type in ("landing", "return_home") and task is not None:
        task.actual_end = now
        if task.status == "in_progress":
            try:
                await _transition_status(db, task, "completed")
            except ValueError:
                pass

    await db.commit()
    await db.refresh(event)

    await publish_event(
        event_type=f"flight.{data.event_type}",
        payload={
            "id": event.id,
            "device_id": event.device_id,
            "task_id": event.task_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        },
    )

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
