from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import device_service
from app.schemas.schemas import (
    DeviceCreate,
    DeviceUpdate,
    DeviceOut,
    MaintenanceRecordCreate,
    MaintenanceRecordOut,
    UtilizationStat,
)

router = APIRouter(prefix="/api/v1/devices", tags=["设备管理"])


@router.post("/", response_model=DeviceOut)
async def create_device(device: DeviceCreate, db: AsyncSession = Depends(get_db)):
    return await device_service.create_device(db, device)


@router.get("/")
async def list_devices(
    device_type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    total, items = await device_service.list_devices(
        db, device_type=device_type, status=status, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/utilization", response_model=list[UtilizationStat])
async def get_utilization_stats(
    device_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await device_service.get_utilization_stats(
        db, device_id=device_id, start_date=start_date, end_date=end_date
    )


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.put("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int, device: DeviceUpdate, db: AsyncSession = Depends(get_db)
):
    updated = await device_service.update_device(db, device_id, device)
    if not updated:
        raise HTTPException(status_code=404, detail="Device not found")
    return updated


@router.post("/{device_id}/maintenance", response_model=MaintenanceRecordOut)
async def add_maintenance_record(
    device_id: int,
    record: MaintenanceRecordCreate,
    db: AsyncSession = Depends(get_db),
):
    device = await device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return await device_service.add_maintenance_record(db, device_id, record)


@router.get("/{device_id}/maintenance", response_model=list[MaintenanceRecordOut])
async def get_maintenance_records(
    device_id: int, db: AsyncSession = Depends(get_db)
):
    device = await device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return await device_service.get_maintenance_records(db, device_id)
