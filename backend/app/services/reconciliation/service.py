"""Database adapter around the pure reconciliation engine."""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Approval,
    Discrepancy,
    Document,
    ExceptionCase,
    GoodsReceipt,
    GRLine,
    Invoice,
    Organization,
    PurchaseOrder,
    ReconciliationRun,
    Supplier,
)
from app.services import audit, events
from app.services.reconciliation import engine as E

ACTION_FOR_FINDING = {
    "INCOMPLETE_EXTRACTION": ("correct_extraction", "Correct the missing invoice fields in the extraction review."),
    "DUPLICATE_INVOICE": ("reject_invoice", "Reject the duplicate and notify the supplier."),
    "PRICE_MISMATCH": ("request_credit_note", "Hold payment and request a credit note for the price difference."),
    "QUANTITY_EXCEEDS_RECEIVED": ("request_credit_note", "Pay only for received quantities; request a credit note "
                                                         "or wait for the remaining delivery."),
    "QUANTITY_EXCEEDS_ORDERED": ("request_credit_note", "Request a credit note for the over-billed quantity."),
    "MISSING_GOODS_RECEIPT": ("request_goods_receipt", "Hold payment until the receiving team records a goods receipt."),
    "MISSING_PURCHASE_ORDER": ("request_po", "Ask the requester to raise a retroactive PO or reject the invoice."),
    "AMBIGUOUS_SUPPLIER": ("select_supplier", "A reviewer must confirm which supplier issued the invoice."),
    "UNRECOGNIZED_SUPPLIER": ("onboard_or_reject", "Verify the supplier and onboard it, or reject the invoice."),
    "AMBIGUOUS_DESCRIPTION": ("confirm_line_match", "Confirm which PO line the invoice line refers to."),
    "CURRENCY_MISMATCH": ("request_corrected_invoice", "Request a corrected invoice in the PO currency."),
    "ITEM_NOT_ON_PO": ("request_po_amendment", "Request a PO amendment or reject the extra line."),
    "TOTAL_MISMATCH": ("request_corrected_invoice", "Request a corrected invoice; totals do not add up."),
    "SUBTOTAL_MISMATCH": ("request_corrected_invoice", "Request a corrected invoice; line totals do not add up."),
    "LINE_TOTAL_MISMATCH": ("request_corrected_invoice", "Request a corrected invoice; a line total is wrong."),
    "SUPPLIER_BLOCKED": ("reject_invoice", "Supplier is blocked; reject or escalate."),
    "POSSIBLE_DUPLICATE": ("verify_duplicate", "Verify with the supplier whether this is a re-submission."),
    "SUSPICIOUS_CONTENT": ("manual_review", "Verify the invoice with the supplier through a known channel; the "
                                            "embedded instructions were ignored."),
    "PO_SUPPLIER_MISMATCH": ("request_corrected_invoice", "The referenced PO belongs to another supplier."),
}
PRIORITY_ORDER = list(ACTION_FOR_FINDING)
TITLE = {
    "DUPLICATE_INVOICE": "Duplicate invoice", "PRICE_MISMATCH": "Unit price differs from PO",
    "QUANTITY_EXCEEDS_RECEIVED": "Billed quantity exceeds received", "QUANTITY_EXCEEDS_ORDERED": "Billed quantity exceeds PO",
    "MISSING_GOODS_RECEIPT": "No goods receipt", "MISSING_PURCHASE_ORDER": "No purchase order",
    "AMBIGUOUS_SUPPLIER": "Supplier is ambiguous", "UNRECOGNIZED_SUPPLIER": "Unknown supplier",
    "AMBIGUOUS_DESCRIPTION": "Ambiguous line description", "CURRENCY_MISMATCH": "Currency mismatch",
    "ITEM_NOT_ON_PO": "Item not on PO", "TOTAL_MISMATCH": "Totals do not add up",
    "INCOMPLETE_EXTRACTION": "Extraction incomplete", "SUSPICIOUS_CONTENT": "Suspicious embedded instructions",
    "PO_CLOSED": "PO is closed", "POSSIBLE_DUPLICATE": "Possible duplicate",
}


def primary_finding(types: list[str]) -> str | None:
    for t in PRIORITY_ORDER:
        if t in types:
            return t
    return types[0] if types else None


