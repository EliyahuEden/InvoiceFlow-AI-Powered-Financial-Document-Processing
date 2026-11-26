from __future__ import annotations

import uuid

import jwt
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import null, select

from app.api.deps import COOKIE_NAME, REFRESH_COOKIE, Principal, get_principal, requires_mfa_enrollment
from app.core.client_ip import client_ip
from app.core.config import get_settings
from app.core.db import new_session, set_session_org
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AuthSession, Membership, Organization, Role, User
from app.services import audit, auth_sessions, auth_tokens, mfa
from app.services import email as mail
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
    #: the version of the terms of use, privacy policy and data-processing agreement the person agreed to
    accepted_legal_version: str = Field(..., min_length=1, max_length=40)


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
    return client_ip(request)  # the real client behind the web proxy, so users do not share one rate-limit bucket


def _me_payload(user: User, org: Organization, role: str, orgs: list[dict]) -> dict:
    verification_required = user.email_verified_at is None
    enrollment_required = requires_mfa_enrollment(user, org)
    locked = enrollment_required or verification_required  # the gates allow only the step that unlocks the account
    return {
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name, "locale": user.locale},
        "organization": {"id": str(org.id), "name": org.name, "slug": org.slug,
                         "name_en": org.settings.get("display_name_en"),
                         "base_currency": org.settings.get("base_currency", "ILS")},
        "role": role, "permissions": [] if locked else permissions_for(role), "organizations": orgs,
        "mfa_enrollment_required": enrollment_required, "two_factor": user.totp_enabled_at is not None,
        "email_verification_required": verification_required,
        "ai_mode": mode_label(),
        # a private "Try the demo" workspace and when it is deleted (null for real businesses)
        "sandbox": ({"expires_at": org.settings["sandbox"].get("expires_at")} if org.settings.get("sandbox") else None),
    }


def _open_session(s, user: User, organization_slug: str | None, request: Request, response: Response,  # noqa: ANN001
                  meta: dict | None = None) -> dict:
    """Create a session for a user whose identity is proven (password, and the code when two-factor is on)."""
    ip = _ip(request)
    memberships = s.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    if not memberships:
        raise HTTPException(403, "User has no organization")
    m = memberships[0]
    if organization_slug:
        for mm in memberships:
            if s.get(Organization, mm.organization_id).slug == organization_slug:
                m = mm
    org = s.get(Organization, m.organization_id)
    issued = auth_sessions.create(s, user_id=user.id, org_id=org.id, ip=ip, user_agent=request.headers.get("user-agent"))
    token = create_access_token(user.id, org.id, m.role.value, issued.session.id)
    orgs = [{"id": str(mm.organization_id), "name": s.get(Organization, mm.organization_id).name,
             "role": mm.role.value} for mm in memberships]
    set_session_org(s, org.id)
    audit.record(s, org_id=org.id, action="auth.login", entity_type="user", entity_id=user.id,
                 actor_id=user.id, actor_label=user.email,
                 meta={"ip": ip, "session_id": str(issued.session.id), **(meta or {})})
    s.commit()
    _set_cookies(response, token, issued.refresh_token)
    return {"access_token": token, "token_type": "bearer", "expires_in": get_settings().access_token_minutes * 60,
            **_me_payload(user, org, m.role.value, orgs)}


class DemoIn(BaseModel):
    locale: str = Field("he", pattern="^(he|en)$")


