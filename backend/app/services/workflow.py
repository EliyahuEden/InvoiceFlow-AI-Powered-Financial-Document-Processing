"""Human-in-the-loop decisions: extraction corrections, exception decisions, payment approvals.

All state transitions are deterministic code guarded by RBAC; each one writes an
audit record in the same database transaction as the change itself.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import D
from app.models import AgentRun, Approval, Document, ExceptionCase, ExceptionComment, Invoice, InvoiceLine, Organization, User
from app.services import audit, events, jobs
from app.services.rbac import Perm, has_perm
from app.services.reconciliation.service import ensure_approval_steps, reconcile_invoice

EDITABLE_HEADER = {"supplier_name_raw", "supplier_tax_id_raw", "invoice_number", "invoice_date", "due_date", "currency",
                   "po_reference", "payment_terms", "subtotal", "discount_total", "tax_total", "tax_rate", "total",
                   "allocation_number"}
MONEY = {"subtotal", "discount_total", "tax_total", "tax_rate", "total"}

# Outcome of approving an exception's proposed action (deterministic mapping).
APPROVE_EFFECT = {
    "reject_invoice": "rejected",
    "accept_variance": "reconciled",
    "request_credit_note": "on_hold",
    "request_goods_receipt": "on_hold",
    "request_po": "on_hold",
    "request_corrected_invoice": "on_hold",
    "request_po_amendment": "on_hold",
    "select_supplier": "needs_review",
    "confirm_line_match": "needs_review",
    "verify_duplicate": "on_hold",
    "onboard_or_reject": "on_hold",
    "manual_review": "on_hold",
    "correct_extraction": "needs_review",
}


def _snapshot(inv: Invoice) -> dict:
    return {f: getattr(inv, f) for f in sorted(EDITABLE_HEADER)} | {"supplier_id": inv.supplier_id}


def correct_invoice(session: Session, inv: Invoice, user: User, header: dict, lines: list[dict] | None,
                    supplier_id: uuid.UUID | None, reason: str | None) -> Invoice:
    if inv.status in ("approved", "rejected", "voided", "credit_note") or inv.archived_at:
        raise HTTPException(409, "Invoice is already finalized and can no longer be edited.")
    before = _snapshot(inv)
    before_lines = [{"line_no": ln.line_no, "description": ln.description, "sku": ln.sku, "quantity": ln.quantity,
                     "unit_price": ln.unit_price, "line_total": ln.line_total} for ln in inv.lines]
    sources = dict(inv.field_sources or {})
    for key, value in header.items():
        if key not in EDITABLE_HEADER:
            raise HTTPException(422, f"Field {key} is not editable.")
        if key in MONEY and value not in (None, ""):
            value = D(str(value))
        setattr(inv, key, value if value != "" else None)
        sources[key] = {**sources.get(key, {}), "corrected_by": str(user.id), "corrected_at": datetime.now(UTC).isoformat()}
    if supplier_id:
        inv.supplier_id = supplier_id
        sources["_supplier_confirmed"] = {"by": str(user.id), "supplier_id": str(supplier_id)}
    inv.field_sources = sources
    if lines is not None:
        # Provenance follows the line's identity, not its position (audit FIN-08): deleting row 1 must not
        # hand row 1's highlight to the row that moves up. Rows without an id are new and have no source.
        by_id = {str(ln.id): ln.source for ln in inv.lines}
        by_no = {ln.line_no: ln.source for ln in inv.lines}
        uses_ids = any(ln.get("id") for ln in lines)
        for ln in list(inv.lines):
            session.delete(ln)
        session.flush()
        for i, ln in enumerate(lines, start=1):
            if uses_ids:
                old = by_id.get(str(ln.get("id"))) if ln.get("id") else None
                source = {**old, "corrected_by": str(user.id)} if old is not None else \
                    {"manual": True, "corrected_by": str(user.id)}
            else:  # older clients that send no ids
                source = {**(by_no.get(ln.get("line_no") or i) or {}), "corrected_by": str(user.id)}
            session.add(InvoiceLine(
                organization_id=inv.organization_id, invoice_id=inv.id, line_no=i, sku=ln.get("sku") or None,
                description=ln["description"], quantity=_dec(ln.get("quantity")), unit_price=_dec(ln.get("unit_price")),
                discount=_dec(ln.get("discount")), line_total=_dec(ln.get("line_total")), source=source))
    inv.reviewed_by = user.id
    inv.updated_at = datetime.now(UTC)  # a lines-only edit must still move the revision (TECH-01)
    inv.missing_fields = [f for f in ("supplier_name_raw", "invoice_number", "invoice_date", "total", "currency")
                          if getattr(inv, f) in (None, "")]
    session.flush()
    session.refresh(inv)
    audit.record(session, org_id=inv.organization_id, action="invoice.corrected", entity_type="invoice", entity_id=inv.id,
                 actor_id=user.id, actor_label=user.email, before={**before, "lines": before_lines},
                 after={**_snapshot(inv), "lines": [{"line_no": ln.line_no, "description": ln.description,
                                                     "quantity": ln.quantity, "unit_price": ln.unit_price,
                                                     "line_total": ln.line_total} for ln in inv.lines]},
                 meta={"reason": reason, "changed_fields": sorted(header.keys()) + (["lines"] if lines is not None else [])})
    reconcile_invoice(session, inv, triggered_by="user", actor_id=user.id)
    return inv


def _dec(v) -> Decimal | None:  # noqa: ANN001
    return None if v in (None, "") else D(str(v))


def add_comment(session: Session, exc: ExceptionCase, user: User, body: str, kind: str = "note") -> ExceptionComment:
    c = ExceptionComment(organization_id=exc.organization_id, exception_id=exc.id, author_id=user.id, body=body, kind=kind)
    session.add(c)
    session.flush()
    audit.record(session, org_id=exc.organization_id, action=f"exception.{kind}", entity_type="exception",
                 entity_id=exc.id, actor_id=user.id, actor_label=user.email, after={"body": body[:2000]})
    return c


REQUEST_TARGETS = ("procurement", "supplier")


def escalated_by(session: Session, exc: ExceptionCase) -> uuid.UUID | None:
    rows = session.scalars(select(ExceptionComment.author_id).where(
        ExceptionComment.exception_id == exc.id, ExceptionComment.kind == "escalation")
        .order_by(ExceptionComment.created_at)).all()
    return rows[-1] if rows else None


def decide_exception(session: Session, exc: ExceptionCase, user: User, role: str, decision: str, note: str | None,
                     action_override: str | None = None, target: str | None = None) -> ExceptionCase:
    """Record a reviewer decision. approve / reject close the case; request_info parks it waiting for
    procurement or the supplier; escalate hands it to an administrator. Nothing here pays anything."""
    if decision not in ("approve", "reject", "request_info", "escalate"):
        raise HTTPException(422, "decision must be approve, reject, request_info or escalate")
    if decision in ("approve", "reject", "escalate") and not has_perm(role, Perm.EXCEPTION_DECIDE):
        raise HTTPException(403, "Your role cannot decide exceptions.")
    if decision == "request_info" and not has_perm(role, Perm.EXCEPTION_COMMENT):
        raise HTTPException(403, "Your role cannot request information.")
    inv = session.scalars(select(Invoice).where(Invoice.id == exc.invoice_id, Invoice.organization_id == exc.organization_id)
                          .with_for_update().execution_options(populate_existing=True)).one()
    if role == "procurement_manager" and decision in ("approve", "reject", "escalate"):
        org = session.get(Organization, exc.organization_id)
        if org.settings.get("approval", {}).get("procurement_cannot_decide_own_upload") is True:
            uploader = session.scalar(select(Document.uploaded_by).where(Document.id == inv.document_id))
            if uploader == user.id:
                raise HTTPException(403, "Another reviewer must decide this case because you uploaded the invoice.")
    # Refresh under a row lock so a reviewer with a stale page cannot overwrite another decision.
    exc = session.scalars(select(ExceptionCase).where(ExceptionCase.id == exc.id,
                                                     ExceptionCase.organization_id == exc.organization_id)
                          .with_for_update().execution_options(populate_existing=True)).first()
    if exc is None:
        raise HTTPException(404, "Exception not found")
    if exc.status in ("approved", "rejected", "resolved"):
        raise HTTPException(409, f"Exception is already {exc.status}.")
    if decision in ("reject", "escalate", "request_info") and not (note and note.strip()):
        raise HTTPException(422, "A note is required for this decision.")
    if decision == "request_info" and target not in REQUEST_TARGETS:
        raise HTTPException(422, "Say who must provide the information: procurement or supplier.")
    if exc.status == "escalated":
        # an escalation goes to another authorized reviewer: an administrator who did not escalate it
        if role != "admin" or escalated_by(session, exc) == user.id:
            raise HTTPException(403, "An escalated case is decided by another administrator.")
    before = {"status": exc.status, "invoice_status": inv.status}
    override: dict = {}
    if decision == "approve" and action_override:
        if action_override not in APPROVE_EFFECT:
            raise HTTPException(422, "Unknown action.")
        if action_override != exc.proposed_action:
            # Anyone who may decide cases may override the proposed action, even over blocking findings
            # (audit FIN-06, owner's decision), but only with a written justification, recorded as an override.
            if not (note and note.strip()):
                raise HTTPException(422, "A written justification is required to override the proposed action.")
            override = {"override": True, "overridden_action": exc.proposed_action,
                        "overridden_findings": list(exc.discrepancy_types or [])}
        exc.proposed_action = action_override
    if decision == "request_info":
        exc.status = "pending_info"
        add_comment(session, exc, user, note or "", kind="info_request")
    elif decision == "escalate":
        exc.status = "escalated"
        add_comment(session, exc, user, note or "", kind="escalation")
    else:
        exc.status = "approved" if decision == "approve" else "rejected"
        exc.decision, exc.decision_note = decision, note
        exc.decided_by, exc.decided_at = user.id, datetime.now(UTC)
        if decision == "approve":
            new_status = APPROVE_EFFECT.get(exc.proposed_action or "manual_review", "on_hold")
            inv.status = new_status
            if new_status == "reconciled":
                ensure_approval_steps(session, session.get(Organization, inv.organization_id), inv)
    session.flush()
    audit.record(session, org_id=exc.organization_id, action=f"exception.{decision}", entity_type="exception",
                 entity_id=exc.id, actor_id=user.id, actor_label=user.email, before=before,
                 after={"status": exc.status, "invoice_status": inv.status, "proposed_action": exc.proposed_action},
                 meta={"note": note, "target": target, "ai_summary_present": exc.ai_summary is not None,
                       "ai_recommended": (exc.ai_summary or {}).get("deterministic_action"), **override})
    # Resume the paused agent workflow so its run records the human decision.
    if exc.agent_run_id and decision in ("approve", "reject"):
        run = session.get(AgentRun, exc.agent_run_id)
        if run and run.status == "awaiting_approval":
            jobs.enqueue(session, org_id=exc.organization_id, job_type="agent.resume",
                         payload={"agent_run_id": str(run.id),
                                  "decision": {"decision": decision, "by": user.email, "note": note,
                                               "action": exc.proposed_action}},
                         idempotency_key=f"agent.resume:{run.id}")
    events.after_commit(session, exc.organization_id, "exception.updated", {"exception_id": str(exc.id), "status": exc.status})
    return exc


def decide_approval(session: Session, inv: Invoice, user: User, role: str, decision: str, comment: str | None) -> Approval:
    if decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")
    # Lock the invoice and its active steps so two reviewers cannot act on the same step; re-read under
    # the lock so a stale page sees the committed state (audit FIN-02).
    inv = session.scalars(select(Invoice).where(Invoice.id == inv.id, Invoice.organization_id == inv.organization_id)
                          .with_for_update().execution_options(populate_existing=True)).first()
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    if inv.status != "reconciled":
        raise HTTPException(409, "Only reconciled invoices without open exceptions can be approved for payment.")
    steps = session.scalars(select(Approval).where(Approval.invoice_id == inv.id, Approval.status != "superseded")
                            .order_by(Approval.step).with_for_update()
                            .execution_options(populate_existing=True)).all()
    pending = next((s for s in steps if s.status == "pending"), None)
    if pending is None:
        raise HTTPException(409, "No pending approval step.")
    needed = Perm.APPROVAL_FINAL if pending.step > 1 else Perm.APPROVAL_DECIDE
    if not has_perm(role, needed):
        raise HTTPException(403, f"Step {pending.step} requires the {pending.required_role} role.")
    # Segregation of duties: uploader cannot approve; one person cannot approve two steps.
    uploader = session.scalar(select(Document.uploaded_by).where(Document.id == inv.document_id))
    if uploader == user.id:
        raise HTTPException(403, "Segregation of duties: the uploader of an invoice cannot approve its payment.")
    if any(s.decided_by == user.id for s in steps if s.status == "approved"):
        raise HTTPException(403, "Segregation of duties: a second, different approver is required.")
    pending.status = "approved" if decision == "approve" else "rejected"
    pending.decided_by, pending.decided_at, pending.comment = user.id, datetime.now(UTC), comment
    before = inv.status
    if decision == "reject":
        inv.status = "rejected"
    elif all(s.status == "approved" for s in steps):
        inv.status = "approved"  # approved for payment; payment execution is outside the system and never automated
    session.flush()
    audit.record(session, org_id=inv.organization_id, action=f"approval.{decision}", entity_type="invoice",
                 entity_id=inv.id, actor_id=user.id, actor_label=user.email, before={"status": before},
                 after={"status": inv.status, "step": pending.step}, meta={"comment": comment})
    events.after_commit(session, inv.organization_id, "invoice.updated", {"invoice_id": str(inv.id), "status": inv.status})
    return pending
