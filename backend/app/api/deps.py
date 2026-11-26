"""Authentication, tenant binding and RBAC dependencies."""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import lock_workspace, new_session
from app.core.security import decode_access_token
from app.models import Membership, Organization, Role, User
from app.services import auth_sessions
from app.services.rbac import Perm, has_perm

COOKIE_NAME = "invoiceflow_session"
REFRESH_COOKIE = "invoiceflow_refresh"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
#: what an account whose email is not confirmed yet may still do
VERIFICATION_ROUTES = {("GET", "/api/auth/me"), ("POST", "/api/auth/verify-email/resend"), ("POST", "/api/auth/logout")}
ENROLLMENT_ROUTES = {
    ("GET", "/api/auth/me"), ("GET", "/api/auth/2fa"),
    ("POST", "/api/auth/2fa/setup"), ("POST", "/api/auth/2fa/enable"),
    ("POST", "/api/auth/logout"),
}


def requires_mfa_enrollment(user: User, org: Organization) -> bool:
    return user.totp_enabled_at is None and org.settings.get("security", {}).get("require_2fa") is True


@dataclass
class Principal:
    user: User
    org: Organization
    role: Role
    session_id: uuid.UUID | None = None

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id


def _token(request: Request) -> tuple[str | None, bool]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:], False
    return request.cookies.get(COOKIE_NAME), True


def get_principal(request: Request) -> Principal:
    token, from_cookie = _token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    # CSRF defence for cookie sessions: unsafe methods need a custom header, which a
    # cross-site form cannot send (and SameSite=Lax cookies are already not sent).
    if from_cookie and request.method in UNSAFE and request.headers.get("x-requested-with") != "invoiceflow":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF header")
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from exc
    route = (request.method, request.scope.get("path"))
    return principal_from_claims(claims, allow_enrollment=route in ENROLLMENT_ROUTES, allow_unverified=route in VERIFICATION_ROUTES)


def principal_from_claims(claims: dict, *, allow_enrollment: bool = False, allow_unverified: bool = False) -> Principal:
    s = new_session()
    try:
        # The server-side session must still be active: logout, "sign out everywhere"
        # and expiry revoke tokens immediately, not when the JWT expires.
        sess = auth_sessions.get_active(s, claims.get("sid") or "")
        if sess is None or str(sess.user_id) != claims.get("sub"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or revoked")
        user = s.get(User, uuid.UUID(claims["sub"]))
        m = s.scalars(select(Membership).where(Membership.user_id == uuid.UUID(claims["sub"]),
                                               Membership.organization_id == uuid.UUID(claims["org"]))).first()
        if not user or not user.is_active or not m:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Membership no longer valid")
        org = s.get(Organization, m.organization_id)
        if org is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Membership no longer valid")
        if not allow_unverified and user.email_verified_at is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Email verification is required")
        if not allow_enrollment and requires_mfa_enrollment(user, org):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Two-factor enrollment is required")
        # Role is read from the database on every request (not trusted from the token),
        # so revoking or downgrading a membership takes effect immediately.
        return Principal(user=user, org=org, role=m.role, session_id=sess.id)
    finally:
        s.close()


def get_db(principal: Principal = Depends(get_principal)) -> Iterator[Session]:
    """Tenant-bound session: RLS restricts every query to the caller's organization."""
    session = new_session(principal.org_id)
    try:
        lock_workspace(session, principal.org_id)
        if session.get(Organization, principal.org_id) is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Membership no longer valid")
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require(perm: Perm):  # noqa: ANN201
    def checker(principal: Principal = Depends(get_principal)) -> Principal:
        if not has_perm(principal.role, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {perm.value}")
        return principal

    return checker


def dec(v: Decimal | None) -> str | None:
    return None if v is None else format(v.normalize() if v == v.to_integral() else v, "f")


def money(v: Decimal | None) -> str | None:
    return None if v is None else f"{v:.2f}"


def price(v: Decimal | None) -> str | None:
    """A unit price with every stored digit (at least two decimals): rounding it to cents would
    change extended amounts when a correction sends the line back (audit FIN-04)."""
    if v is None:
        return None
    s = format(v.normalize(), "f")
    whole, _, frac = s.partition(".")
    return f"{whole}.{frac.ljust(2, '0')}"


MAX_PAGE = 100_000


def page_params(page: int = 1, page_size: int = 25) -> tuple[int, int]:
    if page > MAX_PAGE:  # an offset past this is never a real request and overflows the database (fuzz finding)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"page must be at most {MAX_PAGE}")
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return page, page_size


def paginated(items: list[Any], total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}
