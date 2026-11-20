from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import COOKIE_NAME, Principal, get_principal
from app.core.config import get_settings
from app.core.db import new_session, set_session_org
from app.core.security import create_access_token, verify_password
from app.models import Membership, Organization, User
from app.services import audit
from app.services.llm.provider import mode_label
from app.services.ratelimit import check_rate_limit
from app.services.rbac import permissions_for

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(..., min_length=1, max_length=200)
    organization_slug: str | None = None


class SwitchIn(BaseModel):
    organization_id: uuid.UUID


def _set_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, token, httponly=True, secure=s.cookie_secure, samesite="lax",
                    max_age=s.access_token_minutes * 60, path="/")


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
    ip = request.client.host if request.client else "unknown"
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
        token = create_access_token(user.id, org.id, m.role.value)
        orgs = [{"id": str(mm.organization_id), "name": s.get(Organization, mm.organization_id).name,
                 "role": mm.role.value} for mm in memberships]
        set_session_org(s, org.id)
        audit.record(s, org_id=org.id, action="auth.login", entity_type="user", entity_id=user.id,
                     actor_id=user.id, actor_label=user.email, meta={"ip": ip})
        s.commit()
        _set_cookie(response, token)
        return {"access_token": token, "token_type": "bearer", **_me_payload(user, org, m.role.value, orgs)}
    finally:
        s.close()


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
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
        token = create_access_token(p.user.id, m.organization_id, m.role.value)
    finally:
        s.close()
    _set_cookie(response, token)
    return {"ok": True}
