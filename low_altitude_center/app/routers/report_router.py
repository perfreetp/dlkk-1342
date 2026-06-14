from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import report_service
from app.schemas.schemas import MediaFileCreate, MediaFileOut, AnomalyPointCreate, AnomalyPointOut, ReportQuery

router = APIRouter(prefix="/api/v1/reports", tags=["报表管理"])


@router.post("/media", response_model=MediaFileOut)
async def upload_media(data: MediaFileCreate, db: AsyncSession = Depends(get_db)):
    return await report_service.upload_media(db, data)


@router.get("/media")
async def list_media(
    task_id: int | None = None,
    file_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    items, total = await report_service.list_media(
        db, task_id=task_id, file_type=file_type, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/anomalies", response_model=AnomalyPointOut)
async def create_anomaly(data: AnomalyPointCreate, db: AsyncSession = Depends(get_db)):
    return await report_service.create_anomaly(db, data)


@router.get("/anomalies")
async def list_anomalies(
    task_id: int | None = None,
    severity: str | None = None,
    is_resolved: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    items, total = await report_service.list_anomalies(
        db, task_id=task_id, severity=severity, is_resolved=is_resolved, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/anomalies/{anomaly_id}/resolve", response_model=AnomalyPointOut)
async def resolve_anomaly(anomaly_id: int, db: AsyncSession = Depends(get_db)):
    anomaly = await report_service.resolve_anomaly(db, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly


@router.get("/daily")
async def daily_report(
    report_date: datetime | None = None,
    device_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await report_service.generate_daily_report(db, report_date=report_date, device_id=device_id)


@router.get("/monthly")
async def monthly_report(
    year: int = None,
    month: int = None,
    device_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await report_service.generate_monthly_report(db, year=year, month=month, device_id=device_id)


@router.get("/utilization")
async def utilization_stats(
    device_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_utilization_stats(db, device_id=device_id, start_date=start_date, end_date=end_date)
