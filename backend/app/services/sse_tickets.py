"""Single-use, short-lived tickets for opening the server-sent-events stream.

``EventSource`` cannot send an Authorization header, and a long-lived stream should not
outlive the session it was opened for. The client first asks for a ticket with its normal
credentials, then opens ``/api/events?ticket=…``. A ticket is random (no token in the URL),
valid for ``sse_ticket_seconds`` and deleted on first use. The stream itself re-checks the
session periodically and closes once it is revoked.
"""
from __future__ import annotations

import json
import secrets
import uuid

from app.core.config import get_settings
from app.services.events import get_redis

_PREFIX = "invoiceflow:sse_ticket:"


def issue(*, user_id: uuid.UUID, org_id: uuid.UUID, sid: str) -> tuple[str, int]:
    ttl = get_settings().sse_ticket_seconds
    ticket = secrets.token_urlsafe(32)
    get_redis().set(_PREFIX + ticket, json.dumps({"sub": str(user_id), "org": str(org_id), "sid": sid}), ex=ttl)
    return ticket, ttl


def consume(ticket: str) -> dict | None:
    if not ticket or len(ticket) > 100:
        return None
    raw = get_redis().getdel(_PREFIX + ticket)
    return json.loads(raw) if raw else None
