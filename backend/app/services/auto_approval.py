"""Configurable auto-approval: let a clean invoice skip human review.

An administrator sets one policy per organization (a ceiling on the amount, all suppliers or a chosen few). After
every reconciliation run :func:`apply` asks :func:`evaluate` whether the invoice qualifies. The decision is plain
deterministic code over the stored reconciliation result: no model takes part, and a model could not change it.

What auto-approval does and does not do
---------------------------------------
* An invoice that qualifies is marked (``auto_approved_at`` plus a snapshot of the policy and the values used) and
  an ``invoice.auto_approved`` audit entry records the same. It stays ``reconciled``: the normal payment-approval
  steps (one approver, or two above the dual-approval threshold) are created exactly as for any reconciled invoice
  and are decided by people. Nothing here approves a payment, schedules one or records one.
* An invoice is **never** auto-approved when any of these holds, whatever the policy says (these rules are not
  settings): the match is not a three-way match; the run has any finding at all, even an informational one; a person
  has already edited the invoice; extraction produced a warning or a missing field; the supplier is unknown, blocked,
  has a bank change awaiting review or a bank-change payment hold that has not run out; the amount is unknown, not
  positive, cannot be converted to the base currency or is above the policy ceiling.
* A later run that no longer qualifies withdraws the marker and records ``invoice.auto_approval_revoked``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AutoApprovalPolicy, Invoice, Organization, Supplier, User
from app.services import audit, fx, supplier_banking

#: Documented assumption behind the dashboard's "hours saved" estimate. It is not measured: it is the time we assume
#: a reviewer spends on one invoice that qualified for auto-approval (open it, find the order and the goods receipt,
#: compare lines and prices, record the result). The figure is returned by the API so the page can show it next to
#: the estimate, and docs/api.md repeats it.
MINUTES_SAVED_PER_INVOICE = 6
#: Window of the dashboard KPI, in days (invoices received in the last N days).
KPI_WINDOW_DAYS = 30
MAX_AMOUNT_LIMIT = Decimal("1000000000")
ACTOR_LABEL = "auto-approval-policy"
#: Reason codes, in the order they are checked. They are stable API values (the audit log and the tests use them).
REASONS = ("policy_disabled", "not_reconciled", "archived", "not_three_way", "has_findings", "human_edited",
           "extraction_warnings", "no_supplier", "supplier_not_allowed", "supplier_blocked", "bank_change_pending",
           "payment_hold_active", "amount_unknown", "amount_not_positive", "over_max_amount")


class PolicyIn(BaseModel):
    enabled: bool
    max_amount: Decimal = Field(ge=0, le=MAX_AMOUNT_LIMIT, decimal_places=2)
    supplier_scope: str = Field(pattern="^(all|selected)$")
    supplier_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)


def get_policy(session: Session, org_id: uuid.UUID) -> AutoApprovalPolicy | None:
    return session.scalar(select(AutoApprovalPolicy).where(AutoApprovalPolicy.organization_id == org_id))


def public_policy(policy: AutoApprovalPolicy | None) -> dict:
    """The policy as the API shows it. An organization that never set one has a disabled policy (it has no row)."""
    if policy is None:
        return {"enabled": False, "max_amount": "0.00", "supplier_scope": "selected", "supplier_ids": [], "version": 0,
                "updated_at": None, "updated_by": None}
    return {"enabled": policy.enabled, "max_amount": f"{policy.max_amount:.2f}", "supplier_scope": policy.supplier_scope,
            "supplier_ids": sorted(policy.supplier_ids or []), "version": policy.version,
            "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
            "updated_by": str(policy.updated_by) if policy.updated_by else None}


def save_policy(session: Session, org: Organization, user: User, body: PolicyIn) -> dict:
    """Create or change the organization's policy. Every change is audited with its before and after state."""
    ids = sorted({str(i) for i in body.supplier_ids})
    if body.supplier_scope == "all":
        ids = []
    elif ids:
        found = set(map(str, session.scalars(select(Supplier.id).where(
            Supplier.organization_id == org.id, Supplier.id.in_([uuid.UUID(i) for i in ids])))))
        if found != set(ids):
            raise HTTPException(422, "Choose suppliers of this organization only.")
    if body.enabled and body.supplier_scope == "selected" and not ids:
        raise HTTPException(422, "Choose at least one supplier, or allow all suppliers, to turn auto-approval on.")
    policy = session.scalar(select(AutoApprovalPolicy).where(AutoApprovalPolicy.organization_id == org.id).with_for_update())
    before = public_policy(policy)
    if policy is None:
        policy = AutoApprovalPolicy(organization_id=org.id, version=0)
        session.add(policy)
    policy.enabled, policy.max_amount = body.enabled, body.max_amount
    policy.supplier_scope, policy.supplier_ids = body.supplier_scope, ids
    policy.updated_by = user.id
    policy.version = (policy.version or 0) + 1
    policy.updated_at = datetime.now(UTC)
    session.flush()
    after = public_policy(policy)
    audit.record(session, org_id=org.id, action="org.auto_approval_policy_updated", entity_type="organization",
                 entity_id=org.id, actor_id=user.id, actor_label=user.email, before=before, after=after,
                 meta={"policy_id": str(policy.id), "version": policy.version})
    return after