def build_context(session: Session, org: Organization, inv: Invoice) -> E.Context:
    org_id = org.id
    suppliers = [E.SupplierData(s.id, s.name, s.name_en, list(s.aliases or []), s.tax_id, s.status)
                 for s in session.scalars(select(Supplier).where(Supplier.organization_id == org_id))]
    pos_db = session.scalars(select(PurchaseOrder).where(PurchaseOrder.organization_id == org_id)
                             .options(selectinload(PurchaseOrder.lines))).all()
    pos = [E.POData(p.id, p.po_number, p.supplier_id, p.currency, p.status,
                    [E.POLineData(pl.id, pl.line_no, pl.description, pl.quantity, pl.unit_price, pl.sku) for pl in p.lines])
           for p in pos_db]
    received: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for po_line_id, qty in session.execute(
        select(GRLine.po_line_id, func.sum(GRLine.quantity_received))
        .where(GRLine.organization_id == org_id).group_by(GRLine.po_line_id)
    ):
        received[po_line_id] = qty
    receipt_count = dict(session.execute(
        select(GoodsReceipt.purchase_order_id, func.count()).where(GoodsReceipt.organization_id == org_id)
        .group_by(GoodsReceipt.purchase_order_id)).all())

    priors = session.execute(
        select(Invoice, Document.sha256).outerjoin(Document, Document.id == Invoice.document_id)
        .where(Invoice.organization_id == org_id, Invoice.id != inv.id)
    ).all()
    prior_invoices = [E.PriorInvoice(i.id, i.supplier_id, i.invoice_number, i.invoice_date, i.total, i.status, sha)
                      for i, sha in priors]

    # Quantities billed on earlier, non-duplicate, non-rejected invoices (from their latest run).
    previously: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    earlier = [i for i, _ in priors if i.created_at < inv.created_at and i.status not in ("rejected", "failed")]
    for other in earlier:
        run = session.scalars(select(ReconciliationRun).where(ReconciliationRun.invoice_id == other.id)
                              .order_by(ReconciliationRun.created_at.desc()).limit(1)).first()
        if not run or any(f["type"] == "DUPLICATE_INVOICE" for f in run.result.get("findings", [])):
            continue
        qty_by_line = {ln.line_no: ln.quantity for ln in other.lines}
        for m in run.result.get("line_matches", []):
            if m.get("po_line_id") and qty_by_line.get(m["invoice_line_no"]) is not None:
                previously[uuid.UUID(m["po_line_id"])] += qty_by_line[m["invoice_line_no"]]
    return E.Context(suppliers, pos, dict(received), receipt_count, dict(previously), prior_invoices,
                     E.Tolerances.from_settings(org.settings.get("tolerances", {})))


def to_engine_invoice(inv: Invoice, sha: str | None, confirmed_supplier: bool) -> E.InvoiceData:
    return E.InvoiceData(
        id=inv.id, supplier_name_raw=inv.supplier_name_raw, supplier_tax_id_raw=inv.supplier_tax_id_raw,
        invoice_number=inv.invoice_number, invoice_date=inv.invoice_date, currency=inv.currency,
        po_reference=inv.po_reference, subtotal=inv.subtotal, discount_total=inv.discount_total,
        tax_amount=inv.tax_total, total=inv.total,
        lines=[E.InvLine(ln.id, ln.line_no, ln.description, ln.sku, ln.quantity, ln.unit_price, ln.discount, ln.line_total)
               for ln in inv.lines],
        document_sha256=sha, supplier_id=inv.supplier_id if confirmed_supplier else None,
        security_flags=[snip for w in (inv.validation_warnings or []) if w.get("code") == "SUSPICIOUS_INSTRUCTIONS"
                        for snip in (w.get("snippets") or ["(flagged)"])],
    )


