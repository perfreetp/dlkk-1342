from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Device, MaintenanceRecord
from ..schemas.schemas import (
    DeviceCreate,
    DeviceUpdate,
    MaintenanceRecordCreate,
    UtilizationStat,
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
    query = query.offset(offset).limit(page_size)
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
        if hours_in_period > 0:
            utilization_rate = round(
                device.total_flight_hours / hours_in_period * 100, 2
            )
        else:
            utilization_rate = 0.0

        stats.append(
            UtilizationStat(
                device_id=device.id,
                device_name=device.name,
                total_flight_hours=device.total_flight_hours,
                total_flight_count=device.total_flight_count,
                utilization_rate=utilization_rate,
                period_start=start_date,
                period_end=end_date,
            )
        )

    return stats
