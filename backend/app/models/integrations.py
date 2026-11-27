"""Machine access to an organization: API keys and outbound webhooks."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, Timestamps, UUIDPk


class ApiKey(UUIDPk, Timestamps, TenantScoped, Base):
    """A named organization API key. Only the SHA-256 of the secret is stored; the secret is shown once at creation."""

    __tablename__ = "api_keys"
    name: Mapped[str] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(String(12))  # read | read_write
    prefix: Mapped[str] = mapped_column(String(16))  # the first characters of the secret, to recognise a key in a list
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)


class WebhookEndpoint(UUIDPk, Timestamps, TenantScoped, Base):
    """An HTTPS URL that receives signed event notifications. The signing secret is stored encrypted (it is needed to sign)."""

    __tablename__ = "webhook_endpoints"
    url: Mapped[str] = mapped_column(String(2000))
    description: Mapped[str | None] = mapped_column(String(200))
    events: Mapped[list] = mapped_column(JSONB, default=list)
    secret_enc: Mapped[str] = mapped_column(Text)
    secret_hint: Mapped[str] = mapped_column(String(12))  # the last characters of the secret, to tell rotations apart
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)


class WebhookDelivery(UUIDPk, Timestamps, TenantScoped, Base):
    """One event for one endpoint, and everything that happened trying to deliver it."""

    __tablename__ = "webhook_deliveries"
    endpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | retrying | succeeded | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(500))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_log: Mapped[list] = mapped_column(JSONB, default=list)