@dataclass
class Decision:
    approved: bool
    reasons: list[str] = field(default_factory=list)  # why not (codes from REASONS); empty when approved
    values: dict = field(default_factory=dict)         # the policy and invoice values the decision used


def evaluate(session: Session, org: Organization, inv: Invoice, policy: AutoApprovalPolicy | None, *,
             mode: str, finding_types: list[str], rates: fx.Rates | None = None) -> Decision:
    """Decide whether ``inv`` qualifies. ``finding_types`` is every finding of the latest run (any severity).
    Pure apart from reading the supplier row: it changes nothing."""
    reasons: list[str] = []
    values: dict = {"mode": mode, "findings": len(finding_types), "invoice_status": inv.status,
                    "currency": inv.currency, "total": f"{inv.total:.2f}" if inv.total is not None else None}
    if policy is None or not policy.enabled:
        return Decision(False, ["policy_disabled"], values)
    values.update({"policy_id": str(policy.id), "policy_version": policy.version,
                   "max_amount": f"{policy.max_amount:.2f}", "base_currency": fx.BASE,
                   "supplier_scope": policy.supplier_scope})
    if inv.status != "reconciled":
        reasons.append("not_reconciled")
    if inv.archived_at is not None:
        reasons.append("archived")
    if mode != "three_way":
        reasons.append("not_three_way")
    if finding_types:
        reasons.append("has_findings")
        values["finding_types"] = sorted(set(finding_types))
    if inv.reviewed_by is not None:
        reasons.append("human_edited")
    if inv.missing_fields or any(w.get("severity") in ("warning", "critical") for w in (inv.validation_warnings or [])):
        reasons.append("extraction_warnings")

    supplier = None
    if inv.supplier_id is not None:
        # a shared lock: a bank change cannot be confirmed between this check and the end of the transaction
        supplier = session.scalar(select(Supplier).where(Supplier.id == inv.supplier_id,
                                                         Supplier.organization_id == inv.organization_id)
                                  .with_for_update(read=True).execution_options(populate_existing=True))
    if supplier is None:
        reasons.append("no_supplier")
    else:
        values["supplier_id"] = str(supplier.id)
        if policy.supplier_scope == "selected" and str(supplier.id) not in set(policy.supplier_ids or []):
            reasons.append("supplier_not_allowed")
        if supplier.status == "blocked":
            reasons.append("supplier_blocked")
        if supplier.pending_bank_account is not None:
            reasons.append("bank_change_pending")
        elif supplier_banking.held(supplier):
            reasons.append("payment_hold_active")
            values["hold_until"] = supplier.bank_hold_until.isoformat() if supplier.bank_hold_until else None

    total_base = fx.to_base(inv.total, inv.currency or fx.BASE, rates)
    values["total_base"] = f"{total_base:.2f}" if total_base is not None else None
    if total_base is None:
        reasons.append("amount_unknown")
    elif total_base <= 0:
        reasons.append("amount_not_positive")
    elif total_base > policy.max_amount:
        reasons.append("over_max_amount")
    return Decision(not reasons, reasons, values)


