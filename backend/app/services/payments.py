"""Track payments approved and performed by people outside InvoiceFlow."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, Supplier, User
from app.services import audit, events, supplier_banking


class PaymentIn(BaseModel):
    action: Literal["schedule", "clear_schedule", "record_paid"]
    payment_date: date | None = Field(None, alias="date")
    reference: str | None = Field(None, max_length=120)


def payment_state(invoice: Invoice) -> dict:
    return {"status": "paid" if invoice.payment_paid_on else "scheduled" if invoice.payment_scheduled_for else "unscheduled",
            "scheduled_for": invoice.payment_scheduled_for.isoformat() if invoice.payment_scheduled_for else None,
            "paid_on": invoice.payment_paid_on.isoformat() if invoice.payment_paid_on else None,
            "reference": invoice.payment_reference}


def update_payment(db: Session, invoice: Invoice, user: User, body: PaymentIn) -> dict:
    """The invoice is locked by the caller. Bank changes share the supplier lock."""
    if invoice.status != "approved":
        raise HTTPException(409, "The invoice must be approved for payment first")
    today = date.today()
    reference = (body.reference or "").strip()
    if invoice.payment_paid_on:
        if body.action == "record_paid" and invoice.payment_paid_on == body.payment_date and invoice.payment_reference == reference:
            return payment_state(invoice)
        raise HTTPException(409, "The payment has already been recorded")
    before = payment_state(invoice)
    if body.action == "clear_schedule":
        invoice.payment_scheduled_for = None
    else:
        if body.payment_date is None:
            raise HTTPException(422, "Provide a payment date")
        supplier = db.scalar(select(Supplier).where(Supplier.id == invoice.supplier_id,
                                                    Supplier.organization_id == invoice.organization_id).with_for_update())
        if supplier and supplier_banking.held(supplier):
            raise HTTPException(409, "Payments are on hold for this supplier's bank change")
        if body.action == "schedule":
            if body.payment_date < today:
                raise HTTPException(422, "Choose today or a future date for the scheduled payment")
            invoice.payment_scheduled_for = body.payment_date
        else:
            if body.payment_date > today or not reference:
                raise HTTPException(422, "Provide a completed payment date and an external reference")
            invoice.payment_paid_on = body.payment_date
            invoice.payment_reference = reference
    after = payment_state(invoice)
    if before != after:
        audit.record(db, org_id=invoice.organization_id, action=f"invoice.payment_{body.action}", entity_type="invoice",
                     entity_id=invoice.id, actor_id=user.id, actor_label=user.email, before=before, after=after)
        events.after_commit(db, invoice.organization_id, "invoice.updated", {"invoice_id": str(invoice.id)})
    return after
