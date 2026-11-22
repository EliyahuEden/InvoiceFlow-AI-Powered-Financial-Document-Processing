"""Single-use emailed tokens (password reset, invitation). The raw token only ever exists in the email;
the database keeps its SHA-256, so a database leak does not hand out working links."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuthToken

PASSWORD_RESET, INVITE = "password_reset", "invite"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue(db: Session, *, user_id: uuid.UUID, purpose: str, ttl: timedelta,
          org_id: uuid.UUID | None = None) -> str:
    """A new token; any earlier unused token of the same purpose for this user stops working."""
    now = datetime.now(UTC)
    revoke_all(db, user_id, purposes=(purpose,), now=now)
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user_id, organization_id=org_id, purpose=purpose, token_hash=_hash(raw),
                     expires_at=now + ttl))
    db.flush()
    return raw


def consume(db: Session, raw: str, purposes: tuple[str, ...] = (PASSWORD_RESET, INVITE)) -> AuthToken | None:
    """Mark a valid token used and return it, or None when it is unknown, used, expired or of another purpose."""
    if not raw or len(raw) > 200:
        return None
    now = datetime.now(UTC)
    token = db.scalars(select(AuthToken).where(AuthToken.token_hash == _hash(raw)).with_for_update()).first()
    if token is None or token.purpose not in purposes or token.used_at is not None or token.expires_at <= now:
        return None
    token.used_at = now
    db.flush()
    return token


def revoke_all(db: Session, user_id: uuid.UUID, purposes: tuple[str, ...] = (PASSWORD_RESET, INVITE),
               now: datetime | None = None) -> None:
    db.execute(update(AuthToken).where(AuthToken.user_id == user_id, AuthToken.purpose.in_(purposes),
                                       AuthToken.used_at.is_(None)).values(used_at=now or datetime.now(UTC)))
