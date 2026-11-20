"""Append-only, hash-chained audit logging.

Each entry stores sha256(prev_hash || canonical_json(entry)). Any modification or
deletion of a historical row breaks the chain, which ``verify_chain`` detects.
The database role used by the app additionally lacks UPDATE/DELETE on the table.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog


def _default(o: Any) -> Any:
    if isinstance(o, (uuid.UUID, Decimal)):
        return str(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(type(o))


def to_jsonable(data: Any) -> Any:
    if data is None:
        return None
    return json.loads(json.dumps(data, default=_default))


def _entry_hash(prev_hash: str | None, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=_default)
    return hashlib.sha256(((prev_hash or "") + canonical).encode("utf-8")).hexdigest()


def record(
    session: Session,
    *,
    org_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor_type: str = "user",
    actor_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    meta: dict | None = None,
) -> AuditLog:
    # Serialize chain appends per organization (transaction-scoped advisory lock).
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{org_id}"})
    prev = session.execute(
        select(AuditLog.hash)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    created_at = datetime.now(UTC)
    entry_id = uuid.uuid4()
    payload = {
        "id": str(entry_id),
        "organization_id": str(org_id),
        "created_at": created_at.isoformat(),
        "actor_type": actor_type,
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "before": to_jsonable(before),
        "after": to_jsonable(after),
        "meta": to_jsonable(meta or {}),
    }
    log = AuditLog(
        id=entry_id,
        organization_id=org_id,
        created_at=created_at,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=payload["before"],
        after=payload["after"],
        meta=payload["meta"],
        prev_hash=prev,
        hash=_entry_hash(prev, payload),
    )
    session.add(log)
    session.flush()
    return log


def verify_chain(session: Session, org_id: uuid.UUID) -> dict:
    rows = session.execute(
        select(AuditLog).where(AuditLog.organization_id == org_id).order_by(AuditLog.created_at, AuditLog.id)
    ).scalars()
    prev: str | None = None
    count = 0
    for row in rows:
        payload = {
            "id": str(row.id),
            "organization_id": str(row.organization_id),
            "created_at": row.created_at.astimezone(UTC).isoformat(),
            "actor_type": row.actor_type,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id) if row.entity_id else None,
            "before": row.before,
            "after": row.after,
            "meta": row.meta,
        }
        if row.prev_hash != prev or row.hash != _entry_hash(prev, payload):
            return {"valid": False, "checked": count, "broken_at": str(row.id)}
        prev = row.hash
        count += 1
    return {"valid": True, "checked": count, "broken_at": None}
