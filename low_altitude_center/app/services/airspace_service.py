import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Airspace
from ..schemas.schemas import AirspaceCreate, AirspaceApprove
from ..core.events import publish_event


async def create_airspace(db: AsyncSession, data: AirspaceCreate) -> Airspace:
    airspace = Airspace(
        name=data.name,
        area_json=json.dumps(data.area),
        floor_altitude=data.floor_altitude,
        ceiling_altitude=data.ceiling_altitude,
        status="pending",
        applicant=data.applicant,
        apply_time=datetime.now(timezone.utc),
        valid_from=data.valid_from,
        valid_to=data.valid_to,
    )
    db.add(airspace)
    await db.commit()
    await db.refresh(airspace)
    return airspace


async def get_airspace(db: AsyncSession, airspace_id: int) -> Optional[Airspace]:
    result = await db.execute(select(Airspace).where(Airspace.id == airspace_id))
    return result.scalars().first()


async def list_airspaces(
    db: AsyncSession,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    count_query = select(func.count()).select_from(Airspace)
    query = select(Airspace)

    if status is not None:
        count_query = count_query.where(Airspace.status == status)
        query = query.where(Airspace.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(Airspace.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def approve_airspace(
    db: AsyncSession, airspace_id: int, data: AirspaceApprove
) -> Optional[Airspace]:
    airspace = await get_airspace(db, airspace_id)
    if airspace is None:
        return None

    if data.approved:
        airspace.status = "approved"
        airspace.approver = data.approver
        airspace.approve_time = datetime.now(timezone.utc)
    else:
        airspace.status = "rejected"
        airspace.reject_reason = data.reject_reason

    await db.commit()
    await db.refresh(airspace)

    await publish_event(
        event_type="airspace.status_changed",
        payload={
            "airspace_id": airspace.id,
            "status": airspace.status,
            "name": airspace.name,
        },
    )

    return airspace


async def query_approval_progress(db: AsyncSession, airspace_id: int) -> dict:
    airspace = await get_airspace(db, airspace_id)
    if airspace is None:
        return None

    return {
        "airspace_id": airspace.id,
        "status": airspace.status,
        "apply_time": airspace.apply_time,
        "approve_time": airspace.approve_time,
        "approver": airspace.approver,
        "reject_reason": airspace.reject_reason,
    }


async def revoke_airspace(db: AsyncSession, airspace_id: int) -> Optional[Airspace]:
    airspace = await get_airspace(db, airspace_id)
    if airspace is None:
        return None

    airspace.status = "revoked"
    await db.commit()
    await db.refresh(airspace)

    await publish_event(
        event_type="airspace.status_changed",
        payload={
            "airspace_id": airspace.id,
            "status": "revoked",
            "name": airspace.name,
        },
    )

    return airspace
