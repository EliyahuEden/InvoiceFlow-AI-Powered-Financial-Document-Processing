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
from typing import Any

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
                  supplier_id=_uuid(inp.supplier_id) if inp.supplier_id else None, doc_types=doc_types)
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
    exc = ctx.session.scalars(select(ExceptionCase).where(
        ExceptionCase.invoice_id == inv_id, ExceptionCase.organization_id == ctx.org_id,
        ExceptionCase.status.in_(["draft", "open", "pending_info"]))).first()
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
