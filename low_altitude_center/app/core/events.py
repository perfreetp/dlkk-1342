import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

_subscriptions: Dict[str, dict] = {}
_callback_registry: Dict[str, List[Callable]] = {}
_delivery_log: List[dict] = []
_MAX_DELIVERY_LOG = 200
_failed_deliveries: List[dict] = []
_MAX_FAILED_DELIVERIES = 100


async def register_subscription(subscriber_id: str, event_types: List[str], callback_url: str):
    _subscriptions[subscriber_id] = {
        "event_types": event_types,
        "callback_url": callback_url,
    }
    logger.info("Subscription registered: %s -> %s for %s", subscriber_id, callback_url, event_types)


async def remove_subscription(subscriber_id: str):
    _subscriptions.pop(subscriber_id, None)
    logger.info("Subscription removed: %s", subscriber_id)


async def publish_event(event_type: str, payload: dict):
    logger.info("Publishing event: %s", event_type)
    for sub_id, sub in list(_subscriptions.items()):
        if event_type in sub.get("event_types", []):
            callback_url = sub["callback_url"]
            asyncio.create_task(_send_callback(callback_url, event_type, payload, sub_id))


def _create_delivery_entry(subscriber_id: str, callback_url: str, event_type: str, payload: dict) -> dict:
    entry = {
        "delivery_id": str(uuid.uuid4()),
        "subscriber_id": subscriber_id,
        "callback_url": callback_url,
        "event_type": event_type,
        "payload": payload,
        "success": False,
        "attempts": [],
        "first_attempt_at": datetime.now(timezone.utc).isoformat(),
        "last_attempt_at": None,
    }
    _delivery_log.append(entry)
    if len(_delivery_log) > _MAX_DELIVERY_LOG:
        _delivery_log.pop(0)
    return entry


def _add_attempt(entry: dict, success: bool, status_code: int = None, error: str = None):
    attempt = {
        "attempt": len(entry["attempts"]) + 1,
        "success": success,
        "status_code": status_code,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entry["attempts"].append(attempt)
    entry["last_attempt_at"] = attempt["timestamp"]
    entry["success"] = success

    if success:
        _failed_deliveries[:] = [d for d in _failed_deliveries if d["delivery_id"] != entry["delivery_id"]]
    else:
        if not any(d["delivery_id"] == entry["delivery_id"] for d in _failed_deliveries):
            _failed_deliveries.append(entry)
            if len(_failed_deliveries) > _MAX_FAILED_DELIVERIES:
                _failed_deliveries.pop(0)


async def _send_callback(callback_url: str, event_type: str, payload: dict, subscriber_id: str, existing_entry: dict = None):
    entry = existing_entry or _create_delivery_entry(subscriber_id, callback_url, event_type, payload)
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                callback_url,
                json={"event_type": event_type, "payload": payload},
                timeout=10.0,
            )
            _add_attempt(entry, True, status_code=resp.status_code)
            logger.info("Callback sent to %s for event %s (status=%s)", callback_url, event_type, resp.status_code)
    except Exception as e:
        _add_attempt(entry, False, error=str(e))
        logger.error("Callback failed to %s: %s", callback_url, e)


async def retry_failed_deliveries(subscriber_id: str = None, limit: int = 10) -> dict:
    failed = list(_failed_deliveries)
    if subscriber_id:
        failed = [d for d in failed if d["subscriber_id"] == subscriber_id]

    failed = failed[-limit:]
    retried = 0
    for entry in failed:
        sub = _subscriptions.get(entry["subscriber_id"])
        if not sub:
            continue
        callback_url = sub["callback_url"]
        asyncio.create_task(
            _send_callback(callback_url, entry["event_type"], entry["payload"], entry["subscriber_id"], existing_entry=entry)
        )
        retried += 1

    return {
        "retried_count": retried,
        "total_failed": len(list(_failed_deliveries) if not subscriber_id else [d for d in _failed_deliveries if d["subscriber_id"] == subscriber_id]),
    }


def get_subscriptions() -> Dict[str, dict]:
    return _subscriptions


def get_delivery_log(subscriber_id: str = None, limit: int = 50) -> list[dict]:
    logs = list(_delivery_log)
    if subscriber_id:
        logs = [l for l in logs if l["subscriber_id"] == subscriber_id]
    return list(reversed(logs[-limit:]))


def get_failed_deliveries(subscriber_id: str = None, limit: int = 50) -> list[dict]:
    failed = list(_failed_deliveries)
    if subscriber_id:
        failed = [d for d in failed if d["subscriber_id"] == subscriber_id]
    return list(reversed(failed[-limit:]))
