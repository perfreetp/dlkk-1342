from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import airspace_service
from app.schemas.schemas import AirspaceCreate, AirspaceApprove, AirspaceOut

router = APIRouter(prefix="/api/v1/airspaces", tags=["空域管理"])


@router.post("/", response_model=AirspaceOut)
async def create_airspace(data: AirspaceCreate, db: AsyncSession = Depends(get_db)):
    return await airspace_service.create_airspace(db, data)


@router.get("/")
async def list_airspaces(
    status: str = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    items, total = await airspace_service.list_airspaces(db, status=status, page=page, page_size=page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{airspace_id}", response_model=AirspaceOut)
async def get_airspace(airspace_id: int, db: AsyncSession = Depends(get_db)):
    airspace = await airspace_service.get_airspace(db, airspace_id)
    if airspace is None:
        raise HTTPException(status_code=404, detail="Airspace not found")
    return airspace


@router.post("/{airspace_id}/approve", response_model=AirspaceOut)
async def approve_airspace(
    airspace_id: int, data: AirspaceApprove, db: AsyncSession = Depends(get_db)
):
    airspace = await airspace_service.approve_airspace(db, airspace_id, data)
    if airspace is None:
        raise HTTPException(status_code=404, detail="Airspace not found")
    return airspace


@router.get("/{airspace_id}/progress")
async def query_approval_progress(airspace_id: int, db: AsyncSession = Depends(get_db)):
    result = await airspace_service.query_approval_progress(db, airspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Airspace not found")
    return result


@router.post("/{airspace_id}/revoke", response_model=AirspaceOut)
async def revoke_airspace(airspace_id: int, db: AsyncSession = Depends(get_db)):
    airspace = await airspace_service.revoke_airspace(db, airspace_id)
    if airspace is None:
        raise HTTPException(status_code=404, detail="Airspace not found")
    return airspace