def reconcile_invoice(session: Session, inv: Invoice, *, triggered_by: str = "system", actor_id: uuid.UUID | None = None,
                      mode: str = "three_way") -> ReconciliationRun:
    org = session.get(Organization, inv.organization_id)
    sha = session.scalar(select(Document.sha256).where(Document.id == inv.document_id)) if inv.document_id else None
    confirmed = bool(inv.field_sources.get("_supplier_confirmed")) if inv.field_sources else False
    ctx = build_context(session, org, inv)
    result = E.reconcile(to_engine_invoice(inv, sha, confirmed), ctx, mode=mode)
    data = result.to_dict()

    run = ReconciliationRun(organization_id=org.id, invoice_id=inv.id, mode=mode, engine_version=result.engine_version,
                            outcome=result.outcome, tolerances=audit.to_jsonable(vars(ctx.tolerances)),
                            result=audit.to_jsonable(data), triggered_by=triggered_by)
    session.add(run)
    session.flush()
    for old in session.scalars(select(Discrepancy).where(Discrepancy.invoice_id == inv.id, Discrepancy.status == "open")):
        old.status = "superseded"
    for f in result.findings:
        session.add(Discrepancy(
            organization_id=org.id, invoice_id=inv.id, run_id=run.id, type=f.type, severity=f.severity,
            invoice_line_id=uuid.UUID(f.invoice_line_id) if f.invoice_line_id else None,
            po_line_id=uuid.UUID(f.po_line_id) if f.po_line_id else None,
            expected=f.expected, actual=f.actual, difference=f.difference, message=f.message,
            evidence={**f.evidence, "amount_at_risk": f.amount_at_risk, "invoice_line_no": f.invoice_line_no,
                      "message_key": f.message_key, "params": f.params},
            status="open" if f.severity != "info" else "info",
        ))

    before_status = inv.status
    inv.supplier_id = uuid.UUID(result.supplier_id) if result.supplier_id else (inv.supplier_id if confirmed else None)
    inv.purchase_order_id = uuid.UUID(result.purchase_order_id) if result.purchase_order_id else None
    actionable = [f for f in result.findings if f.severity in ("critical", "warning")]
    if inv.status not in ("approved", "rejected"):
        inv.status = "exception" if actionable else "reconciled"
    session.flush()

    open_exc = session.scalars(select(ExceptionCase).where(
        ExceptionCase.invoice_id == inv.id, ExceptionCase.status.in_(["draft", "open", "pending_info", "escalated"]))).first()
    if actionable:
        types = sorted({f.type for f in actionable}, key=lambda t: PRIORITY_ORDER.index(t) if t in PRIORITY_ORDER else 99)
        main = primary_finding(types)
        action, detail = ACTION_FOR_FINDING.get(main, ("manual_review", "Review the discrepancies manually."))
        if open_exc is None:
            open_exc = ExceptionCase(
                organization_id=org.id, invoice_id=inv.id,
                title=f"{TITLE.get(main, main.replace('_', ' ').title())} — {inv.invoice_number or 'invoice'}",
                status="open", priority=_priority_level(org, inv, actionable),
                discrepancy_types=types, proposed_action=action, proposed_action_detail=detail,
            )
            session.add(open_exc)
            session.flush()
            audit.record(session, org_id=org.id, action="exception.created", entity_type="exception",
                         entity_id=open_exc.id, actor_type="system", actor_label="reconciliation-engine",
                         after={"title": open_exc.title, "types": types, "proposed_action": action},
                         meta={"invoice_id": str(inv.id), "run_id": str(run.id)})
        else:
            open_exc.discrepancy_types = types
            open_exc.proposed_action = open_exc.proposed_action or action
            open_exc.priority = _priority_level(org, inv, actionable)
    elif open_exc is not None:
        open_exc.status = "resolved"
        open_exc.decision_note = "Resolved automatically: re-reconciliation found no discrepancies."
        audit.record(session, org_id=org.id, action="exception.auto_resolved", entity_type="exception",
                     entity_id=open_exc.id, actor_type="system", actor_label="reconciliation-engine")

    if inv.status == "reconciled":
        ensure_approval_steps(session, org, inv)

    audit.record(session, org_id=org.id, action="invoice.reconciled", entity_type="invoice", entity_id=inv.id,
                 actor_type="user" if actor_id else "system", actor_id=actor_id,
                 actor_label=None if actor_id else "reconciliation-engine",
                 before={"status": before_status}, after={"status": inv.status, "outcome": result.outcome,
                                                          "findings": [f.type for f in result.findings]},
                 meta={"run_id": str(run.id), "engine_version": result.engine_version, "mode": mode})
    events.publish(org.id, "invoice.updated", {"invoice_id": str(inv.id), "status": inv.status})
    return run


def ensure_approval_steps(session: Session, org: Organization, inv: Invoice) -> None:
    existing = session.scalars(select(Approval).where(Approval.invoice_id == inv.id)).all()
    if existing:
        return
    session.add(Approval(organization_id=org.id, invoice_id=inv.id, step=1, required_role="finance_reviewer"))
    threshold = Decimal(str(org.settings.get("approval", {}).get("dual_approval_threshold", "20000")))
    if inv.total is not None and inv.total > threshold:
        session.add(Approval(organization_id=org.id, invoice_id=inv.id, step=2, required_role="admin"))
    session.flush()


def _priority_level(org, inv, findings) -> str:  # noqa: ANN001
    """Stored copy of the risk-first level (the queue recomputes it daily for due-date urgency)."""
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from app.api.routes.queue import critical_amount
    from app.services import priority as P

    risk = sum((Decimal(f.amount_at_risk) for f in findings if f.amount_at_risk), Decimal(0))
    inp = P.PriorityInput(exception_id=inv.id, finding_types=[f.type for f in findings], amount_at_risk=risk,
                          due_date=inv.due_date, created_at=datetime.now(UTC), invoice_total=inv.total)
    return P.compute(inp, date.today(), critical_amount(org)).level
