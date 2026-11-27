from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money, Timestamps, TenantScoped, UUIDPk


class AutoApprovalPolicy(UUIDPk, Timestamps, TenantScoped, Base):
    """The one auto-approval policy of a business (migration 0015). An administrator sets it; the decision itself
    is deterministic code in ``services/auto_approval.py``. A policy never approves or pays anything: it only lets a
    clean invoice skip human review and go straight to the normal payment-approval step.

    The rules "three-way match with zero findings" and "no payment hold or bank change" are not columns on purpose:
    no setting can switch them off."""

    __tablename__ = "auto_approval_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_auto_approval_policies_org"),
        CheckConstraint("max_amount >= 0", name="ck_auto_approval_max_amount"),
        CheckConstraint("supplier_scope IN ('all', 'selected')", name="ck_auto_approval_scope"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # largest invoice total (in the base currency, shekels) that may be auto-approved
    max_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), server_default="0")
    # "all": every recognised supplier; "selected": only the suppliers listed in supplier_ids (an empty list: none)
    supplier_scope: Mapped[str] = mapped_column(String(10), default="selected", server_default="selected")
    supplier_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    # bumped on every change, so an audit entry names the exact policy version that made a decision
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
