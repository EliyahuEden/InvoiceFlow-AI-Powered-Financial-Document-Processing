"""Daily AI token budget per business.

Every model call is recorded through ``telemetry.record_call``, which charges its tokens here. When a business
has used its budget for the day, ``get_llm(org_id)`` returns no model and every feature takes its existing
offline path (rules, templates, extractive answers), so a shared provider key cannot be used up by one tenant.
Like the rate limiter, the budget fails open if Redis is unavailable: Redis is not the source of truth.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.events import get_redis

log = get_logger(__name__)


def _key(org_id: uuid.UUID | str) -> str:
    return f"invoiceflow:ai_tokens:{org_id}:{datetime.now(UTC).date().isoformat()}"


def used_today(org_id: uuid.UUID | str) -> int:
    try:
        return int(get_redis().get(_key(org_id)) or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_budget_unavailable", error=str(exc)[:200])
        return 0


def charge(org_id: uuid.UUID | str, tokens: int) -> None:
    if tokens <= 0:
        return
    try:
        r = get_redis()
        key = _key(org_id)
        r.incrby(key, tokens)
        r.expire(key, 2 * 24 * 3600)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_budget_unavailable", error=str(exc)[:200])


def allowed(org_id: uuid.UUID | str) -> bool:
    budget = get_settings().ai_daily_token_budget
    return budget <= 0 or used_today(org_id) < budget
