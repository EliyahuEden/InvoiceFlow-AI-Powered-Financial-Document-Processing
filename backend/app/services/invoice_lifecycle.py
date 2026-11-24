"""Preserve invoice evidence while changing how it participates in the workflow."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AgentRun, Approval, Discrepancy, ExceptionCase, Invoice, User
from app.services import audit, events


class LifecycleIn(BaseModel):
    action: Literal["void", "archive", "restore", "link_credit"]
    reason: str = Field(..., min_length=1, max_length=1000)
    original_invoice_id: uuid.UUID | None = None


def state(invoice: Invoice) -> dict:
    return {"status": invoice.status, "archived_at": invoice.archived_at.isoformat() if invoice.archived_at else None,
            "credit_for_invoice_id": str(invoice.credit_for_invoice_id) if invoice.credit_for_invoice_id else None}


def apply(db: Session, invoice: Invoice, user: User, body: LifecycleIn, original: Invoice | None) -> dict:
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(422, "A reason is required")
    before = state(invoice)
    if body.action == "archive":
        if not invoice.payment_paid_on and invoice.status not in ("voided", "rejected", "credit_note"):
            raise HTTPException(409, "Only completed invoices and credit notes can be archived")
        if invoice.archived_at is None:
            invoice.archived_at = datetime.now(UTC)
    elif body.action == "restore":
        invoice.archived_at = None
    else:
        if invoice.archived_at or invoice.payment_paid_on or invoice.payment_scheduled_for:
            raise HTTPException(409, "Archived or payment-tracked invoices cannot be changed here")
        if invoice.status in ("processing", "voided", "credit_note"):
            raise HTTPException(409, "This invoice is not eligible for the requested action")
        if db.scalar(select(AgentRun.id).where(AgentRun.invoice_id == invoice.id,
                                               AgentRun.status.in_(("queued", "running"))).limit(1)):
            raise HTTPException(409, "Wait for the investigation to finish before changing this invoice")
        if body.action == "link_credit":
            if (original is None or original.id == invoice.id or original.status in ("voided", "credit_note", "processing", "failed")
                    or invoice.status in ("approved", "failed", "rejected") or not invoice.supplier_id or not invoice.currency
                    or original.supplier_id != invoice.supplier_id or original.currency != invoice.currency):
                raise HTTPException(422, "Choose an original invoice from the same supplier and currency")
            invoice.credit_for_invoice_id = original.id
            invoice.status = "credit_note"
        else:
            if db.scalar(select(Invoice.id).where(Invoice.credit_for_invoice_id == invoice.id).limit(1)):
                raise HTTPException(409, "An invoice with linked credit notes cannot be voided")
            invoice.status = "voided"
        db.execute(update(Approval).where(Approval.invoice_id == invoice.id, Approval.status == "pending")
                   .values(status="superseded"))
        db.execute(update(ExceptionCase).where(ExceptionCase.invoice_id == invoice.id,
                                              ExceptionCase.status.in_(("draft", "open", "pending_info", "escalated")))
                   .values(status="resolved"))
        db.execute(update(Discrepancy).where(Discrepancy.invoice_id == invoice.id, Discrepancy.status == "open")
                   .values(status="resolved"))
    after = state(invoice)
    if before != after:
        audit.record(db, org_id=invoice.organization_id, action=f"invoice.{body.action}", entity_type="invoice",
                     entity_id=invoice.id, actor_id=user.id, actor_label=user.email, before=before, after=after,
                     meta={"reason": reason})
        events.after_commit(db, invoice.organization_id, "invoice.updated", {"invoice_id": str(invoice.id)})
    return after
