"""Fixed-window rate limiter backed by Redis (fails open if Redis is unavailable)."""
from __future__ import annotations

import time

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.services.events import get_redis

log = get_logger(__name__)


def check_rate_limit(bucket: str, limit: int, window_seconds: int = 60) -> None:
    window = int(time.time() // window_seconds)
    key = f"invoiceflow:rl:{bucket}:{window}"
    try:
        r = get_redis()
        count = r.incr(key)
        if count == 1:
            r.expire(key, window_seconds + 1)
    except Exception as exc:  # noqa: BLE001
        log.warning("rate_limit_unavailable", error=str(exc))
        return
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, please retry later.",
            headers={"Retry-After": str(window_seconds)},
        )


def check_daily_ai_limit(request) -> None:  # noqa: ANN001 - a starlette Request
    """A daily cap on model-backed questions per visitor address (RATE_LIMIT_AI_PER_DAY), on top of the per-minute
    limit per user: on a public demo every visitor shares the same demo accounts, so the address is what tells them
    apart. The window resets at midnight UTC."""
    from app.core.client_ip import client_ip
    from app.core.config import get_settings

    limit = get_settings().rate_limit_ai_per_day
    if limit > 0:
        check_rate_limit(f"ai-day:{client_ip(request)}", limit, window_seconds=86400)
