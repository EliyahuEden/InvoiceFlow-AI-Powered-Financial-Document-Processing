from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk


class Role(str, enum.Enum):
    ADMIN = "admin"
    PROCUREMENT_MANAGER = "procurement_manager"
    FINANCE_REVIEWER = "finance_reviewer"
    READ_ONLY = "read_only"


DEFAULT_ORG_SETTINGS: dict = {
    "base_currency": "ILS",
    "default_locale": "he",
    # Reconciliation tolerances (configurable business rules, not hard-coded law).
    "tolerances": {
        "price_abs": "0.05",       # currency units per unit
        "price_pct": "1.0",        # percent of PO unit price
        "quantity_abs": "0",       # units
        "total_abs": "1.00",       # currency units on header totals
        "line_total_abs": "0.05",
        "duplicate_window_days": 60,
        "description_match_min": "0.35",
        "description_ambiguity_margin": "0.08",
    },
    # Approval policy: invoices above this total need a second approver.
    "approval": {"dual_approval_threshold": "20000.00"},
}


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=lambda: dict(DEFAULT_ORG_SETTINGS))

    memberships: Mapped[list[Membership]] = relationship(back_populates="organization")


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(5), default="he")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


class Membership(UUIDPk, Timestamps, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="role", values_callable=lambda e: [x.value for x in e]))

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")
