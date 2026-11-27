"""Organization API keys: a named, revocable Bearer credential with a read-only or read-write scope.

The secret (``ifk_`` + 256 random bits) is shown once and only its SHA-256 is stored; a random secret of that
length needs no salt or slow hash. A key opens a deliberately small part of the API (``SCOPE_ROUTES``): anything
not listed there, such as approvals, settings, members, keys and webhooks, is refused for every key, whatever its scope.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.db import new_session, session_scope
from app.models import ApiKey
from app.services import audit
from app.services.rbac import Perm

KEY_PREFIX = "ifk_"
SCOPES = ("read", "read_write")
MAX_ACTIVE_KEYS = 25
#: how often a busy key rewrites its last-used time
LAST_USED_RESOLUTION_SECONDS = 60

_READ_ROUTES = {
    ("GET", "/api/invoices"), ("GET", "/api/invoices/{invoice_id}"),
    ("GET", "/api/exceptions"), ("GET", "/api/exceptions/{exception_id}"),
    ("GET", "/api/suppliers"), ("GET", "/api/suppliers/{supplier_id}"),
    ("GET", "/api/purchase-orders"), ("GET", "/api/purchase-orders/{po_id}"),
}
_WRITE_ROUTES = {("POST", "/api/invoices/upload")}

#: the whole API surface a key may use, by route template
SCOPE_ROUTES: dict[str, set[tuple[str, str]]] = {"read": set(_READ_ROUTES), "read_write": _READ_ROUTES | _WRITE_ROUTES}

#: the permissions a key carries (the RBAC check still runs on every endpoint it reaches)
SCOPE_PERMS: dict[str, set[Perm]] = {
    "read": {Perm.INVOICE_READ, Perm.MASTERDATA_READ},
    "read_write": {Perm.INVOICE_READ, Perm.MASTERDATA_READ, Perm.INVOICE_UPLOAD},
}


@dataclass(frozen=True)
class KeyIdentity:
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    scope: str

    @property
    def perms(self) -> set[Perm]:
        return SCOPE_PERMS[self.scope]


def looks_like_key(token: str) -> bool:
    return token.startswith(KEY_PREFIX)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def route_allowed(scope: str, method: str, route_path: str | None) -> bool:
    return (method.upper(), route_path or "") in SCOPE_ROUTES.get(scope, ())


def serialize(key: ApiKey) -> dict:
    return {"id": str(key.id), "name": key.name, "scope": key.scope, "prefix": key.prefix,
            "created_at": key.created_at.isoformat(), "created_by": str(key.created_by) if key.created_by else None,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None}


def create(db: Session, *, org_id: uuid.UUID, name: str, scope: str, actor_id: uuid.UUID, actor_label: str) -> tuple[ApiKey, str]:
    """Returns the stored key and its secret; the secret is never recoverable afterwards."""
    secret = KEY_PREFIX + secrets.token_urlsafe(32)
    key = ApiKey(organization_id=org_id, name=name.strip(), scope=scope, prefix=secret[:12],
                 key_hash=hash_secret(secret), created_by=actor_id)
    db.add(key)
    db.flush()
    audit.record(db, org_id=org_id, action="api_key.created", entity_type="api_key", entity_id=key.id,
                 actor_id=actor_id, actor_label=actor_label, after={"name": key.name, "scope": key.scope, "prefix": key.prefix})
    return key, secret


def revoke(db: Session, key: ApiKey, *, actor_id: uuid.UUID, actor_label: str) -> bool:
    if key.revoked_at is not None:
        return False
    key.revoked_at, key.revoked_by = datetime.now(UTC), actor_id
    db.flush()
    audit.record(db, org_id=key.organization_id, action="api_key.revoked", entity_type="api_key", entity_id=key.id,
                 actor_id=actor_id, actor_label=actor_label, before={"name": key.name, "scope": key.scope},
                 after={"revoked": True})
    return True


def authenticate(secret: str) -> KeyIdentity | None:
    """Find the active key for a presented secret, or None. Records its use at most once a minute."""
    digest = hash_secret(secret)
    session = new_session()  # no tenant yet: the policy lets this one transaction see only the row with this hash
    try:
        session.execute(text("SELECT set_config('app.api_key_hash', :h, true)"), {"h": digest})
        key = session.scalars(select(ApiKey).where(ApiKey.key_hash == digest)).first()
        if key is None or key.revoked_at is not None:
            return None
        identity = KeyIdentity(key.id, key.organization_id, key.name, key.scope)
    finally:
        session.close()
    with session_scope(identity.org_id) as s:
        now = datetime.now(UTC)
        s.execute(update(ApiKey).where(
            ApiKey.id == identity.id,
            (ApiKey.last_used_at.is_(None)) | (ApiKey.last_used_at < now - timedelta(seconds=LAST_USED_RESOLUTION_SECONDS)),
        ).values(last_used_at=now))
    return identity
