import asyncio
import json
import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

_subscriptions: Dict[str, List[dict]] = {}
_callback_registry: Dict[str, List[Callable]] = {}


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
            asyncio.create_task(_send_callback(callback_url, event_type, payload))


async def _send_callback(callback_url: str, event_type: str, payload: dict):
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json={"event_type": event_type, "payload": payload},
                timeout=10.0,
            )
            logger.info("Callback sent to %s for event %s", callback_url, event_type)
    except Exception as e:
        logger.error("Callback failed to %s: %s", callback_url, e)


def get_subscriptions() -> Dict[str, dict]:
    return _subscriptions
