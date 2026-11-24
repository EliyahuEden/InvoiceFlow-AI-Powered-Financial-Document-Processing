"""Typed, permission-checked tools for the investigation agent.

Security model:
* The tenant (organization), acting user and role come from the authenticated
  ``ToolContext`` - never from model output. A model cannot widen its own scope.
* Each tool declares the permission it needs; the same RBAC matrix as the API applies.
* Inputs are validated with Pydantic before execution; outputs are plain JSON.
* There is deliberately no tool that approves, rejects, pays or edits financial data.
  ``create_exception_draft`` only attaches an advisory summary to a review case.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ExceptionCase, GoodsReceipt, Invoice, PurchaseOrder, Supplier
from app.services import audit
from app.services.rbac import Perm, has_perm


class ToolPermissionError(PermissionError):
    pass


@dataclass
class ToolContext:
    session: Session
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    role: str
    agent_run_id: uuid.UUID | None = None
    trace: list[dict] = field(default_factory=list)
    # Policies and agreements are read as they stood on this date (the invoice date for investigations); None = today.
    as_of: _date | None = None


# ------------------------------------------------------------------ inputs
class GetInvoiceIn(BaseModel):
    invoice_id: str


class GetSupplierIn(BaseModel):
    supplier_id: str


class FindPOIn(BaseModel):
    supplier_id: str | None = None
    po_number: str | None = None


class GetReceiptsIn(BaseModel):
    purchase_order_id: str


class RunReconIn(BaseModel):
    invoice_id: str
    mode: str = Field("three_way", pattern="^(two_way|three_way)$")


class SearchIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    supplier_id: str | None = None


class QueueIn(BaseModel):
    level: str | None = Field(None, pattern="^(critical|high|normal)$", description="priority level filter")
    status: str | None = Field(None, pattern="^(open|escalated|pending_info)$",
                               description="case status: open, escalated, or pending_info (waiting for information)")
    overdue: bool = Field(False, description="only cases whose invoice is past its due date")
    due_within_days: int | None = Field(None, ge=0, le=90, description="only cases due within this many days")
    supplier: str | None = Field(None, max_length=120, description="supplier name (Hebrew or English), partial")
    finding_type: str | None = Field(None, max_length=60, description="e.g. PRICE_MISMATCH, MISSING_GOODS_RECEIPT")
    limit: int = Field(10, ge=1, le=25)


class EmptyIn(BaseModel):
    pass


class InvoiceSearchIn(BaseModel):
    text: str | None = Field(None, max_length=120, description="invoice number, supplier name or PO number, partial")
    sort: str = Field("newest", pattern="^(newest|oldest|largest)$")
    status: Literal[
        "processing", "needs_review", "exception", "reconciled", "on_hold", "approved", "rejected", "failed", "voided", "credit_note",
    ] | None = Field(
        None, description="Use reconciled for invoices ready for approval and approved for invoices approved for payment.",
    )
    min_total: str | None = Field(None, max_length=20)
    max_total: str | None = Field(None, max_length=20)
    date_from: str | None = Field(None, max_length=10, description="YYYY-MM-DD")
    date_to: str | None = Field(None, max_length=10, description="YYYY-MM-DD")
    limit: int = Field(10, ge=1, le=25)


class GetExceptionIn(BaseModel):
    exception_id: str


class SupplierLookupIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, description="supplier name, alias or tax ID")


class SupplierListIn(BaseModel):
    status: str | None = Field(None, pattern="^(active|blocked|inactive)$")
    sort: str = Field("name", pattern="^(name|open_cases|invoices)$")


class FindingsIn(BaseModel):
    finding_type: str = Field(..., max_length=60, description="e.g. DUPLICATE_INVOICE, PRICE_MISMATCH, "
                              "QUANTITY_EXCEEDS_RECEIVED, MISSING_GOODS_RECEIPT, NOT_AN_INVOICE, CURRENCY_MISMATCH, "
                              "MISSING_ALLOCATION_NUMBER")
    limit: int = Field(15, ge=1, le=50)


class InvoiceRefIn(BaseModel):
    invoice_number: str | None = Field(None, max_length=60)
    invoice_id: str | None = None


class PORefIn(BaseModel):
    po_number: str = Field(..., max_length=60)


class PeriodIn(BaseModel):
    date_from: str | None = Field(None, max_length=10, description="YYYY-MM-DD invoice date")
    date_to: str | None = Field(None, max_length=10, description="YYYY-MM-DD invoice date")


class ActivityIn(BaseModel):
    days: int = Field(7, ge=1, le=90)


class HelpIn(BaseModel):
    topic: str = Field("overview", max_length=40, description="overview, statuses, approve, correct, escalate, "
                       "request_info, priority, matching, roles, shortcuts")


class SpendIn(BaseModel):
    date_from: str | None = Field(None, max_length=10, description="YYYY-MM-DD, invoice date")
    date_to: str | None = Field(None, max_length=10, description="YYYY-MM-DD, invoice date")
    limit: int = Field(10, ge=1, le=25)


class DraftIn(BaseModel):
    invoice_id: str
    summary: dict
    proposed_action: str = Field(..., max_length=60)


def _uuid(v: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(v))
    except ValueError as exc:
        raise ValueError(f"invalid id: {v!r}") from exc


def _dec(v: Any) -> str | None:
    return None if v is None else str(v)


# ------------------------------------------------------------------ implementations
def get_invoice(ctx: ToolContext, inp: GetInvoiceIn) -> dict:
    inv = ctx.session.scalars(select(Invoice).where(Invoice.id == _uuid(inp.invoice_id),
                                                    Invoice.organization_id == ctx.org_id)
                              .options(selectinload(Invoice.lines))).first()
    if inv is None:
        return {"error": "invoice not found"}
    return {
        "id": str(inv.id), "status": inv.status, "invoice_number": inv.invoice_number,
        "supplier_name_printed": inv.supplier_name_raw, "supplier_tax_id_printed": inv.supplier_tax_id_raw,
        "supplier_id": str(inv.supplier_id) if inv.supplier_id else None,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None, "currency": inv.currency,
        "po_reference": inv.po_reference, "subtotal": _dec(inv.subtotal), "tax": _dec(inv.tax_total),
        "total": _dec(inv.total), "payment_terms": inv.payment_terms, "language": inv.language,
        "security_flags": [w for w in inv.validation_warnings if w.get("code") == "SUSPICIOUS_INSTRUCTIONS"],
        "lines": [{"line_no": ln.line_no, "sku": ln.sku, "description": ln.description, "quantity": _dec(ln.quantity),
                   "unit_price": _dec(ln.unit_price), "line_total": _dec(ln.line_total)} for ln in inv.lines],
    }


def get_supplier(ctx: ToolContext, inp: GetSupplierIn) -> dict:
    s = ctx.session.scalars(select(Supplier).where(Supplier.id == _uuid(inp.supplier_id),
                                                   Supplier.organization_id == ctx.org_id)).first()
    if s is None:
        return {"error": "supplier not found"}
    return {"id": str(s.id), "name": s.name, "name_en": s.name_en, "tax_id": s.tax_id, "status": s.status,
            "payment_terms": s.payment_terms, "default_currency": s.default_currency}


def find_purchase_orders(ctx: ToolContext, inp: FindPOIn) -> dict:
    q = select(PurchaseOrder).where(PurchaseOrder.organization_id == ctx.org_id).options(selectinload(PurchaseOrder.lines))
    if inp.supplier_id:
        q = q.where(PurchaseOrder.supplier_id == _uuid(inp.supplier_id))
    if inp.po_number:
        q = q.where(PurchaseOrder.po_number == inp.po_number)
    pos = ctx.session.scalars(q.limit(10)).all()
    return {"purchase_orders": [
        {"id": str(p.id), "po_number": p.po_number, "status": p.status, "currency": p.currency,
         "order_date": p.order_date.isoformat(),
         "lines": [{"id": str(pl.id), "line_no": pl.line_no, "sku": pl.sku, "description": pl.description,
                    "quantity": _dec(pl.quantity), "unit_price": _dec(pl.unit_price)} for pl in p.lines]}
        for p in pos]}


def get_goods_receipts(ctx: ToolContext, inp: GetReceiptsIn) -> dict:
    grs = ctx.session.scalars(select(GoodsReceipt).where(
        GoodsReceipt.purchase_order_id == _uuid(inp.purchase_order_id), GoodsReceipt.organization_id == ctx.org_id)
        .options(selectinload(GoodsReceipt.lines))).all()
    return {"goods_receipts": [
        {"id": str(g.id), "gr_number": g.gr_number, "received_date": g.received_date.isoformat(),
         "lines": [{"po_line_id": str(gl.po_line_id), "quantity_received": _dec(gl.quantity_received)} for gl in g.lines]}
        for g in grs]}


def run_reconciliation(ctx: ToolContext, inp: RunReconIn) -> dict:
    from app.services.reconciliation.service import reconcile_invoice

    inv = ctx.session.scalars(select(Invoice).where(Invoice.id == _uuid(inp.invoice_id),
                                                    Invoice.organization_id == ctx.org_id)).first()
    if inv is None:
        return {"error": "invoice not found"}
    run = reconcile_invoice(ctx.session, inv, triggered_by="agent", mode=inp.mode)
    return {"run_id": str(run.id), "outcome": run.outcome, "engine_version": run.engine_version,
            "findings": [{k: f.get(k) for k in ("type", "severity", "message", "expected", "actual", "difference",
                                                 "amount_at_risk", "invoice_line_no", "message_key", "params")}
                         for f in run.result["findings"]],
            "purchase_order_id": run.result.get("purchase_order_id"), "supplier_id": run.result.get("supplier_id"),
            "supplier_match": run.result.get("supplier_match")}


def _search(ctx: ToolContext, inp: SearchIn, doc_types: list[str]) -> dict:
    from app.services.rag.service import search

    from app.services.rag.answer import screen_hits

    hits = search(ctx.session, ctx.org_id, inp.query, k=4,
                  supplier_id=_uuid(inp.supplier_id) if inp.supplier_id else None, doc_types=doc_types,
                  as_of=ctx.as_of)
    hits, excluded = screen_hits(hits)  # injected instructions never reach the model or the citations
    return {"excluded_passages": excluded, "passages": [{"chunk_id": h.chunk.id, "title": h.chunk.document_title, "doc_type": h.chunk.doc_type,
                          "page": h.chunk.page, "section": h.chunk.section, "effective_date": h.chunk.effective_date,
                          "document_id": h.chunk.source_document_id, "knowledge_document_id": h.chunk.document_id,
                          "text": h.chunk.text, "score": round(h.score, 4)} for h in hits]}


def search_supplier_agreements(ctx: ToolContext, inp: SearchIn) -> dict:
    return _search(ctx, inp, ["supplier_agreement"])


def retrieve_policy(ctx: ToolContext, inp: SearchIn) -> dict:
    return _search(ctx, SearchIn(query=inp.query), ["purchasing_policy", "procedure"])


def create_exception_draft(ctx: ToolContext, inp: DraftIn) -> dict:
    inv_id = _uuid(inp.invoice_id)
    invoice = ctx.session.scalar(select(Invoice.id).where(Invoice.id == inv_id, Invoice.organization_id == ctx.org_id)
                                 .with_for_update())
    if invoice is None:
        return {"error": "invoice not found"}
    exc = ctx.session.scalars(select(ExceptionCase).where(
        ExceptionCase.invoice_id == inv_id, ExceptionCase.organization_id == ctx.org_id,
        ExceptionCase.status.in_(["draft", "open", "pending_info", "escalated"]))).first()
    created = False
    if exc is None:
        exc = ExceptionCase(organization_id=ctx.org_id, invoice_id=inv_id, status="draft",
                            title=f"AI investigation — {inp.summary.get('headline', 'review required')}"[:300])
        ctx.session.add(exc)
        created = True
    exc.ai_summary = inp.summary
    exc.created_by_agent = exc.created_by_agent or created
    exc.agent_run_id = ctx.agent_run_id
    exc.proposed_action_detail = exc.proposed_action_detail or inp.summary.get("recommendation")
    if inp.proposed_action and not exc.proposed_action:
        exc.proposed_action = inp.proposed_action
    ctx.session.flush()
    audit.record(ctx.session, org_id=ctx.org_id, action="exception.ai_summary_attached", entity_type="exception",
                 entity_id=exc.id, actor_type="agent", actor_label="investigation-agent",
                 after={"proposed_action": inp.proposed_action, "mode": inp.summary.get("mode")},
                 meta={"agent_run_id": str(ctx.agent_run_id) if ctx.agent_run_id else None})
    return {"exception_id": str(exc.id), "status": exc.status, "created": created}


# ------------------------------------------------------------------ copilot read tools
def _org(ctx: ToolContext):  # noqa: ANN202
    from app.models import Organization

    return ctx.session.get(Organization, ctx.org_id)


def review_queue(ctx: ToolContext, inp: QueueIn) -> dict:
    from app.api.routes.queue import ranked_items

    statuses = (inp.status,) if inp.status else ("open", "escalated", "pending_info")
    items = ranked_items(ctx.session, _org(ctx), statuses=statuses)
    if inp.level:
        items = [i for i in items if i["priority"]["level"] == inp.level]
    if inp.overdue:
        items = [i for i in items if i["due_in_days"] is not None and i["due_in_days"] < 0]
    if inp.due_within_days is not None:
        items = [i for i in items if i["due_in_days"] is not None and i["due_in_days"] <= inp.due_within_days]
    if inp.supplier:
        q = inp.supplier.lower()
        items = [i for i in items if q in (i["supplier_name"] or "").lower() or q in (i["supplier_name_en"] or "").lower()]
    if inp.finding_type:
        items = [i for i in items if inp.finding_type.upper() in i["finding_types"]]
    keep = ("exception_id", "invoice_id", "invoice_number", "supplier_name", "supplier_name_en", "total", "currency",
            "amount_at_risk", "amount_at_risk_base", "due_date", "due_in_days", "status", "finding_types",
            "proposed_action")
    return {"count": len(items), "items": [{**{k: i[k] for k in keep}, "priority": i["priority"]["level"],
                                            "rank": i["priority"]["rank"]} for i in items[:inp.limit]]}


def queue_summary(ctx: ToolContext, inp: EmptyIn) -> dict:
    from decimal import Decimal

    from sqlalchemy import func

    from app.api.routes.queue import ranked_items
    from app.core.money import D

    items = ranked_items(ctx.session, _org(ctx))
    by_currency: dict[str, dict[str, Decimal]] = {}
    for i in items:
        g = by_currency.setdefault(i["currency"] or "unknown", {"value_under_review": Decimal(0), "amount_at_risk": Decimal(0)})
        g["value_under_review"] += D(i["total"]) if i["total"] else Decimal(0)
        g["amount_at_risk"] += D(i["amount_at_risk"])
    ready = ctx.session.scalar(select(func.count()).select_from(Invoice).where(
        Invoice.organization_id == ctx.org_id, Invoice.status == "reconciled")) or 0
    return {"needs_review": len(items),
            "by_priority": {lvl: sum(1 for i in items if i["priority"]["level"] == lvl) for lvl in ("critical", "high", "normal")},
            "overdue": sum(1 for i in items if i["due_in_days"] is not None and i["due_in_days"] < 0),
            "ready_for_payment_approval": ready,
            "totals_by_currency": {c: {k: f"{v:.2f}" for k, v in g.items()} for c, g in by_currency.items()},
            "note": "Amounts are per currency and are never added across currencies."}


def search_invoices(ctx: ToolContext, inp: InvoiceSearchIn) -> dict:
    from decimal import Decimal, InvalidOperation

    from sqlalchemy import or_

    q = (select(Invoice, Supplier).outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
         .where(Invoice.organization_id == ctx.org_id))
    if inp.text:
        like = f"%{inp.text}%"
        q = q.where(or_(Invoice.invoice_number.ilike(like), Invoice.supplier_name_raw.ilike(like),
                        Invoice.po_reference.ilike(like), Supplier.name.ilike(like), Supplier.name_en.ilike(like)))
    if inp.status:
        q = q.where(Invoice.status == inp.status)
    try:
        if inp.min_total:
            q = q.where(Invoice.total >= Decimal(inp.min_total))
        if inp.max_total:
            q = q.where(Invoice.total <= Decimal(inp.max_total))
        if inp.date_from:
            q = q.where(Invoice.invoice_date >= _date.fromisoformat(inp.date_from))
        if inp.date_to:
            q = q.where(Invoice.invoice_date <= _date.fromisoformat(inp.date_to))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid filter: {exc}") from exc
    order = {"newest": Invoice.created_at.desc(), "oldest": Invoice.created_at.asc(),
             "largest": Invoice.total.desc().nulls_last()}[inp.sort]
    rows = ctx.session.execute(q.order_by(order).limit(inp.limit)).all()
    return {"invoices": [{"invoice_id": str(i.id), "invoice_number": i.invoice_number,
                          "supplier": s.name if s else i.supplier_name_raw, "status": i.status,
                          "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None,
                          "total": _dec(i.total), "currency": i.currency, "po_reference": i.po_reference}
                         for i, s in rows]}


def get_exception(ctx: ToolContext, inp: GetExceptionIn) -> dict:
    from app.models import Discrepancy

    exc = ctx.session.scalars(select(ExceptionCase).where(ExceptionCase.id == _uuid(inp.exception_id),
                                                          ExceptionCase.organization_id == ctx.org_id)).first()
    if exc is None:
        return {"error": "exception not found"}
    findings = ctx.session.scalars(select(Discrepancy).where(Discrepancy.invoice_id == exc.invoice_id,
                                                             Discrepancy.status == "open")).all()
    summary = exc.ai_summary or {}
    return {"exception_id": str(exc.id), "invoice_id": str(exc.invoice_id), "status": exc.status, "title": exc.title,
            "proposed_action": exc.proposed_action,
            "findings": [{"type": f.type, "severity": f.severity, "message": f.message,
                          "amount_at_risk": (f.evidence or {}).get("amount_at_risk")} for f in findings],
            "ai_summary": {k: summary.get(k) for k in ("headline", "summary", "recommendation")} if summary else None}


def supplier_overview(ctx: ToolContext, inp: SupplierLookupIn) -> dict:
    from sqlalchemy import func, or_

    from app.services.reconciliation.text_match import name_similarity

    sups = ctx.session.scalars(select(Supplier).where(Supplier.organization_id == ctx.org_id)).all()
    scored = sorted(((max(name_similarity(inp.name, n) for n in [s.name, s.name_en or "", *(s.aliases or [])] if n)
                      if inp.name.strip() != s.tax_id else 1.0, s) for s in sups), key=lambda x: -x[0])
    if not scored or scored[0][0] < 0.5:
        return {"error": "no supplier matches that name", "suppliers": [s.name for s in sups][:20]}
    sup = scored[0][1]
    invoices = ctx.session.scalars(select(Invoice).where(Invoice.organization_id == ctx.org_id, Invoice.supplier_id == sup.id)
                                   .order_by(Invoice.created_at.desc()).limit(10)).all()
    open_exc = ctx.session.scalar(select(func.count()).select_from(ExceptionCase).join(Invoice, Invoice.id == ExceptionCase.invoice_id)
                                  .where(Invoice.supplier_id == sup.id, ExceptionCase.organization_id == ctx.org_id,
                                         or_(ExceptionCase.status == "open", ExceptionCase.status == "pending_info",
                                             ExceptionCase.status == "escalated"))) or 0
    pos = ctx.session.scalars(select(PurchaseOrder).where(PurchaseOrder.organization_id == ctx.org_id,
                                                          PurchaseOrder.supplier_id == sup.id)).all()
    return {"supplier_id": str(sup.id), "name": sup.name, "name_en": sup.name_en, "tax_id": sup.tax_id,
            "status": sup.status, "payment_terms": getattr(sup, "payment_terms", None), "open_exceptions": open_exc,
            "purchase_orders": [{"purchase_order_id": str(p.id), "po_number": p.po_number, "status": p.status,
                                 "currency": p.currency} for p in pos],
            "recent_invoices": [{"invoice_id": str(i.id), "invoice_number": i.invoice_number, "status": i.status,
                                 "total": _dec(i.total), "currency": i.currency} for i in invoices]}


COUNTED = ("needs_review", "exception", "reconciled", "approved", "on_hold")  # not rejected, failed or processing


def list_suppliers(ctx: ToolContext, inp: SupplierListIn) -> dict:
    from sqlalchemy import func

    open_cases = dict(ctx.session.execute(
        select(Invoice.supplier_id, func.count()).select_from(ExceptionCase).join(Invoice, Invoice.id == ExceptionCase.invoice_id)
        .where(ExceptionCase.organization_id == ctx.org_id, ExceptionCase.status.in_(["open", "pending_info", "escalated"]))
        .group_by(Invoice.supplier_id)).all())
    invoices = dict(ctx.session.execute(
        select(Invoice.supplier_id, func.count()).where(Invoice.organization_id == ctx.org_id).group_by(Invoice.supplier_id)).all())
    q = select(Supplier).where(Supplier.organization_id == ctx.org_id).order_by(Supplier.name)
    if inp.status:
        q = q.where(Supplier.status == inp.status)
    rows = [{"supplier_id": str(s.id), "name": s.name, "name_en": s.name_en, "tax_id": s.tax_id, "status": s.status,
             "payment_terms": s.payment_terms, "invoices": invoices.get(s.id, 0), "open_cases": open_cases.get(s.id, 0)}
            for s in ctx.session.scalars(q)]
    if inp.sort != "name":
        rows.sort(key=lambda r: (-r[inp.sort], r["name"]))
    return {"count": len(rows), "suppliers": rows}


def _by_supplier(ctx: ToolContext, statuses: tuple[str, ...], date_from=None, date_to=None, *, unpaid_only=False):  # noqa: ANN001, ANN202
    from sqlalchemy import func

    q = (select(Supplier.id, Supplier.name, Supplier.name_en, Invoice.currency, Invoice.status,
                func.count(), func.coalesce(func.sum(Invoice.total), 0))
         .join(Supplier, Supplier.id == Invoice.supplier_id)
         .where(Invoice.organization_id == ctx.org_id, Invoice.status.in_(statuses))
         .group_by(Supplier.id, Supplier.name, Supplier.name_en, Invoice.currency, Invoice.status))
    if unpaid_only:
        q = q.where(Invoice.payment_paid_on.is_(None))
    try:
        if date_from:
            q = q.where(Invoice.invoice_date >= _date.fromisoformat(date_from))
        if date_to:
            q = q.where(Invoice.invoice_date <= _date.fromisoformat(date_to))
    except ValueError as exc:
        raise ValueError(f"invalid date: {exc}") from exc
    return ctx.session.execute(q).all()


def supplier_spend(ctx: ToolContext, inp: SpendIn) -> dict:
    """Invoiced amounts per supplier and currency (rejected, failed and unprocessed invoices excluded)."""
    from decimal import Decimal

    base = ((_org(ctx).settings or {}).get("base_currency")) or "ILS"
    agg: dict = {}
    for sid, name, name_en, cur, _status, n, total in _by_supplier(ctx, COUNTED, inp.date_from, inp.date_to):
        row = agg.setdefault(str(sid), {"supplier_id": str(sid), "name": name, "name_en": name_en, "invoices": 0, "totals": {}})
        row["invoices"] += n
        row["totals"][cur or "unknown"] = row["totals"].get(cur or "unknown", Decimal(0)) + Decimal(total)
    rows = sorted(agg.values(), key=lambda r: (-r["totals"].get(base, Decimal(0)), -sum(r["totals"].values()), r["name"]))
    return {"base_currency": base, "suppliers": [{**r, "totals": {c: f"{v:.2f}" for c, v in r["totals"].items()}}
                                                 for r in rows[:inp.limit]],
            "note": "Ranked by the base currency; amounts in other currencies are listed separately, never converted."}


def open_payables(ctx: ToolContext, inp: EmptyIn) -> dict:
    """What is owed per supplier and currency: approved for payment, awaiting approval, still in review."""
    from decimal import Decimal

    stage = {"approved": "approved_for_payment", "reconciled": "awaiting_approval", "needs_review": "in_review",
             "exception": "in_review", "on_hold": "in_review"}
    agg: dict = {}
    for sid, name, name_en, cur, status, n, total in _by_supplier(ctx, tuple(stage), unpaid_only=True):
        row = agg.setdefault(str(sid), {"supplier_id": str(sid), "name": name, "name_en": name_en, "by_stage": {}})
        cell = row["by_stage"].setdefault(stage[status], {})
        cell[cur or "unknown"] = cell.get(cur or "unknown", Decimal(0)) + Decimal(total)
    rows = sorted(agg.values(), key=lambda r: ("approved_for_payment" not in r["by_stage"], r["name"]))
    return {"suppliers": [{**r, "by_stage": {s: {c: f"{v:.2f}" for c, v in cells.items()} for s, cells in r["by_stage"].items()}}
                          for r in rows],
            "note": "Recorded payments are excluded. 'approved_for_payment' means approved and due to be paid outside "
                    "the system. The other stages are awaiting approval or review. Currencies are never added together."}


def findings_by_type(ctx: ToolContext, inp: FindingsIn) -> dict:
    from app.models import Discrepancy

    rows = ctx.session.execute(
        select(Discrepancy, Invoice, Supplier).join(Invoice, Invoice.id == Discrepancy.invoice_id)
        .outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
        .where(Discrepancy.organization_id == ctx.org_id, Discrepancy.status == "open",
               Discrepancy.type == inp.finding_type.upper())
        .order_by(Discrepancy.created_at.desc()).limit(inp.limit)).all()
    cases = {e.invoice_id: e for e in ctx.session.scalars(select(ExceptionCase).where(
        ExceptionCase.organization_id == ctx.org_id, ExceptionCase.invoice_id.in_([i.id for _, i, _ in rows])))} if rows else {}
    return {"finding_type": inp.finding_type.upper(), "count": len(rows), "findings": [{
        "invoice_id": str(i.id), "invoice_number": i.invoice_number, "supplier": s.name if s else i.supplier_name_raw,
        "currency": i.currency, "message": d.message, "amount_at_risk": (d.evidence or {}).get("amount_at_risk"),
        "exception_id": str(cases[i.id].id) if i.id in cases else None,
    } for d, i, s in rows]}


def _find_invoice(ctx: ToolContext, number: str | None, invoice_id: str | None):  # noqa: ANN202
    from app.services.reconciliation.text_match import normalize_doc_number

    if invoice_id:
        return ctx.session.scalars(select(Invoice).where(Invoice.id == _uuid(invoice_id),
                                                         Invoice.organization_id == ctx.org_id)).first()
    if not number:
        return None
    want = normalize_doc_number(number)
    rows = ctx.session.scalars(select(Invoice).where(Invoice.organization_id == ctx.org_id,
                                                     Invoice.invoice_number.ilike(f"%{number[-4:]}%"))).all()
    exact = [i for i in rows if normalize_doc_number(i.invoice_number) == want]
    return (exact or rows or [None])[0]


def invoice_case(ctx: ToolContext, inp: InvoiceRefIn) -> dict:
    from app.models import Approval, Discrepancy

    inv = _find_invoice(ctx, inp.invoice_number, inp.invoice_id)
    if inv is None:
        return {"error": "invoice not found"}
    sup = ctx.session.get(Supplier, inv.supplier_id) if inv.supplier_id else None
    findings = ctx.session.scalars(select(Discrepancy).where(Discrepancy.invoice_id == inv.id,
                                                             Discrepancy.status == "open")).all()
    exc = ctx.session.scalars(select(ExceptionCase).where(ExceptionCase.invoice_id == inv.id)
                              .order_by(ExceptionCase.created_at.desc())).first()
    steps = ctx.session.scalars(select(Approval).where(Approval.invoice_id == inv.id, Approval.status != "superseded")
                                .order_by(Approval.step)).all()
    summary = (exc.ai_summary or {}) if exc else {}
    return {"invoice_id": str(inv.id), "invoice_number": inv.invoice_number, "status": inv.status,
            "supplier": sup.name if sup else inv.supplier_name_raw, "supplier_id": str(sup.id) if sup else None,
            "total": _dec(inv.total), "currency": inv.currency, "po_reference": inv.po_reference,
            "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "findings": [{"type": f.type, "severity": f.severity, "message": f.message,
                          "amount_at_risk": (f.evidence or {}).get("amount_at_risk")} for f in findings],
            "case": {"exception_id": str(exc.id), "status": exc.status, "proposed_action": exc.proposed_action,
                     "ai_headline": summary.get("headline")} if exc else None,
            "approval_steps": [{"step": a.step, "required_role": a.required_role, "status": a.status} for a in steps]}


def po_status(ctx: ToolContext, inp: PORefIn) -> dict:
    from decimal import Decimal
    from types import SimpleNamespace

    from app.api.routes.masterdata import get_po
    from app.services.reconciliation.text_match import normalize_doc_number

    want = normalize_doc_number(inp.po_number)
    po = next((p for p in ctx.session.scalars(select(PurchaseOrder).where(PurchaseOrder.organization_id == ctx.org_id))
               if normalize_doc_number(p.po_number) == want), None)
    if po is None:
        return {"error": f"purchase order {inp.po_number} not found"}
    d = get_po(po.id, SimpleNamespace(org_id=ctx.org_id), ctx.session)
    lines = []
    for ln in d["lines"]:
        ordered, received, invoiced = (Decimal(ln[k] or 0) for k in ("quantity", "received", "invoiced"))
        lines.append({**{k: ln[k] for k in ("line_no", "sku", "description", "quantity", "unit_price", "received", "invoiced")},
                      "to_receive": str(max(ordered - received, Decimal(0)).normalize()),
                      "to_invoice": str(max(ordered - invoiced, Decimal(0)).normalize())})
    return {"purchase_order_id": str(po.id), "po_number": po.po_number, "status": po.status, "currency": po.currency,
            "supplier": d.get("supplier_name"), "supplier_en": d.get("supplier_name_en"),
            "supplier_id": str(po.supplier_id), "lines": lines}


def period_totals(ctx: ToolContext, inp: PeriodIn) -> dict:
    from decimal import Decimal

    from sqlalchemy import func

    q = (select(Invoice.currency, func.count(), func.coalesce(func.sum(Invoice.subtotal), 0),
                func.coalesce(func.sum(Invoice.tax_total), 0), func.coalesce(func.sum(Invoice.total), 0))
         .where(Invoice.organization_id == ctx.org_id, Invoice.status.in_(COUNTED)).group_by(Invoice.currency))
    try:
        if inp.date_from:
            q = q.where(Invoice.invoice_date >= _date.fromisoformat(inp.date_from))
        if inp.date_to:
            q = q.where(Invoice.invoice_date <= _date.fromisoformat(inp.date_to))
    except ValueError as exc:
        raise ValueError(f"invalid date: {exc}") from exc
    return {"date_from": inp.date_from, "date_to": inp.date_to, "by_currency": [
        {"currency": c or "unknown", "invoices": n, "net": f"{Decimal(s):.2f}", "vat": f"{Decimal(t):.2f}",
         "total": f"{Decimal(tt):.2f}"} for c, n, s, t, tt in ctx.session.execute(q).all()],
        "note": "Invoices that are rejected, failed or still processing are excluded. Currencies are never added together."}


def approval_rules(ctx: ToolContext, inp: EmptyIn) -> dict:
    org = _org(ctx)
    st = org.settings or {}
    return {"approval": st.get("approval", {}), "tolerances": st.get("tolerances", {}),
            "critical_amount": (st.get("priority") or {}).get("critical_amount"),
            "steps": ["step 1: a finance reviewer approves", "step 2 (above the dual-approval threshold): an administrator "
                      "approves; the same person cannot approve both steps, and the uploader cannot approve"],
            "base_currency": st.get("base_currency", "ILS")}


def invoice_history(ctx: ToolContext, inp: InvoiceRefIn) -> dict:
    from app.models import AuditLog

    inv = _find_invoice(ctx, inp.invoice_number, inp.invoice_id)
    if inv is None:
        return {"error": "invoice not found"}
    ids = [inv.id] + list(ctx.session.scalars(select(ExceptionCase.id).where(ExceptionCase.invoice_id == inv.id)))
    rows = ctx.session.scalars(select(AuditLog).where(AuditLog.organization_id == ctx.org_id,
                                                      AuditLog.entity_id.in_(ids)).order_by(AuditLog.created_at)).all()
    return {"invoice_id": str(inv.id), "invoice_number": inv.invoice_number, "events": [
        {"at": a.created_at.isoformat(timespec="minutes"), "action": a.action, "by": a.actor_label or a.actor_type,
         "note": (a.meta or {}).get("reason") or (a.meta or {}).get("note")} for a in rows[-25:]]}


def my_activity(ctx: ToolContext, inp: ActivityIn) -> dict:
    from datetime import UTC, datetime, timedelta

    from app.models import AuditLog

    since = datetime.now(UTC) - timedelta(days=inp.days)
    rows = ctx.session.scalars(select(AuditLog).where(AuditLog.organization_id == ctx.org_id, AuditLog.actor_id == ctx.user_id,
                                                      AuditLog.created_at >= since)
                               .order_by(AuditLog.created_at.desc()).limit(40)).all() if ctx.user_id else []
    return {"days": inp.days, "count": len(rows), "events": [
        {"at": a.created_at.isoformat(timespec="minutes"), "action": a.action, "entity_type": a.entity_type,
         **({"invoice_id": str(a.entity_id)} if a.entity_type == "invoice" and a.entity_id else {}),
         **({"exception_id": str(a.entity_id)} if a.entity_type == "exception" and a.entity_id else {})} for a in rows]}


HELP = {
    "overview": ("InvoiceFlow reads supplier invoices, matches them against purchase orders and goods receipts, and puts "
                 "every problem in a ranked review queue. People decide; the AI only explains and looks things up."),
    "statuses": ("needs_review: being checked; exception: a problem needs a decision; reconciled: matched and waiting for "
                 "payment approval; approved: approved for payment (paid outside the system); rejected: will not be paid; "
                 "on_hold: parked; processing: still being read."),
    "approve": ("Open the invoice, check it is reconciled, and use Approve in the approval panel. Invoices above the "
                "dual-approval threshold need a second, different approver (an administrator)."),
    "correct": ("Open the invoice's extraction review, fix the field or line next to the highlighted source, give a reason "
                "and save. Matching runs again automatically."),
    "escalate": "In the case workspace choose Escalate and write a note; an administrator who did not escalate it decides.",
    "request_info": ("In the case workspace choose Request clarification, say whether procurement or the supplier must "
                     "answer, and write what is missing. The case waits in 'awaiting information'."),
    "priority": ("Cases are ranked risk-first: blocking problems (unknown or ambiguous supplier, duplicate, missing PO, "
                 "not an invoice) and large amounts at risk are critical; overdue invoices move up."),
    "matching": ("Two-way matching compares the invoice with the purchase order; three-way also checks goods receipts. "
                 "Price and quantity differences within the organisation's tolerances are accepted."),
    "roles": ("Administrator: everything; finance reviewer: decides cases and approves step 1; procurement manager: uploads, "
              "corrects and answers clarifications; read-only: views."),
    "shortcuts": "Ctrl/⌘+K search and jump; / Copilot; ? all shortcuts; G then D, Q, I, S, P or K to navigate.",
}


def app_help(ctx: ToolContext, inp: HelpIn) -> dict:
    topic = inp.topic if inp.topic in HELP else "overview"
    return {"topic": topic, "text": HELP[topic], "topics": sorted(HELP)}


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    perm: Perm
    fn: Callable[[ToolContext, Any], dict]
    llm_visible: bool = True

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "schema": self.input_model.model_json_schema()}


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("get_invoice", "Get the extracted invoice header and line items.", GetInvoiceIn, Perm.INVOICE_READ, get_invoice),
    Tool("get_supplier", "Get a supplier master record.", GetSupplierIn, Perm.MASTERDATA_READ, get_supplier),
    Tool("find_purchase_orders", "Find purchase orders by supplier or PO number.", FindPOIn, Perm.MASTERDATA_READ,
         find_purchase_orders),
    Tool("get_goods_receipts", "Get goods receipts recorded against a purchase order.", GetReceiptsIn,
         Perm.MASTERDATA_READ, get_goods_receipts),
    Tool("run_reconciliation", "Run the deterministic reconciliation engine on an invoice.", RunReconIn,
         Perm.RECONCILE_RUN, run_reconciliation, llm_visible=False),
    Tool("search_supplier_agreements", "Search the supplier's agreements (Hebrew or English query).", SearchIn,
         Perm.KNOWLEDGE_READ, search_supplier_agreements),
    Tool("retrieve_policy", "Search internal purchasing policies and finance procedures.", SearchIn,
         Perm.KNOWLEDGE_READ, retrieve_policy),
    Tool("review_queue", "List open review cases ranked by risk, optionally filtered by priority, supplier or finding type.",
         QueueIn, Perm.INVOICE_READ, review_queue),
    Tool("queue_summary", "Counts of cases needing review by priority, overdue cases, and money at risk per currency.",
         EmptyIn, Perm.INVOICE_READ, queue_summary),
    Tool("search_invoices", "Search invoices by number, supplier or PO text, status, total range or invoice date range.",
         InvoiceSearchIn, Perm.INVOICE_READ, search_invoices),
    Tool("get_exception", "Get a review case: its findings, proposed action and AI summary.", GetExceptionIn,
         Perm.INVOICE_READ, get_exception),
    Tool("supplier_overview", "Look up a supplier by name, alias or tax ID: status, purchase orders, recent invoices, "
         "open cases.", SupplierLookupIn, Perm.MASTERDATA_READ, supplier_overview),
    Tool("list_suppliers", "List suppliers (optionally only blocked/active/inactive; sort by name, open cases or "
         "invoices): status, tax ID, payment terms, invoice and open-case counts.", SupplierListIn,
         Perm.MASTERDATA_READ, list_suppliers),
    Tool("findings_by_type", "Open problems of one type across all invoices (duplicates, price above PO, missing goods "
         "receipt, quantity over received, not an invoice, currency mismatch, missing Tax Authority allocation "
         "number...).", FindingsIn, Perm.INVOICE_READ,
         findings_by_type),
    Tool("invoice_case", "Why an invoice is in its state: status, open findings, its review case and approval steps. "
         "Look up by invoice number or id.", InvoiceRefIn, Perm.INVOICE_READ, invoice_case),
    Tool("po_status", "A purchase order's lines: ordered, received, invoiced, still to receive and still to invoice.",
         PORefIn, Perm.MASTERDATA_READ, po_status),
    Tool("period_totals", "Invoice count, net, VAT and total per currency for an invoice-date range.", PeriodIn,
         Perm.INVOICE_READ, period_totals),
    Tool("approval_rules", "The organisation's approval route, dual-approval threshold, tolerances and critical amount.",
         EmptyIn, Perm.INVOICE_READ, approval_rules),
    Tool("invoice_history", "Timeline of what happened to an invoice and its case (audit events).", InvoiceRefIn,
         Perm.INVOICE_READ, invoice_history),
    Tool("my_activity", "What the signed-in user did recently (decisions, approvals, corrections).", ActivityIn,
         Perm.INVOICE_READ, my_activity),
    Tool("app_help", "How InvoiceFlow works: statuses, approving, correcting, escalating, requesting information, "
         "priority, matching, roles, shortcuts.", HelpIn, Perm.INVOICE_READ, app_help),
    Tool("supplier_spend", "Invoiced amounts per supplier and currency, ranked; optional invoice-date range.", SpendIn,
         Perm.INVOICE_READ, supplier_spend),
    Tool("open_payables", "What is owed per supplier and currency: approved for payment, awaiting approval, in review.",
         EmptyIn, Perm.INVOICE_READ, open_payables),
    Tool("create_exception_draft", "Attach an advisory investigation summary to the invoice's review case.", DraftIn,
         Perm.EXCEPTION_COMMENT, create_exception_draft, llm_visible=False),
]}


def call_tool(ctx: ToolContext, name: str, args: dict, *, source: str = "planner") -> dict:
    """Validate, authorize, execute and trace one tool call."""
    tool = TOOLS.get(name)
    t0 = time.perf_counter()
    entry: dict = {"tool": name, "source": source, "input": args, "ts": time.time()}
    try:
        if tool is None:
            raise ValueError(f"unknown tool {name}")
        if not has_perm(ctx.role, tool.perm):
            raise ToolPermissionError(f"role '{ctx.role}' lacks permission {tool.perm.value} for tool {name}")
        inp = tool.input_model.model_validate(args)
        out = tool.fn(ctx, inp)
        entry.update(status="ok", output_preview=json.dumps(out, ensure_ascii=False, default=str)[:600])
        return out
    except (ValidationError, ValueError, ToolPermissionError) as exc:
        entry.update(status="rejected", error=str(exc)[:500])
        return {"error": str(exc)[:500]}
    finally:
        entry["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        ctx.trace.append(entry)
