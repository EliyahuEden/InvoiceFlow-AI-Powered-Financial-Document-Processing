"""Live progress events (Redis pub/sub), consumed by the SSE endpoint.

Publishing is best-effort: the job row in PostgreSQL is the durable source of truth
for status/progress, so a Redis outage degrades live updates to polling, never
correctness.
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache

import redis

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True, socket_timeout=3)


def channel(org_id: uuid.UUID | str) -> str:
    return f"invoiceflow:org:{org_id}:events"


def publish(org_id: uuid.UUID | str, event: str, data: dict) -> None:
    try:
        get_redis().publish(channel(org_id), json.dumps({"event": event, "data": data}, default=str))
    except Exception as exc:  # noqa: BLE001
        log.warning("event_publish_failed", error=str(exc), event_name=event)
