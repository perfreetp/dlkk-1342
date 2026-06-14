import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

_subscriptions: Dict[str, List[dict]] = {}
_callback_registry: Dict[str, List[Callable]] = {}
_delivery_log: List[dict] = []
_MAX_DELIVERY_LOG = 200


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


def _log_delivery(subscriber_id: str, callback_url: str, event_type: str,
                  success: bool, status_code: int = None, error: str = None):
    entry = {
        "subscriber_id": subscriber_id,
        "callback_url": callback_url,
        "event_type": event_type,
        "success": success,
        "status_code": status_code,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _delivery_log.append(entry)
    if len(_delivery_log) > _MAX_DELIVERY_LOG:
        _delivery_log.pop(0)


async def _send_callback(callback_url: str, event_type: str, payload: dict, subscriber_id: str):
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                callback_url,
                json={"event_type": event_type, "payload": payload},
                timeout=10.0,
            )
            _log_delivery(subscriber_id, callback_url, event_type, True, status_code=resp.status_code)
            logger.info("Callback sent to %s for event %s", callback_url, event_type)
    except Exception as e:
        _log_delivery(subscriber_id, callback_url, event_type, False, error=str(e))
        logger.error("Callback failed to %s: %s", callback_url, e)


def get_subscriptions() -> Dict[str, dict]:
    return _subscriptions


def get_delivery_log(subscriber_id: str = None, limit: int = 50) -> list[dict]:
    logs = _delivery_log
    if subscriber_id:
        logs = [l for l in logs if l["subscriber_id"] == subscriber_id]
    return list(reversed(logs[-limit:]))
