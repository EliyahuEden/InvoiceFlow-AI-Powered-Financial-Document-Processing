from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import COOKIE_NAME, REFRESH_COOKIE, Principal, get_principal
from app.core.config import get_settings
from app.core.db import new_session, set_session_org
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AuthSession, Membership, Organization, Role, User
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


class SignupIn(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=200)
    full_name: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=12, max_length=200)
    tax_id: str | None = Field(None, pattern=r"^\d{9}$", description="the business's own company/VAT number")
    locale: str = Field("he", pattern="^(he|en)$")


class PasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=12, max_length=200)


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


def _slug(name: str) -> str:
    import re
    import secrets

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    return f"{base}-{secrets.token_hex(3)}"


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response) -> dict:
    """Create a business: an isolated organization (row-level security keeps its data apart) and its first
    administrator, then sign in. The administrator adds the rest of the team from Settings."""
    import copy

    from app.models.tenancy import DEFAULT_ORG_SETTINGS

    s_cfg = get_settings()
    if not s_cfg.signup_enabled:
        raise HTTPException(403, "Sign-up is disabled on this installation.")
    ip = _ip(request)
    check_rate_limit(f"signup:{ip}", s_cfg.rate_limit_signup_per_hour, window_seconds=3600)
    email = body.email.lower().strip()
    s = new_session()
    try:
        if s.scalars(select(User).where(User.email == email)).first():
            raise HTTPException(409, "An account with this email already exists. Please sign in instead.")
        settings = copy.deepcopy(DEFAULT_ORG_SETTINGS)
        settings.update({"tax_id": body.tax_id, "base_currency": "ILS"})
        org = Organization(name=body.company_name.strip(), slug=_slug(body.company_name), settings=settings)
        user = User(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password),
                    locale=body.locale)
        s.add_all([org, user])
        s.flush()
        s.add(Membership(user_id=user.id, organization_id=org.id, role=Role.ADMIN))
        issued = auth_sessions.create(s, user_id=user.id, org_id=org.id, ip=ip, user_agent=request.headers.get("user-agent"))
        token = create_access_token(user.id, org.id, Role.ADMIN.value, issued.session.id)
        set_session_org(s, org.id)
        audit.record(s, org_id=org.id, action="org.created", entity_type="organization", entity_id=org.id,
                     actor_id=user.id, actor_label=user.email, after={"name": org.name})
        s.commit()
        _set_cookies(response, token, issued.refresh_token)
        return {"access_token": token, "token_type": "bearer", "expires_in": s_cfg.access_token_minutes * 60,
                **_me_payload(user, org, Role.ADMIN.value, [{"id": str(org.id), "name": org.name, "role": "admin"}])}
    finally:
        s.close()


@router.post("/password")
def change_password(body: PasswordIn, request: Request, p: Principal = Depends(get_principal)) -> dict:
    """Change your own password; every other signed-in device is signed out."""
    _require_csrf(request)
    check_rate_limit(f"password:{p.user.id}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        user = s.get(User, p.user.id)
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(400, "The current password is not correct.")
        user.password_hash = hash_password(body.new_password)
        current = _session_id_from_request(request)
        others = [a for a in auth_sessions.active_sessions(s, user.id) if a.id != current]
        for a in others:
            auth_sessions.revoke(s, a.id, "password_changed")
        set_session_org(s, p.org_id)
        audit.record(s, org_id=p.org_id, action="auth.password_changed", entity_type="user", entity_id=user.id,
                     actor_id=user.id, actor_label=user.email, meta={"other_sessions_signed_out": len(others)})
        s.commit()
        return {"ok": True, "other_sessions_signed_out": len(others)}
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


@router.get("/sessions")
def list_sessions(request: Request, p: Principal = Depends(get_principal)) -> dict:
    """The caller's own signed-in browsers and clients (never other users')."""
    current = _session_id_from_request(request)
    s = new_session()
    try:
        rows = sorted(auth_sessions.active_sessions(s, p.user.id),
                      key=lambda r: r.last_used_at or r.created_at, reverse=True)
        return {"items": [{
            "id": str(r.id), "current": r.id == current, "created_at": r.created_at.isoformat(),
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "expires_at": min(r.expires_at, r.absolute_expires_at).isoformat(),
            "ip": r.ip, "user_agent": r.user_agent,
        } for r in rows]}
    finally:
        s.close()


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: uuid.UUID, request: Request, p: Principal = Depends(get_principal)) -> dict:
    """Sign out one of the caller's own sessions (another browser, a lost laptop)."""
    _require_csrf(request)
    s = new_session()
    try:
        if session_id not in {r.id for r in auth_sessions.active_sessions(s, p.user.id)}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        auth_sessions.revoke(s, session_id, "revoked_by_user")
        set_session_org(s, p.org_id)
        audit.record(s, org_id=p.org_id, action="auth.session_revoked", entity_type="user", entity_id=p.user.id,
                     actor_id=p.user.id, actor_label=p.user.email, meta={"session_id": str(session_id)})
        s.commit()
    finally:
        s.close()
    return {"ok": True}


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
