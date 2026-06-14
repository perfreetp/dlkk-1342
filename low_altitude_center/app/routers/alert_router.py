from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import alert_service
from app.schemas.schemas import AlertCreate, AlertOut, SubscriptionCreate, SubscriptionOut

router = APIRouter(prefix="/api/v1/alerts", tags=["告警管理"])


@router.post("/", response_model=AlertOut)
async def create_alert(alert: AlertCreate, db: AsyncSession = Depends(get_db)):
    return await alert_service.create_alert(db, alert)


@router.get("/")
async def list_alerts(
    alert_type: str | None = None,
    severity: str | None = None,
    is_read: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    items, total = await alert_service.list_alerts(
        db, alert_type=alert_type, severity=severity, is_read=is_read, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/subscriptions")
async def subscribe(body: SubscriptionCreate):
    return await alert_service.subscribe(body)


@router.delete("/subscriptions/{subscriber_id}")
async def unsubscribe(subscriber_id: str):
    return await alert_service.unsubscribe(subscriber_id)


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions():
    return alert_service.list_subscriptions()


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await alert_service.get_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/read", response_model=AlertOut)
async def mark_alert_read(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await alert_service.mark_alert_read(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
