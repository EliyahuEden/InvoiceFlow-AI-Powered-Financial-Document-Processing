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

from app.core.db import new_session
from app.core.security import decode_access_token
from app.models import Membership, Organization, Role, User
from app.services.rbac import Perm, has_perm

COOKIE_NAME = "invoiceflow_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Principal:
    user: User
    org: Organization
    role: Role

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
    s = new_session()
    try:
        user = s.get(User, uuid.UUID(claims["sub"]))
        m = s.scalars(select(Membership).where(Membership.user_id == uuid.UUID(claims["sub"]),
                                               Membership.organization_id == uuid.UUID(claims["org"]))).first()
        if not user or not user.is_active or not m:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Membership no longer valid")
        org = s.get(Organization, m.organization_id)
        # Role is read from the database on every request (not trusted from the token),
        # so revoking or downgrading a membership takes effect immediately.
        return Principal(user=user, org=org, role=m.role)
    finally:
        s.close()


def get_db(principal: Principal = Depends(get_principal)) -> Iterator[Session]:
    """Tenant-bound session: RLS restricts every query to the caller's organization."""
    session = new_session(principal.org_id)
    try:
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


def page_params(page: int = 1, page_size: int = 25) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return page, page_size


def paginated(items: list[Any], total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}
