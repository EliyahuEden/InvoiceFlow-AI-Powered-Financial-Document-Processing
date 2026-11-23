"""Role-based access control. The single source of truth for who may do what.

Enforced in the backend for every endpoint *and* every agent tool. The frontend only
uses the same matrix (via /api/auth/me) to hide controls; it is never trusted.
"""
from __future__ import annotations

from enum import Enum

from app.models.tenancy import Role


class Perm(str, Enum):
    INVOICE_READ = "invoice:read"
    INVOICE_UPLOAD = "invoice:upload"
    INVOICE_EDIT = "invoice:edit"
    RECONCILE_RUN = "reconcile:run"
    EXCEPTION_COMMENT = "exception:comment"
    EXCEPTION_DECIDE = "exception:decide"
    APPROVAL_DECIDE = "approval:decide"
    APPROVAL_FINAL = "approval:final"  # second step for high-value invoices
    MASTERDATA_READ = "masterdata:read"
    MASTERDATA_WRITE = "masterdata:write"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    AGENT_RUN = "agent:run"
    AUDIT_READ = "audit:read"
    OBSERVABILITY_READ = "observability:read"
    ORG_MANAGE = "org:manage"


_ALL = set(Perm)
_READ = {Perm.INVOICE_READ, Perm.MASTERDATA_READ, Perm.KNOWLEDGE_READ, Perm.OBSERVABILITY_READ}

ROLE_PERMISSIONS: dict[Role, set[Perm]] = {
    Role.ADMIN: _ALL,
    # Procurement decides cases and may override with a justification (owner's decision, 2026-11-23), but never
    # approves payment: that stays with finance, and the uploader of an invoice can never approve its payment.
    Role.PROCUREMENT_MANAGER: _READ
    | {
        Perm.INVOICE_UPLOAD, Perm.INVOICE_EDIT, Perm.RECONCILE_RUN, Perm.EXCEPTION_COMMENT, Perm.EXCEPTION_DECIDE,
        Perm.MASTERDATA_WRITE, Perm.KNOWLEDGE_WRITE, Perm.AGENT_RUN, Perm.AUDIT_READ,
    },
    Role.FINANCE_REVIEWER: _READ
    | {
        Perm.INVOICE_UPLOAD, Perm.INVOICE_EDIT, Perm.RECONCILE_RUN, Perm.EXCEPTION_COMMENT,
        Perm.EXCEPTION_DECIDE, Perm.APPROVAL_DECIDE, Perm.AGENT_RUN, Perm.AUDIT_READ,
    },
    Role.READ_ONLY: set(_READ),
}


def has_perm(role: Role | str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS[Role(role)]


def permissions_for(role: Role | str) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS[Role(role)])
