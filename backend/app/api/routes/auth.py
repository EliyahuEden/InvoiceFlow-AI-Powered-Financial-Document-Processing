from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import COOKIE_NAME, REFRESH_COOKIE, Principal, get_principal
from app.core.config import get_settings
from app.core.db import new_session, set_session_org
from app.core.security import create_access_token, verify_password
from app.models import AuthSession, Membership, Organization, User
from app.services import audit, auth_sessions
from app.services.llm.provider import mode_label
from app.services.ratelimit import check_rate_limit
from app.services.rbac import permissions_for

router = APIRouter(prefix="/api/auth", tags=["auth"])
CSRF_HEADER = ("x-requested-with", "invoiceflow")


class LoginIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(..., min_length=1, max_length=200)
    organization_slug: str | None = None


class SwitchIn(BaseModel):
    organization_id: uuid.UUID


def _set_cookies(resp: Response, access: str, refresh: str | None = None) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, access, httponly=True, secure=s.cookie_secure, samesite="lax",
                    max_age=s.access_token_minutes * 60, path="/")
    if refresh is not None:
        resp.set_cookie(REFRESH_COOKIE, refresh, httponly=True, secure=s.cookie_secure, samesite="lax",
                        max_age=s.session_max_days * 86400, path="/")  # the server enforces the real limits


def _clear_cookies(resp: Response) -> None:
    resp.delete_cookie(COOKIE_NAME, path="/")
    resp.delete_cookie(REFRESH_COOKIE, path="/")


