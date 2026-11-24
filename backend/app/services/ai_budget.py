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


PAID_PROVIDERS = {"openai", "anthropic"}  # billed per token; "groq" (free tier) and local servers are "shared"


def bucket_for(provider: str | None) -> str:
    return "paid" if provider in PAID_PROVIDERS else "shared"


def _key(org_id: uuid.UUID | str, bucket: str = "shared") -> str:
    suffix = "" if bucket == "shared" else f":{bucket}"
    return f"invoiceflow:ai_tokens:{org_id}:{datetime.now(UTC).date().isoformat()}{suffix}"


def used_today(org_id: uuid.UUID | str, bucket: str | None = None) -> int:
    """Tokens used today: one bucket, or both when ``bucket`` is None."""
    try:
        r = get_redis()
        keys = [_key(org_id, b) for b in (("shared", "paid") if bucket is None else (bucket,))]
        return sum(int(r.get(k) or 0) for k in keys)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_budget_unavailable", error=str(exc)[:200])
        return 0


def charge(org_id: uuid.UUID | str, tokens: int, bucket: str = "shared") -> None:
    if tokens <= 0:
        return
    try:
        r = get_redis()
        key = _key(org_id, bucket)
        r.incrby(key, tokens)
        r.expire(key, 2 * 24 * 3600)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_budget_unavailable", error=str(exc)[:200])


def allowed(org_id: uuid.UUID | str, bucket: str = "shared") -> bool:
    s = get_settings()
    budget = s.ai_paid_daily_token_budget if bucket == "paid" else s.ai_daily_token_budget
    return budget <= 0 or used_today(org_id, bucket) < budget
