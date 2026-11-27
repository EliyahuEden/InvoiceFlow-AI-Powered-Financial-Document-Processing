from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, Timestamps, UUIDPk


class InboundEmail(UUIDPk, Timestamps, TenantScoped, Base):
    """One message received at an organization's forwarding address (under RLS like every tenant table).

    The unique (organization_id, message_id) is the dedupe: a message that is polled twice, redelivered by a mail
    provider or posted to the webhook again is recognised and ignored. ``details`` holds the outcome of each
    attachment, never its content.
    """

    __tablename__ = "inbound_emails"
    __table_args__ = (UniqueConstraint("organization_id", "message_id", name="uq_inbound_emails_org_message"),
                      Index("ix_inbound_emails_org_received", "organization_id", "created_at"))
    message_id: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(10))  # imap | webhook
    sender: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(500))
    recipient: Mapped[str] = mapped_column(String(320))  # the forwarding address the message was sent to
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the message's own Date header
    # accepted (every attachment taken) | partial (some taken) | rejected (nothing taken)
    status: Mapped[str] = mapped_column(String(10), default="rejected")
    attachments_total: Mapped[int] = mapped_column(Integer, default=0)
    attachments_accepted: Mapped[int] = mapped_column(Integer, default=0)
    # [{"filename": ..., "status": "accepted|duplicate|rejected|skipped", "reason": ..., "invoice_id": ...}]
    details: Mapped[list] = mapped_column(JSONB, default=list)