def _core(snapshot: dict | None) -> tuple:
    """What makes two approvals the same decision (a re-run with identical inputs is not a new decision)."""
    s = snapshot or {}
    return (s.get("policy_id"), s.get("policy_version"), s.get("supplier_id"), s.get("total_base"), s.get("max_amount"))


def apply(session: Session, org: Organization, inv: Invoice, *, run_id: uuid.UUID, mode: str,
          finding_types: list[str]) -> Decision:
    """The decision hook, called by ``reconcile_invoice`` after every run once status and approval steps are set.
    Marks or unmarks the invoice and audits the change. It never changes the invoice status or approval steps."""
    if inv.status in ("approved", "rejected") and inv.auto_approved_at is None:
        return Decision(False, ["not_reconciled"], {})
    policy = get_policy(session, org.id)
    decision = evaluate(session, org, inv, policy, mode=mode, finding_types=finding_types, rates=fx.current_rates())
    if inv.status in ("approved", "rejected"):
        return decision  # a finished invoice keeps the record of how it got here
    if decision.approved:
        snapshot = {**decision.values, "decided_at": datetime.now(UTC).isoformat(), "run_id": str(run_id),
                    "rules": ["three_way_match", "zero_findings", "no_human_edit", "no_payment_hold_or_bank_change"]}
        if inv.auto_approved_at is None or _core(inv.auto_approval) != _core(snapshot):
            before = {"auto_approved": inv.auto_approved_at is not None}
            inv.auto_approved_at, inv.auto_approval = datetime.now(UTC), audit.to_jsonable(snapshot)
            session.flush()
            audit.record(session, org_id=org.id, action="invoice.auto_approved", entity_type="invoice", entity_id=inv.id,
                         actor_type="system", actor_label=ACTOR_LABEL, before=before,
                         after={"status": inv.status, "auto_approved": True, "policy": decision.values},
                         meta={"run_id": str(run_id), "policy_id": str(policy.id), "policy_version": policy.version,
                               "next_step": "payment approval by people; nothing is paid automatically"})
    elif inv.auto_approved_at is not None:
        was = inv.auto_approval
        inv.auto_approved_at, inv.auto_approval = None, None
        session.flush()
        audit.record(session, org_id=org.id, action="invoice.auto_approval_revoked", entity_type="invoice",
                     entity_id=inv.id, actor_type="system", actor_label=ACTOR_LABEL,
                     before={"auto_approved": True, "policy": was},
                     after={"auto_approved": False, "status": inv.status, "reasons": decision.reasons},
                     meta={"run_id": str(run_id)})
    return decision


def kpis(session: Session, org_id: uuid.UUID, today: datetime | None = None) -> dict:
    """Touchless rate and estimated time saved over the last ``KPI_WINDOW_DAYS`` days (by the day the invoice was received).

    * touchless rate = invoices that stand auto-approved / invoices that finished processing in the window
      (failed, still-processing, voided and credit-note documents are not counted);
    * hours saved = auto-approved invoices x ``MINUTES_SAVED_PER_INVOICE`` / 60: an estimate from an assumption,
      not a measurement.
    """
    since = (today or datetime.now(UTC)) - timedelta(days=KPI_WINDOW_DAYS)
    base = (Invoice.organization_id == org_id, Invoice.created_at >= since,
            Invoice.status.notin_(("processing", "failed", "voided", "credit_note")))
    processed = session.scalar(select(func.count()).select_from(Invoice).where(*base)) or 0
    auto = session.scalar(select(func.count()).select_from(Invoice).where(*base, Invoice.auto_approved_at.isnot(None))) or 0
    minutes = auto * MINUTES_SAVED_PER_INVOICE
    return {"touchless_rate": round(auto / processed, 3) if processed else None, "auto_approved": auto,
            "processed": processed, "hours_saved": round(minutes / 60, 1), "minutes_per_invoice": MINUTES_SAVED_PER_INVOICE,
            "window_days": KPI_WINDOW_DAYS}

