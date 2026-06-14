from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import flight_service
from app.schemas.schemas import (
    FlightPositionCreate,
    FlightPositionOut,
    FlightEventCreate,
    FlightEventOut,
    TrajectoryPoint,
)

router = APIRouter(prefix="/api/v1/flights", tags=["飞行管理"])


@router.post("/positions", response_model=FlightPositionOut)
async def report_position(
    position: FlightPositionCreate, db: AsyncSession = Depends(get_db)
):
    return await flight_service.report_position(db, position)


@router.get("/{device_id}/trajectory", response_model=list[TrajectoryPoint])
async def get_trajectory(
    device_id: int,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await flight_service.get_trajectory(
        db, device_id, start_time=start_time, end_time=end_time
    )


@router.post("/events", response_model=FlightEventOut)
async def record_event(
    event: FlightEventCreate, db: AsyncSession = Depends(get_db)
):
    return await flight_service.record_event(db, event)


@router.get("/events")
async def get_flight_events(
    task_id: int | None = None,
    device_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1),
    db: AsyncSession = Depends(get_db),
):
    items, total = await flight_service.get_flight_events(
        db, task_id=task_id, device_id=device_id, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}
