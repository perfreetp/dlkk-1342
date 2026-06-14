import json
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Alert
from ..schemas.schemas import AlertCreate, AlertOut, SubscriptionCreate
from ..core.events import register_subscription, remove_subscription, publish_event, get_subscriptions


async def create_alert(db: AsyncSession, data: AlertCreate) -> Alert:
    details_json = json.dumps(data.details, ensure_ascii=False)
    alert = Alert(
        task_id=data.task_id,
        device_id=data.device_id,
        alert_type=data.alert_type,
        severity=data.severity,
        message=data.message,
        latitude=data.latitude,
        longitude=data.longitude,
        details_json=details_json,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    await publish_event(
        event_type=f"alert.{data.alert_type}",
        payload={
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "device_id": alert.device_id,
            "task_id": alert.task_id,
        },
    )

    return alert


async def get_alert(db: AsyncSession, alert_id: int) -> Optional[Alert]:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    return result.scalars().first()


async def list_alerts(
    db: AsyncSession,
    alert_type: str = None,
    severity: str = None,
    is_read: int = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = select(Alert)
    count_query = select(func.count()).select_from(Alert)

    if alert_type is not None:
        query = query.where(Alert.alert_type == alert_type)
        count_query = count_query.where(Alert.alert_type == alert_type)
    if severity is not None:
        query = query.where(Alert.severity == severity)
        count_query = count_query.where(Alert.severity == severity)
    if is_read is not None:
        query = query.where(Alert.is_read == is_read)
        count_query = count_query.where(Alert.is_read == is_read)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def mark_alert_read(db: AsyncSession, alert_id: int) -> Optional[Alert]:
    alert = await get_alert(db, alert_id)
    if alert is None:
        return None
    alert.is_read = 1
    await db.commit()
    await db.refresh(alert)
    return alert


async def subscribe(sub_data: SubscriptionCreate) -> dict:
    await register_subscription(
        subscriber_id=sub_data.subscriber_id,
        event_types=sub_data.event_types,
        callback_url=sub_data.callback_url,
    )
    return {
        "subscriber_id": sub_data.subscriber_id,
        "event_types": sub_data.event_types,
        "callback_url": sub_data.callback_url,
    }


async def unsubscribe(subscriber_id: str) -> dict:
    await remove_subscription(subscriber_id)
    return {"subscriber_id": subscriber_id, "removed": True}


def list_subscriptions() -> dict:
    return get_subscriptions()