@router.post("/demo", status_code=201)
def try_demo(body: DemoIn, request: Request, response: Response) -> dict:
    """"Try the demo": a private copy of the demo workspace for this visitor, signed in, deleted after a day. Nobody
    else sees what the visitor uploads or decides there."""
    from app.services import sandbox

    s_cfg = get_settings()
    if not s_cfg.demo_sandbox_enabled:
        raise HTTPException(403, "The demo is not available on this installation.")
    _require_csrf(request)
    check_rate_limit(f"demo:{_ip(request)}", s_cfg.rate_limit_demo_per_day, window_seconds=86400)
    try:
        user, _org = sandbox.create(body.locale)
    except sandbox.SandboxUnavailable:
        raise HTTPException(503, "The demo is being prepared. Please try again in a few minutes.") from None
    s = new_session()
    try:
        visitor = s.get(User, user.id)
        return _open_session(s, visitor, None, request, response, meta={"via": "try_demo"})
    finally:
        s.close()


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    ip = _ip(request)
    check_rate_limit(f"login:{ip}", get_settings().rate_limit_login_per_minute)
    check_rate_limit(f"login:{body.email.lower()}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.email == body.email.lower()).with_for_update()).first()
        if not user or not user.is_active or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")
        if user.totp_enabled_at is not None:
            # the password was right, but it is only half: no session until the code (POST /login/verify)
            return {"mfa_required": True, "mfa_token": mfa.challenge_token(user.id, body.organization_slug),
                    "expires_in": mfa.CHALLENGE_MINUTES * 60}
        return _open_session(s, user, body.organization_slug, request, response)
    finally:
        s.close()


class VerifyIn(BaseModel):
    mfa_token: str = Field(..., min_length=10, max_length=2000)
    code: str | None = Field(None, max_length=12)
    recovery_code: str | None = Field(None, max_length=20)


def _check_second_factor(user: User, code: str | None, recovery_code: str | None) -> str | None:
    """Consumes a valid code (records its step) or recovery code (removes it). Returns how, or None."""
    if code:
        secret = mfa.decrypt(user.totp_secret_enc or "")
        step = mfa.verify(secret, code, user.totp_last_step) if secret else None
        if step is not None:
            user.totp_last_step = step
            return "totp"
    if recovery_code:
        h = mfa.hash_code(recovery_code)
        if h in (user.recovery_codes or []):
            user.recovery_codes = [c for c in user.recovery_codes if c != h]
            return "recovery_code"
    return None


@router.post("/login/verify")
def login_verify(body: VerifyIn, request: Request, response: Response) -> dict:
    """Second step of sign-in: the challenge from /login plus an authenticator code or a recovery code."""
    _require_csrf(request)
    claims = mfa.read_challenge(body.mfa_token)
    if claims is None:
        raise HTTPException(401, "The sign-in step expired. Enter your password again.")
    cfg = get_settings()
    check_rate_limit(f"mfa:{claims['sub']}", cfg.rate_limit_mfa_per_5min, window_seconds=300)
    check_rate_limit(f"mfa-ip:{_ip(request)}", cfg.rate_limit_login_per_minute * 2)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.id == uuid.UUID(claims["sub"])).with_for_update()).first()
        if not user or not user.is_active or user.totp_enabled_at is None:
            raise HTTPException(401, "The sign-in step expired. Enter your password again.")
        how = _check_second_factor(user, body.code, body.recovery_code)
        if how is None:
            s.rollback()
            raise HTTPException(401, "The code is not correct.")
        return _open_session(s, user, claims.get("org_slug"), request, response,
                             meta={"second_factor": how, "recovery_codes_left": len(user.recovery_codes or [])})
    finally:
        s.close()


def _slug(name: str) -> str:
    import re
    import secrets

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    return f"{base}-{secrets.token_hex(3)}"


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response, background: BackgroundTasks) -> dict:
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
    from app.core.legal import LEGAL_VERSION

    if body.accepted_legal_version != LEGAL_VERSION:
        raise HTTPException(400, "Please accept the current terms of use, privacy policy and data-processing agreement.")
    s = new_session()
    try:
        if s.scalars(select(User).where(User.email == email)).first():
            raise HTTPException(409, "An account with this email already exists. Please sign in instead.")
        settings = copy.deepcopy(DEFAULT_ORG_SETTINGS)
        settings.update({"tax_id": body.tax_id, "base_currency": "ILS"})
        org = Organization(name=body.company_name.strip(), slug=_slug(body.company_name), settings=settings)
        user = User(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password),
                    locale=body.locale)
        if s_cfg.email_enabled:  # without a mail server a link could never arrive, so the address is taken as given
            user.email_verified_at = null()  # a plain None would let the column default mark it verified
        s.add_all([org, user])
        s.flush()
        s.add(Membership(user_id=user.id, organization_id=org.id, role=Role.ADMIN))
        issued = auth_sessions.create(s, user_id=user.id, org_id=org.id, ip=ip, user_agent=request.headers.get("user-agent"))
        token = create_access_token(user.id, org.id, Role.ADMIN.value, issued.session.id)
        set_session_org(s, org.id)
        audit.record(s, org_id=org.id, action="org.created", entity_type="organization", entity_id=org.id,
                     actor_id=user.id, actor_label=user.email, after={"name": org.name})
        # evidence of consent: who agreed, to which version, when (the audit entry is timestamped and hash-chained)
        audit.record(s, org_id=org.id, action="legal.accepted", entity_type="user", entity_id=user.id,
                     actor_id=user.id, actor_label=user.email,
                     meta={"version": LEGAL_VERSION, "documents": ["terms", "privacy", "dpa"]})
        verify_token = (auth_tokens.issue(s, user_id=user.id, purpose=auth_tokens.EMAIL_VERIFY, org_id=org.id,
                                          ttl=timedelta(hours=s_cfg.email_verify_ttl_hours))
                        if user.email_verified_at is None else None)
        s.commit()
        if verify_token:
            background.add_task(mail.send, mail.verify_email(user.email, user.full_name, verify_token, user.locale))
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
        auth_tokens.revoke_all(s, user.id, purposes=(auth_tokens.PASSWORD_RESET,))  # an emailed link must not outlive it
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


class ForgotIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")


class ResetIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=12, max_length=200)


@router.get("/options")
def options() -> dict:
    """Public switches the sign-in pages need (no secrets)."""
    s = get_settings()
    return {"email_enabled": s.email_enabled, "signup_enabled": s.signup_enabled}


@router.post("/forgot-password", status_code=202)
def forgot_password(body: ForgotIn, request: Request, background: BackgroundTasks) -> dict:
    """Email a single-use reset link. The answer is the same whether or not the address has an account, and the
    email is sent after the response, so neither the body nor the timing reveals who is registered."""
    _require_csrf(request)
    cfg = get_settings()
    email = body.email.strip().lower()
    check_rate_limit(f"pwreset:{email}", cfg.rate_limit_password_reset_per_hour, window_seconds=3600)
    check_rate_limit(f"pwreset-ip:{_ip(request)}", cfg.rate_limit_password_reset_per_hour * 5, window_seconds=3600)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.email == email, User.is_active.is_(True))).first()
        if user is not None:
            token = auth_tokens.issue(s, user_id=user.id, purpose=auth_tokens.PASSWORD_RESET,
                                      ttl=timedelta(minutes=cfg.password_reset_ttl_minutes))
            s.commit()
            background.add_task(mail.send, mail.password_reset(user.email, user.full_name, token, user.locale))
    finally:
        s.close()
    return {"ok": True, "detail": "If this address has an account, a reset link is on its way."}


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request) -> dict:
    """Set a new password from an emailed link (a reset or an invitation). Every signed-in device is signed out."""
    _require_csrf(request)
    check_rate_limit(f"pwreset-use:{_ip(request)}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        token = auth_tokens.consume(s, body.token)
        user = s.get(User, token.user_id) if token else None
        if token is None or user is None or not user.is_active:
            raise HTTPException(400, "This link is invalid or has expired. Ask for a new one.")
        user.password_hash = hash_password(body.password)
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
        auth_tokens.revoke_all(s, user.id)
        signed_out = auth_sessions.revoke_all(s, user.id, "password_reset")
        org_id = token.organization_id or s.scalar(select(Membership.organization_id)
                                                   .where(Membership.user_id == user.id).limit(1))
        if org_id is not None:
            set_session_org(s, org_id)
            audit.record(s, org_id=org_id, action="auth.invite_accepted" if token.purpose == auth_tokens.INVITE
                         else "auth.password_reset", entity_type="user", entity_id=user.id, actor_id=user.id,
                         actor_label=user.email, meta={"sessions_signed_out": signed_out})
        s.commit()
        return {"ok": True, "email": user.email}
    finally:
        s.close()


class EmailTokenIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


@router.post("/verify-email")
def verify_email(body: EmailTokenIn, request: Request) -> dict:
    """Confirm an address from the emailed link. Works without being signed in (the link may open on another device)."""
    _require_csrf(request)
    check_rate_limit(f"verify-use:{_ip(request)}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        token = auth_tokens.consume(s, body.token, purposes=(auth_tokens.EMAIL_VERIFY,))
        user = s.get(User, token.user_id) if token else None
        if token is None or user is None or not user.is_active:
            raise HTTPException(400, "This link is invalid or has expired. Sign in to get a new one.")
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
            org_id = token.organization_id or s.scalar(select(Membership.organization_id)
                                                       .where(Membership.user_id == user.id).limit(1))
            if org_id is not None:
                set_session_org(s, org_id)
                audit.record(s, org_id=org_id, action="auth.email_verified", entity_type="user", entity_id=user.id,
                             actor_id=user.id, actor_label=user.email)
        s.commit()
        return {"ok": True, "email": user.email}
    finally:
        s.close()


@router.post("/verify-email/resend", status_code=202)
def resend_verification(request: Request, background: BackgroundTasks, p: Principal = Depends(get_principal)) -> dict:
    """Send a fresh confirmation link to the signed-in account (any earlier link stops working)."""
    _require_csrf(request)
    cfg = get_settings()
    if p.user.email_verified_at is not None:
        return {"ok": True, "already_verified": True}
    check_rate_limit(f"verify-resend:{p.user.id}", cfg.rate_limit_verify_resend_per_hour, window_seconds=3600)
    s = new_session()
    try:
        raw = auth_tokens.issue(s, user_id=p.user.id, purpose=auth_tokens.EMAIL_VERIFY, org_id=p.org_id,
                                ttl=timedelta(hours=cfg.email_verify_ttl_hours))
        s.commit()
    finally:
        s.close()
    background.add_task(mail.send, mail.verify_email(p.user.email, p.user.full_name, raw, p.user.locale))
    return {"ok": True}


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


# ------------------------------------------------------------------ two-factor sign-in
class CodeIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=12)


class DisableIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)
    code: str | None = Field(None, max_length=12)
    recovery_code: str | None = Field(None, max_length=20)