def _require_csrf(request: Request) -> None:
    if request.headers.get(CSRF_HEADER[0]) != CSRF_HEADER[1]:
        raise HTTPException(403, "Missing CSRF header")


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _me_payload(user: User, org: Organization, role: str, orgs: list[dict]) -> dict:
    return {
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name, "locale": user.locale},
        "organization": {"id": str(org.id), "name": org.name, "slug": org.slug,
                         "name_en": org.settings.get("display_name_en"),
                         "base_currency": org.settings.get("base_currency", "ILS")},
        "role": role, "permissions": permissions_for(role), "organizations": orgs,
        "ai_mode": mode_label(),
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    ip = _ip(request)
    check_rate_limit(f"login:{ip}", get_settings().rate_limit_login_per_minute)
    check_rate_limit(f"login:{body.email.lower()}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.email == body.email.lower())).first()
        if not user or not user.is_active or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")
        memberships = s.scalars(select(Membership).where(Membership.user_id == user.id)).all()
        if not memberships:
            raise HTTPException(403, "User has no organization")
        m = memberships[0]
        if body.organization_slug:
            for mm in memberships:
                if s.get(Organization, mm.organization_id).slug == body.organization_slug:
                    m = mm
        org = s.get(Organization, m.organization_id)
        issued = auth_sessions.create(s, user_id=user.id, org_id=org.id, ip=ip,
                                      user_agent=request.headers.get("user-agent"))
        token = create_access_token(user.id, org.id, m.role.value, issued.session.id)
        orgs = [{"id": str(mm.organization_id), "name": s.get(Organization, mm.organization_id).name,
                 "role": mm.role.value} for mm in memberships]
        set_session_org(s, org.id)
        audit.record(s, org_id=org.id, action="auth.login", entity_type="user", entity_id=user.id,
                     actor_id=user.id, actor_label=user.email, meta={"ip": ip, "session_id": str(issued.session.id)})
        s.commit()
        _set_cookies(response, token, issued.refresh_token)
        return {"access_token": token, "token_type": "bearer", "expires_in": get_settings().access_token_minutes * 60,
                **_me_payload(user, org, m.role.value, orgs)}
    finally:
        s.close()


@router.post("/refresh")
def refresh(request: Request, response: Response) -> dict:
    """Rotate the refresh token and issue a new access token for the same session."""
    _require_csrf(request)
    ip = _ip(request)
    check_rate_limit(f"refresh:{ip}", get_settings().rate_limit_refresh_per_minute)
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(401, "No session")
    s = new_session()
    try:
        try:
            issued = auth_sessions.rotate(s, raw)
        except auth_sessions.RefreshError as err:
            if err.reason == "reuse" and err.session is not None:
                set_session_org(s, err.session.organization_id)
                audit.record(s, org_id=err.session.organization_id, action="auth.refresh_reuse", entity_type="user",
                             entity_id=err.session.user_id, actor_id=err.session.user_id, actor_label="system",
                             meta={"ip": ip, "session_id": str(err.session.id)})
            s.commit()
            raise HTTPException(401, "Session expired or revoked", headers={"set-cookie": _expired_cookies()}) from err
        sess = issued.session
        user = s.get(User, sess.user_id)
        m = s.scalars(select(Membership).where(Membership.user_id == sess.user_id,
                                               Membership.organization_id == sess.organization_id)).first()
        if not user or not user.is_active or not m:
            auth_sessions.revoke(s, sess.id, "membership_invalid")
            s.commit()
            raise HTTPException(401, "Membership no longer valid", headers={"set-cookie": _expired_cookies()})
        token = create_access_token(user.id, sess.organization_id, m.role.value, sess.id)
        s.commit()
        _set_cookies(response, token, issued.refresh_token)
        return {"access_token": token, "token_type": "bearer", "expires_in": get_settings().access_token_minutes * 60}
    finally:
        s.close()


def _expired_cookies() -> str:
    # HTTPException responses drop cookies set on the injected Response, so expire them here.
    return f"{REFRESH_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=lax"


def _session_id_from_request(request: Request) -> uuid.UUID | None:
    """The caller's session: from a validly signed access token (even if expired), else from
    a refresh token whose secret matches."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get(COOKIE_NAME)
    if token:
        s = get_settings()
        try:
            claims = jwt.decode(token, s.jwt_secret.get_secret_value(), algorithms=[s.jwt_algorithm],
                                options={"verify_exp": False})
            return uuid.UUID(claims["sid"])
        except (jwt.PyJWTError, KeyError, ValueError):
            pass
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return None
    db = new_session()
    try:
        sess = auth_sessions.match(db, raw)
        return sess.id if sess else None
    finally:
        db.close()


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    _require_csrf(request)
    sid = _session_id_from_request(request)
    if sid:
        s = new_session()
        try:
            auth_sessions.revoke(s, sid, "logout")
            s.commit()
        finally:
            s.close()
    _clear_cookies(response)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, p: Principal = Depends(get_principal)) -> dict:
    """Sign out of every browser and client of this user."""
    _require_csrf(request)
    s = new_session()
    try:
        n = auth_sessions.revoke_all(s, p.user.id)
        set_session_org(s, p.org_id)
        audit.record(s, org_id=p.org_id, action="auth.logout_all", entity_type="user", entity_id=p.user.id,
                     actor_id=p.user.id, actor_label=p.user.email, meta={"sessions_revoked": n})
        s.commit()
    finally:
        s.close()
    _clear_cookies(response)
    return {"ok": True, "sessions_revoked": n}


@router.get("/me")
def me(p: Principal = Depends(get_principal)) -> dict:
    s = new_session()
    try:
        ms = s.scalars(select(Membership).where(Membership.user_id == p.user.id)).all()
        orgs = [{"id": str(m.organization_id), "name": s.get(Organization, m.organization_id).name,
                 "role": m.role.value} for m in ms]
    finally:
        s.close()
    return _me_payload(p.user, p.org, p.role.value, orgs)


@router.post("/switch-organization")
def switch_org(body: SwitchIn, response: Response, p: Principal = Depends(get_principal)) -> dict:
    s = new_session()
    try:
        m = s.scalars(select(Membership).where(Membership.user_id == p.user.id,
                                               Membership.organization_id == body.organization_id)).first()
        if not m:
            raise HTTPException(403, "Not a member of that organization")
        sess = s.get(AuthSession, p.session_id)
        sess.organization_id = m.organization_id  # later refreshes stay in the chosen organization
        token = create_access_token(p.user.id, m.organization_id, m.role.value, sess.id)
        s.commit()
    finally:
        s.close()
    _set_cookies(response, token)
    return {"ok": True}
