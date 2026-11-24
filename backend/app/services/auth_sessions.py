"""Server-side sessions behind the short-lived access tokens.

A session is created at login. Its id travels in every access token (``sid``) and is
checked on each request, so logout, "sign out everywhere", deactivation and expiry take
effect immediately instead of when the JWT expires.

The refresh token has the form ``<session id>.<secret>``; only SHA-256(secret) is stored.
Every refresh rotates the secret. Presenting a secret that was already rotated away means
the token was copied: the session is revoked (reuse detection), which also kills the
access token of whoever holds the current one.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import new_session
from app.models import DEFAULT_ORG_SETTINGS, AuthSession, Organization


class RefreshError(Exception):
    def __init__(self, reason: str, session: AuthSession | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.session = session


@dataclass
class Issued:
    session: AuthSession
    refresh_token: str


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _active(sess: AuthSession | None, now: datetime | None = None) -> bool:
    now = now or _now()
    return bool(sess and sess.revoked_at is None and sess.expires_at > now and sess.absolute_expires_at > now)


def lifetimes(db: Session, org_id: uuid.UUID) -> tuple[timedelta, timedelta]:
    """(idle timeout, absolute maximum) from the organization's security settings."""
    s = get_settings()
    org = db.get(Organization, org_id)
    sec = {**DEFAULT_ORG_SETTINGS["security"], **((org.settings or {}).get("security", {}) if org else {})}
    idle = int(sec.get("session_idle_hours") or s.session_idle_hours)
    max_days = int(sec.get("session_max_days") or s.session_max_days)
    return timedelta(hours=idle), timedelta(days=max_days)


def create(db: Session, *, user_id: uuid.UUID, org_id: uuid.UUID, ip: str | None, user_agent: str | None) -> Issued:
    now = _now()
    idle, maximum = lifetimes(db, org_id)
    secret = secrets.token_urlsafe(32)
    sess = AuthSession(id=uuid.uuid4(), user_id=user_id, organization_id=org_id, refresh_token_hash=_hash(secret),
                       expires_at=now + idle, absolute_expires_at=now + maximum, last_used_at=now,
                       ip=(ip or "")[:64] or None, user_agent=(user_agent or "")[:300] or None)
    db.add(sess)
    db.flush()
    return Issued(sess, f"{sess.id}.{secret}")


def rotate(db: Session, refresh_token: str) -> Issued:
    """Exchange a refresh token for a new one. Raises RefreshError (session revoked on reuse)."""
    sid, _, secret = (refresh_token or "").partition(".")
    try:
        sess = db.get(AuthSession, uuid.UUID(sid), with_for_update=True)
    except ValueError:
        sess = None
    if sess is None or not secret:
        raise RefreshError("unknown")
    if not hmac.compare_digest(sess.refresh_token_hash, _hash(secret)):
        if sess.revoked_at is None:
            sess.revoked_at, sess.revoked_reason = _now(), "refresh_reuse"
        raise RefreshError("reuse", sess)
    if not _active(sess):
        raise RefreshError("inactive", sess)
    now = _now()
    new_secret = secrets.token_urlsafe(32)
    sess.refresh_token_hash = _hash(new_secret)
    sess.last_used_at = now
    sess.expires_at = min(now + lifetimes(db, sess.organization_id)[0], sess.absolute_expires_at)
    return Issued(sess, f"{sess.id}.{new_secret}")


def match(db: Session, refresh_token: str) -> AuthSession | None:
    """The session a refresh token belongs to, if its secret is the current one (no rotation)."""
    sid, _, secret = (refresh_token or "").partition(".")
    try:
        sess = db.get(AuthSession, uuid.UUID(sid)) if secret else None
    except ValueError:
        return None
    return sess if sess is not None and hmac.compare_digest(sess.refresh_token_hash, _hash(secret)) else None


def revoke(db: Session, sid: uuid.UUID | str, reason: str = "logout") -> None:
    sess = db.get(AuthSession, uuid.UUID(str(sid)))
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at, sess.revoked_reason = _now(), reason


def revoke_all(db: Session, user_id: uuid.UUID, reason: str = "logout_all", *, keep: uuid.UUID | None = None) -> int:
    stmt = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if keep is not None:
        stmt = stmt.where(AuthSession.id != keep)
    res = db.execute(stmt.values(revoked_at=_now(), revoked_reason=reason))
    return res.rowcount or 0


def get_active(db: Session, sid: uuid.UUID | str) -> AuthSession | None:
    try:
        sess = db.get(AuthSession, uuid.UUID(str(sid)))
    except ValueError:
        return None
    return sess if _active(sess) else None


def is_active(sid: uuid.UUID | str) -> bool:
    """Standalone check, used by long-lived event streams to notice revocation."""
    db = new_session()
    try:
        return get_active(db, sid) is not None
    finally:
        db.close()


def active_sessions(db: Session, user_id: uuid.UUID) -> list[AuthSession]:
    now = _now()
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))).all()
    return [r for r in rows if _active(r, now)]