def _audit_user(s, p: Principal, action: str, meta: dict | None = None) -> None:  # noqa: ANN001
    set_session_org(s, p.org_id)
    audit.record(s, org_id=p.org_id, action=action, entity_type="user", entity_id=p.user.id,
                 actor_id=p.user.id, actor_label=p.user.email, meta=meta)


@router.get("/2fa")
def two_factor_status(p: Principal = Depends(get_principal)) -> dict:
    return {"enabled": p.user.totp_enabled_at is not None,
            "enabled_at": p.user.totp_enabled_at.isoformat() if p.user.totp_enabled_at else None,
            "recovery_codes_left": len(p.user.recovery_codes or []) if p.user.totp_enabled_at else 0}


@router.post("/2fa/setup")
def two_factor_setup(request: Request, p: Principal = Depends(get_principal)) -> dict:
    """A new secret to scan. It does nothing until confirmed with a code (/2fa/enable)."""
    _require_csrf(request)
    secret = mfa.new_secret()
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.id == p.user.id).with_for_update()).one()
        if user.totp_enabled_at is not None:
            raise HTTPException(409, "Two-factor sign-in is already on. Turn it off first to set up a new app.")
        user.totp_secret_enc, user.totp_last_step = mfa.encrypt(secret), None
        s.commit()
    finally:
        s.close()
    uri = mfa.otpauth_uri(secret, p.user.email)
    return {"secret": secret, "otpauth_uri": uri, "qr": mfa.qr_data_uri(uri)}


@router.post("/2fa/enable")
def two_factor_enable(body: CodeIn, request: Request, p: Principal = Depends(get_principal)) -> dict:
    _require_csrf(request)
    check_rate_limit(f"mfa-setup:{p.user.id}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.id == p.user.id).with_for_update()).one()
        if user.totp_enabled_at is not None:
            raise HTTPException(409, "Two-factor sign-in is already on.")
        secret = mfa.decrypt(user.totp_secret_enc or "")
        step = mfa.verify(secret, body.code, None) if secret else None
        if step is None:
            raise HTTPException(422, "The code is not correct. Check the time on your phone and try again.")
        codes = mfa.new_recovery_codes()
        user.totp_last_step, user.totp_enabled_at = step, datetime.now(UTC)
        user.recovery_codes = [mfa.hash_code(c) for c in codes]
        auth_sessions.revoke_all(s, user.id, "two_factor_enabled", keep=p.session_id)
        _audit_user(s, p, "auth.2fa_enabled")
        s.commit()
        return {"enabled": True, "recovery_codes": codes}
    finally:
        s.close()


@router.post("/2fa/disable")
def two_factor_disable(body: DisableIn, request: Request, p: Principal = Depends(get_principal)) -> dict:
    _require_csrf(request)
    check_rate_limit(f"mfa-disable:{p.user.id}", get_settings().rate_limit_mfa_per_5min, window_seconds=300)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.id == p.user.id).with_for_update()).one()
        if user.totp_enabled_at is None:
            return {"enabled": False}
        if not verify_password(body.password, user.password_hash):
            raise HTTPException(403, "The password is not correct.")
        if _check_second_factor(user, body.code, body.recovery_code) is None:
            raise HTTPException(403, "The code is not correct.")
        user.totp_secret_enc = user.totp_enabled_at = user.totp_last_step = None
        user.recovery_codes = []
        _audit_user(s, p, "auth.2fa_disabled")
        s.commit()
        return {"enabled": False}
    finally:
        s.close()


@router.post("/2fa/recovery-codes")
def two_factor_new_recovery_codes(body: CodeIn, request: Request, p: Principal = Depends(get_principal)) -> dict:
    """Replaces all recovery codes; the old ones stop working."""
    _require_csrf(request)
    check_rate_limit(f"mfa-setup:{p.user.id}", get_settings().rate_limit_login_per_minute)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.id == p.user.id).with_for_update()).one()
        if user.totp_enabled_at is None:
            raise HTTPException(409, "Two-factor sign-in is off.")
        if _check_second_factor(user, body.code, None) is None:
            raise HTTPException(403, "The code is not correct.")
        codes = mfa.new_recovery_codes()
        user.recovery_codes = [mfa.hash_code(c) for c in codes]
        _audit_user(s, p, "auth.2fa_recovery_codes_replaced")
        s.commit()
        return {"recovery_codes": codes}
    finally:
        s.close()
