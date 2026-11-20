from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, Timestamps, UUIDPk


class ReconciliationRun(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "reconciliation_runs"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(10))  # two_way | three_way
    engine_version: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str] = mapped_column(String(20))  # matched | discrepancies | blocked
    tolerances: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)  # full deterministic trace (line matches, checks)
    triggered_by: Mapped[str] = mapped_column(String(20), default="system")  # system | user | agent


class Discrepancy(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "discrepancies"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(10))  # info | warning | critical
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    po_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expected: Mapped[str | None] = mapped_column(String(100))
    actual: Mapped[str | None] = mapped_column(String(100))
    difference: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved | waived


class ExceptionCase(UUIDPk, Timestamps, TenantScoped, Base):
    """A review case for a human. Created by the system or proposed (drafted) by the agent."""

    __tablename__ = "exceptions"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    # draft | open | pending_info | approved | rejected | resolved
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    discrepancy_types: Mapped[list] = mapped_column(JSONB, default=list)
    proposed_action: Mapped[str | None] = mapped_column(String(60))
    proposed_action_detail: Mapped[str | None] = mapped_column(Text)
    # AI-generated investigation summary (clearly labelled as AI output in UI and API).
    ai_summary: Mapped[dict | None] = mapped_column(JSONB)
    created_by_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision: Mapped[str | None] = mapped_column(String(20))  # approve | reject | request_info
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    comments: Mapped[list[ExceptionComment]] = relationship(
        back_populates="exception", order_by="ExceptionComment.created_at", cascade="all, delete-orphan"
    )


class ExceptionComment(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "exception_comments"
    exception_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exceptions.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="note")  # note | info_request | decision

    exception: Mapped[ExceptionCase] = relationship(back_populates="comments")


class Approval(UUIDPk, Timestamps, TenantScoped, Base):
    """Payment-approval step for an invoice. The AI can never create an approved row."""

    __tablename__ = "approvals"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[int] = mapped_column(Integer, default=1)
    required_role: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)


class AgentRun(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "agent_runs"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[str] = mapped_column(String(100), unique=True)
    # queued | running | awaiting_approval | completed | failed
    status: Mapped[str] = mapped_column(String(30), default="queued")
    mode: Mapped[str] = mapped_column(String(40))  # llm:<model> | offline-deterministic
    prompt_version: Mapped[str] = mapped_column(String(20))
    steps: Mapped[list] = mapped_column(JSONB, default=list)  # tool-call trace
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class AICall(UUIDPk, Timestamps, TenantScoped, Base):
    """Observability record for every model invocation (LLM, embedding, rerank, OCR)."""

    __tablename__ = "ai_calls"
    kind: Mapped[str] = mapped_column(String(30), index=True)  # extraction | rag_answer | agent | embedding | ocr
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    workflow: Mapped[str | None] = mapped_column(String(50))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))  # ok | error | invalid_output
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class Job(UUIDPk, Timestamps, Base):
    """Durable background job (PostgreSQL queue, claimed with FOR UPDATE SKIP LOCKED).

    Not under RLS because the worker claims jobs across tenants; every handler then
    opens a tenant-bound session using ``organization_id``.
    """

    __tablename__ = "jobs"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|succeeded|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str | None] = mapped_column(String(300))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)


class AuditLog(UUIDPk, TenantScoped, Base):
    """Append-only, hash-chained audit trail. The app DB role has INSERT+SELECT only."""

    __tablename__ = "audit_logs"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor_type: Mapped[str] = mapped_column(String(10))  # user | system | agent
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_label: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
