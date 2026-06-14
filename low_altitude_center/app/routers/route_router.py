from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import route_service
from app.schemas.schemas import RouteCreate, RouteOut, RouteValidateResult

router = APIRouter(prefix="/api/v1/routes", tags=["航线管理"])


@router.post("/", response_model=RouteOut)
async def create_route(route: RouteCreate, db: AsyncSession = Depends(get_db)):
    return await route_service.create_route(db, route)


@router.get("/")
async def list_routes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    items, total = await route_service.list_routes(db, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{route_id}", response_model=RouteOut)
async def get_route(route_id: int, db: AsyncSession = Depends(get_db)):
    route = await route_service.get_route(db, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.post("/{route_id}/validate", response_model=RouteValidateResult)
async def validate_route(route_id: int, db: AsyncSession = Depends(get_db)):
    result = await route_service.validate_route(db, route_id)
    if result.is_valid is False and result.errors == ["Route not found"]:
        raise HTTPException(status_code=404, detail="Route not found")
    return result


@router.delete("/{route_id}")
async def delete_route(route_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await route_service.delete_route(db, route_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"deleted": True}
