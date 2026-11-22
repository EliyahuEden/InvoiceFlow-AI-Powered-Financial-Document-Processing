"""Organization settings & members, jobs, live events (SSE), health checks."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sse_starlette.sse import EventSourceResponse

from app.api.deps import Principal, get_db, get_principal, principal_from_claims, require
from app.core.db import new_session
from app.core.security import hash_password
from app.models import DEFAULT_ORG_SETTINGS, SETTING_BOUNDS, Job, Membership, Organization, Role, User
from app.services import audit, sse_tickets
from app.services.events import channel, get_redis
from app.services.llm.provider import mode_label
from app.services.rbac import ROLE_PERMISSIONS, Perm

router = APIRouter(tags=["system"])


@router.get("/api/org")
def get_org(p: Principal = Depends(require(Perm.INVOICE_READ))) -> dict:
    return {"id": str(p.org.id), "name": p.org.name, "slug": p.org.slug, "settings": p.org.settings,
            "ai_mode": mode_label(),
            "roles": {r.value: sorted(x.value for x in perms) for r, perms in ROLE_PERMISSIONS.items()}}


class SettingsIn(BaseModel):
    tolerances: dict | None = None
    approval: dict | None = None
    priority: dict | None = None
    security: dict | None = None
    auto_investigate: bool | None = None
    default_locale: str | None = Field(None, pattern="^(he|en)$")


@router.patch("/api/org/settings")
def update_settings(body: SettingsIn, p: Principal = Depends(require(Perm.ORG_MANAGE)), db=Depends(get_db)) -> dict:
    org = db.get(Organization, p.org_id)
    before = json.loads(json.dumps(org.settings))
    new = json.loads(json.dumps(org.settings))
    for section in ("tolerances", "approval", "priority", "security"):
        new[section] = {**DEFAULT_ORG_SETTINGS.get(section, {}), **new.get(section, {})}
        values = getattr(body, section)
        if values:
            for k, v in values.items():
                lo_hi = SETTING_BOUNDS.get(f"{section}.{k}")
                if lo_hi and not (isinstance(v, int) and lo_hi[0] <= v <= lo_hi[1]):
                    raise HTTPException(422, f"{section}.{k} must be a whole number from {lo_hi[0]} to {lo_hi[1]}")
                if k not in new.get(section, {}):
                    raise HTTPException(422, f"Unknown setting {section}.{k}")
                try:
                    if Decimal(str(v)) < 0:
                        raise HTTPException(422, f"{section}.{k} must be non-negative")
                except InvalidOperation as exc:
                    raise HTTPException(422, f"{section}.{k} must be a number") from exc
                new[section][k] = int(v) if k.endswith(("_days", "_hours")) else str(v)
    if body.auto_investigate is not None:
        new["auto_investigate"] = body.auto_investigate
    if body.default_locale:
        new["default_locale"] = body.default_locale
    org.settings = new
    db.flush()
    audit.record(db, org_id=org.id, action="org.settings_updated", entity_type="organization", entity_id=org.id,
                 actor_id=p.user.id, actor_label=p.user.email, before=before, after=new)
    return {"settings": new}


@router.get("/api/org/members")
def members(p: Principal = Depends(require(Perm.INVOICE_READ))) -> dict:
    s = new_session()
    try:
        rows = s.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                         .where(Membership.organization_id == p.org_id).order_by(User.full_name)).all()
        return {"items": [{"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": m.role.value,
                           "is_active": u.is_active, "locale": u.locale} for m, u in rows]}
    finally:
        s.close()


class MemberIn(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)
    full_name: str = Field(..., min_length=2, max_length=200)
    role: Role
    password: str = Field(..., min_length=12, max_length=200)


@router.post("/api/org/members", status_code=201)
def add_member(body: MemberIn, p: Principal = Depends(require(Perm.ORG_MANAGE))) -> dict:
    s = new_session(p.org_id)
    try:
        user = s.scalars(select(User).where(User.email == body.email.lower())).first()
        if user is None:
            user = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password))
            s.add(user)
            s.flush()
        s.add(Membership(user_id=user.id, organization_id=p.org_id, role=body.role))
        try:
            s.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "User is already a member") from exc
        audit.record(s, org_id=p.org_id, action="member.added", entity_type="user", entity_id=user.id,
                     actor_id=p.user.id, actor_label=p.user.email, after={"email": user.email, "role": body.role.value})
        s.commit()
        return {"id": str(user.id)}
    finally:
        s.close()


@router.delete("/api/org/members/{user_id}")
def remove_member(user_id: uuid.UUID, request: Request, p: Principal = Depends(require(Perm.ORG_MANAGE))) -> dict:
    """Remove someone from this business. Their sessions here end at once; their account and any other
    businesses they belong to are untouched. You cannot remove yourself or the last administrator."""
    from app.models import AuthSession
    from sqlalchemy import update

    if request.headers.get("x-requested-with") != "invoiceflow":
        raise HTTPException(403, "Missing CSRF header")
    if user_id == p.user.id:
        raise HTTPException(422, "You cannot remove yourself.")
    s = new_session(p.org_id)
    try:
        m = s.scalars(select(Membership).where(Membership.user_id == user_id, Membership.organization_id == p.org_id)).first()
        if not m:
            raise HTTPException(404, "Member not found")
        if m.role == Role.ADMIN:
            admins = s.scalars(select(Membership).where(Membership.organization_id == p.org_id,
                                                        Membership.role == Role.ADMIN)).all()
            if len(admins) <= 1:
                raise HTTPException(422, "A business needs at least one administrator.")
        email = s.get(User, user_id).email
        s.delete(m)
        s.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.organization_id == p.org_id,
                                            AuthSession.revoked_at.is_(None))
                  .values(revoked_at=datetime.now(UTC), revoked_reason="removed_from_organization"))
        audit.record(s, org_id=p.org_id, action="member.removed", entity_type="user", entity_id=user_id,
                     actor_id=p.user.id, actor_label=p.user.email, before={"email": email, "role": m.role.value})
        s.commit()
        return {"ok": True}
    finally:
        s.close()


class RoleIn(BaseModel):
    role: Role


@router.patch("/api/org/members/{user_id}")
def change_role(user_id: uuid.UUID, body: RoleIn, p: Principal = Depends(require(Perm.ORG_MANAGE))) -> dict:
    if user_id == p.user.id:
        raise HTTPException(422, "You cannot change your own role")
    s = new_session(p.org_id)
    try:
        m = s.scalars(select(Membership).where(Membership.user_id == user_id,
                                               Membership.organization_id == p.org_id)).first()
        if not m:
            raise HTTPException(404, "Member not found")
        before = m.role.value
        m.role = body.role
        audit.record(s, org_id=p.org_id, action="member.role_changed", entity_type="user", entity_id=user_id,
                     actor_id=p.user.id, actor_label=p.user.email, before={"role": before}, after={"role": body.role.value})
        s.commit()
        return {"role": body.role.value}
    finally:
        s.close()


@router.get("/api/jobs/{job_id}")
def job_status(job_id: uuid.UUID, p: Principal = Depends(require(Perm.INVOICE_READ))) -> dict:
    s = new_session()
    try:
        j = s.scalars(select(Job).where(Job.id == job_id, Job.organization_id == p.org_id)).first()
        if not j:
            raise HTTPException(404, "Job not found")
        return {"id": str(j.id), "type": j.type, "status": j.status, "progress": j.progress,
                "message": j.progress_message, "attempts": j.attempts, "max_attempts": j.max_attempts,
                "error": j.last_error, "entity_id": str(j.entity_id) if j.entity_id else None}
    finally:
        s.close()


@router.post("/api/events/ticket")
def events_ticket(request: Request, p: Principal = Depends(get_principal)) -> dict:
    """A single-use ticket for opening the event stream (EventSource cannot send headers)."""
    if request.headers.get("x-requested-with") != "invoiceflow":
        raise HTTPException(403, "Missing CSRF header")
    try:
        ticket, ttl = sse_tickets.issue(user_id=p.user.id, org_id=p.org_id, sid=str(p.session_id))
    except Exception as exc:  # noqa: BLE001 - Redis down: the client falls back to polling
        raise HTTPException(503, "Event stream unavailable") from exc
    return {"ticket": ticket, "expires_in": ttl}


SESSION_RECHECK_SECONDS = 60


@router.get("/api/events")
async def events(request: Request, ticket: str | None = None) -> EventSourceResponse:
    """Server-sent events for the caller's organization (job progress, status changes).

    Opened with a single-use ticket from POST /api/events/ticket (or, for same-origin
    clients, the session cookie). The stream ends once the session is revoked or expires."""
    if ticket:
        claims = await asyncio.to_thread(sse_tickets.consume, ticket)
        if claims is None:
            raise HTTPException(401, "Invalid or expired ticket")
        p = await asyncio.to_thread(principal_from_claims, claims)
    else:
        p = await asyncio.to_thread(get_principal, request)
    stream_claims = {"sid": str(p.session_id), "sub": str(p.user.id), "org": str(p.org_id)}

    async def stream():  # noqa: ANN202
        pubsub = get_redis().pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(channel(p.org_id))
            yield {"event": "ready", "data": json.dumps({"org": str(p.org_id)})}
            idle = 0
            next_check = time.monotonic() + SESSION_RECHECK_SECONDS
            while not await request.is_disconnected():
                if time.monotonic() >= next_check:
                    try:
                        await asyncio.to_thread(principal_from_claims, stream_claims)
                    except HTTPException:
                        yield {"event": "session.ended", "data": "{}"}
                        return
                    next_check = time.monotonic() + SESSION_RECHECK_SECONDS
                msg = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
                if msg and msg.get("type") == "message":
                    payload = json.loads(msg["data"])
                    yield {"event": payload["event"], "data": json.dumps(payload["data"])}
                    idle = 0
                else:
                    idle += 1
                    if idle >= 15:
                        yield {"event": "ping", "data": "{}"}
                        idle = 0
        except Exception:  # noqa: BLE001 - Redis unavailable: client falls back to polling
            yield {"event": "degraded", "data": json.dumps({"reason": "event bus unavailable"})}
        finally:
            pubsub.close()

    return EventSourceResponse(stream())


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    checks = {}
    s = new_session()
    try:
        s.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
    finally:
        s.close()
    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"degraded: {type(exc).__name__}"
    healthy = checks["database"] == "ok"
    return JSONResponse({"status": "ok" if healthy else "error", "checks": checks, "ai_mode": mode_label()},
                        status_code=200 if healthy else 503)
