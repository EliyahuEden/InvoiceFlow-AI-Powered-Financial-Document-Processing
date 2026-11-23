"""Invoices: upload, inbox, detail, corrections, reconciliation, investigation, approvals."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Principal, dec, get_db, money, page_params, paginated, price, require
from app.core.config import get_settings
from app.models import (
    AgentRun,
    Approval,
    Discrepancy,
    Document,
    ExceptionCase,
    Invoice,
    Job,
    PurchaseOrder,
    ReconciliationRun,
    Supplier,
)
from app.services.public_errors import public_error
from app.services import workflow
from app.services.agent.runner import start_investigation
from app.services.documents.validation import UploadRejected
from app.services.processing import DuplicateUpload, create_invoice_upload
from app.services.ratelimit import check_rate_limit
from app.services.rbac import Perm
from app.services.reconciliation.service import reconcile_invoice

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def invoice_row(i: Invoice, supplier: Supplier | None, doc: Document | None, open_exc: int = 0) -> dict:
    return {
        "id": str(i.id), "status": i.status, "invoice_number": i.invoice_number,
        "supplier_id": str(i.supplier_id) if i.supplier_id else None,
        "supplier_name": supplier.name if supplier else i.supplier_name_raw,
        "supplier_name_en": supplier.name_en if supplier else None,
        "supplier_matched": supplier is not None,
        "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None, "currency": i.currency,
        "total": money(i.total), "po_reference": i.po_reference, "language": i.language,
        "extraction_method": i.extraction_method, "created_at": i.created_at.isoformat(),
        "filename": doc.filename if doc else None, "text_method": doc.text_method if doc else None,
        "open_exceptions": open_exc, "warnings": len(i.validation_warnings or []),
        "security_flag": any(w.get("code") == "SUSPICIOUS_INSTRUCTIONS" for w in (i.validation_warnings or [])),
    }


def invoice_query(org_id: uuid.UUID, q: str | None, status: str | None, supplier_id: uuid.UUID | None, sort: str):  # noqa: ANN201
    """The invoice list's filters and order, shared by the inbox and its export."""
    stmt = (select(Invoice, Supplier, Document)
            .outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
            .outerjoin(Document, Document.id == Invoice.document_id)
            .where(Invoice.organization_id == org_id))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Invoice.invoice_number.ilike(like), Invoice.supplier_name_raw.ilike(like),
                              Supplier.name.ilike(like), Supplier.name_en.ilike(like), Invoice.po_reference.ilike(like),
                              Document.filename.ilike(like)))
    if status:
        stmt = stmt.where(Invoice.status.in_(status.split(",")))
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    col = {"created_at": Invoice.created_at, "total": Invoice.total, "invoice_date": Invoice.invoice_date,
           "invoice_number": Invoice.invoice_number}.get(sort.lstrip("-"), Invoice.created_at)
    return stmt.order_by(col.desc().nulls_last() if sort.startswith("-") else col.asc().nulls_last())


def open_exception_counts(db: Session, org_id: uuid.UUID) -> dict:
    return dict(db.execute(select(ExceptionCase.invoice_id, func.count())
                           .where(ExceptionCase.organization_id == org_id,
                                  ExceptionCase.status.in_(["draft", "open", "pending_info"]))
                           .group_by(ExceptionCase.invoice_id)).all())


@router.get("")
def list_invoices(q: str | None = None, status: str | None = None, supplier_id: uuid.UUID | None = None,
                  sort: str = "-created_at", pg=Depends(page_params),
                  p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = invoice_query(p.org_id, q, status, supplier_id, sort)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.offset((page - 1) * size).limit(size)).all()
    exc_counts = open_exception_counts(db, p.org_id)
    status_counts = dict(db.execute(select(Invoice.status, func.count()).where(Invoice.organization_id == p.org_id)
                                    .group_by(Invoice.status)).all())
    out = paginated([invoice_row(i, s, d, exc_counts.get(i.id, 0)) for i, s, d in rows], total, page, size)
    out["status_counts"] = status_counts
    return out


@router.post("/upload", status_code=202)
async def upload_invoice(file: UploadFile = File(...), p: Principal = Depends(require(Perm.INVOICE_UPLOAD)),
                         db: Session = Depends(get_db)) -> dict:
    check_rate_limit(f"upload:{p.user.id}", get_settings().rate_limit_upload_per_minute)
    data = await file.read(get_settings().max_upload_bytes + 1)
    try:
        inv, job = create_invoice_upload(db, org_id=p.org_id, user=p.user, data=data, filename=file.filename or "upload")
    except UploadRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except DuplicateUpload as dup:
        raise HTTPException(409, {"message": "This exact file was already uploaded.",
                                  "invoice_id": str(dup.invoice_id) if dup.invoice_id else None}) from None
    return {"invoice_id": str(inv.id), "job_id": str(job.id), "status": inv.status}


def _discrepancy(d: Discrepancy) -> dict:
    return {"id": str(d.id), "type": d.type, "severity": d.severity, "message": d.message, "expected": d.expected,
            "actual": d.actual, "difference": d.difference, "status": d.status,
            "invoice_line_id": str(d.invoice_line_id) if d.invoice_line_id else None,
            "po_line_id": str(d.po_line_id) if d.po_line_id else None, "evidence": d.evidence}


@router.get("/{invoice_id}")
def get_invoice(invoice_id: uuid.UUID, p: Principal = Depends(require(Perm.INVOICE_READ)),
                db: Session = Depends(get_db)) -> dict:
    inv = db.scalars(select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == p.org_id)
                     .options(selectinload(Invoice.lines))).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    doc = db.get(Document, inv.document_id) if inv.document_id else None
    supplier = db.get(Supplier, inv.supplier_id) if inv.supplier_id else None
    po = db.scalars(select(PurchaseOrder).where(PurchaseOrder.id == inv.purchase_order_id)
                    .options(selectinload(PurchaseOrder.lines))).first() if inv.purchase_order_id else None
    run = db.scalars(select(ReconciliationRun).where(ReconciliationRun.invoice_id == inv.id)
                     .order_by(ReconciliationRun.created_at.desc()).limit(1)).first()
    discrepancies = db.scalars(select(Discrepancy).where(Discrepancy.run_id == run.id)).all() if run else []
    exc = db.scalars(select(ExceptionCase).where(ExceptionCase.invoice_id == inv.id)
                     .order_by(ExceptionCase.created_at.desc()).limit(1)).first()
    approvals = db.scalars(select(Approval).where(Approval.invoice_id == inv.id, Approval.status != "superseded")
                           .order_by(Approval.step)).all()
    agent_runs = db.scalars(select(AgentRun).where(AgentRun.invoice_id == inv.id)
                            .order_by(AgentRun.created_at.desc()).limit(5)).all()
    job = db.scalars(select(Job).where(Job.entity_id == inv.id, Job.type == "invoice.process")
                     .order_by(Job.created_at.desc()).limit(1)).first()
    received = {}
    if po:
        from app.models import GRLine

        received = dict(db.execute(select(GRLine.po_line_id, func.sum(GRLine.quantity_received))
                                   .where(GRLine.po_line_id.in_([ln.id for ln in po.lines]))
                                   .group_by(GRLine.po_line_id)).all())
    return {
        **invoice_row(inv, supplier, doc),
        "supplier_name_raw": inv.supplier_name_raw, "supplier_tax_id_raw": inv.supplier_tax_id_raw,
        "due_date": inv.due_date.isoformat() if inv.due_date else None, "payment_terms": inv.payment_terms,
        "allocation_number": inv.allocation_number,
        "subtotal": money(inv.subtotal), "discount_total": money(inv.discount_total), "tax_total": money(inv.tax_total),
        "tax_rate": dec(inv.tax_rate), "field_sources": inv.field_sources, "missing_fields": inv.missing_fields,
        "validation_warnings": inv.validation_warnings, "revision": revision(inv),
        "lines": [{"id": str(ln.id), "line_no": ln.line_no, "sku": ln.sku, "description": ln.description,
                   "quantity": dec(ln.quantity), "unit_price": price(ln.unit_price), "discount": money(ln.discount),
                   "line_total": money(ln.line_total), "source": ln.source} for ln in inv.lines],
        "document": {"id": str(doc.id), "filename": doc.filename, "mime_type": doc.mime_type, "page_count": doc.page_count,
                     "text_method": doc.text_method, "language": doc.language, "status": doc.status,
                     "error": public_error(doc.error), "size_bytes": doc.size_bytes, "sha256": doc.sha256} if doc else None,
        "supplier": {"id": str(supplier.id), "name": supplier.name, "name_en": supplier.name_en,
                     "tax_id": supplier.tax_id} if supplier else None,
        "purchase_order": {"id": str(po.id), "po_number": po.po_number, "currency": po.currency, "status": po.status,
                           "lines": [{"id": str(ln.id), "line_no": ln.line_no, "sku": ln.sku, "description": ln.description,
                                      "quantity": dec(ln.quantity), "unit_price": price(ln.unit_price),
                                      "received": dec(received.get(ln.id, Decimal(0)))} for ln in po.lines]} if po else None,
        "reconciliation": {"id": str(run.id), "outcome": run.outcome, "mode": run.mode,
                           "engine_version": run.engine_version, "created_at": run.created_at.isoformat(),
                           "tolerances": run.tolerances, "checks": run.result.get("checks", []),
                           "line_matches": run.result.get("line_matches", []),
                           "supplier_match": run.result.get("supplier_match"), "po_match": run.result.get("po_match"),
                           "triggered_by": run.triggered_by} if run else None,
        "discrepancies": [_discrepancy(d) for d in discrepancies],
        "exception": {"id": str(exc.id), "status": exc.status, "title": exc.title, "proposed_action": exc.proposed_action,
                      "has_ai_summary": exc.ai_summary is not None} if exc else None,
        "approvals": [{"id": str(a.id), "step": a.step, "required_role": a.required_role, "status": a.status,
                       "decided_by": str(a.decided_by) if a.decided_by else None,
                       "decided_at": a.decided_at.isoformat() if a.decided_at else None, "comment": a.comment}
                      for a in approvals],
        "agent_runs": [{"id": str(r.id), "status": r.status, "mode": r.mode, "created_at": r.created_at.isoformat()}
                       for r in agent_runs],
        "job": {"id": str(job.id), "status": job.status, "progress": job.progress, "message": job.progress_message,
                "attempts": job.attempts, "error": public_error(job.last_error)} if job else None,
    }


class LineIn(BaseModel):
    id: uuid.UUID | None = None  # the existing line this row edits; empty for a newly added row
    line_no: int | None = None
    sku: str | None = None
    description: str = Field(..., min_length=1, max_length=1000)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    discount: Decimal | None = None
    line_total: Decimal | None = None


class CorrectionIn(BaseModel):
    header: dict = Field(default_factory=dict)
    lines: list[LineIn] | None = None
    supplier_id: uuid.UUID | None = None
    reason: str | None = Field(None, max_length=1000)
    # The `revision` the client loaded. When it no longer matches, someone else saved in between (audit TECH-01).
    revision: str | None = Field(None, max_length=64)


def revision(inv: Invoice) -> str:
    """An opaque version token: changes whenever the invoice row is saved."""
    return inv.updated_at.isoformat()


@router.patch("/{invoice_id}")
def correct(invoice_id: uuid.UUID, body: CorrectionIn, p: Principal = Depends(require(Perm.INVOICE_EDIT)),
            db: Session = Depends(get_db)) -> dict:
    inv = db.scalars(select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == p.org_id)
                     .options(selectinload(Invoice.lines)).with_for_update()).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if body.revision is not None and body.revision != revision(inv):
        raise HTTPException(409, "This invoice was changed by someone else since you opened it. Reload to see the latest version.")
    if body.supplier_id and not db.scalars(select(Supplier).where(Supplier.id == body.supplier_id,
                                                                  Supplier.organization_id == p.org_id)).first():
        raise HTTPException(422, "Unknown supplier")
    workflow.correct_invoice(db, inv, p.user, body.header,
                             [ln.model_dump() for ln in body.lines] if body.lines is not None else None,
                             body.supplier_id, body.reason)
    return {"id": str(inv.id), "status": inv.status}


@router.post("/{invoice_id}/reconcile")
def rerun_reconciliation(invoice_id: uuid.UUID, mode: str = "three_way",
                         p: Principal = Depends(require(Perm.RECONCILE_RUN)), db: Session = Depends(get_db)) -> dict:
    if mode not in ("two_way", "three_way"):
        raise HTTPException(422, "mode must be two_way or three_way")
    inv = db.scalars(select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == p.org_id)
                     .options(selectinload(Invoice.lines))).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    run = reconcile_invoice(db, inv, triggered_by="user", actor_id=p.user.id, mode=mode)
    return {"run_id": str(run.id), "outcome": run.outcome, "status": inv.status}


@router.post("/{invoice_id}/investigate", status_code=202)
def investigate(invoice_id: uuid.UUID, p: Principal = Depends(require(Perm.AGENT_RUN)), db: Session = Depends(get_db)) -> dict:
    check_rate_limit(f"investigate:{p.user.id}", get_settings().rate_limit_ai_per_minute)  # each run makes model calls
    inv = db.scalars(select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == p.org_id)).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    active = db.scalars(select(AgentRun).where(AgentRun.invoice_id == inv.id,
                                               AgentRun.status.in_(["queued", "running"]))).first()
    if active:
        return {"agent_run_id": str(active.id), "status": active.status, "deduplicated": True}
    run, job = start_investigation(db, inv, p.user.id, p.role.value)
    return {"agent_run_id": str(run.id), "job_id": str(job.id), "status": run.status}


class ApprovalIn(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    comment: str | None = Field(None, max_length=2000)


@router.post("/{invoice_id}/approvals")
def approve(invoice_id: uuid.UUID, body: ApprovalIn, p: Principal = Depends(require(Perm.APPROVAL_DECIDE)),
            db: Session = Depends(get_db)) -> dict:
    inv = db.scalars(select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == p.org_id)).first()
    if not inv:
        raise HTTPException(404, "Invoice not found")
    step = workflow.decide_approval(db, inv, p.user, p.role.value, body.decision, body.comment)
    return {"step": step.step, "status": step.status, "invoice_status": inv.status}


# ------------------------------------------------------------------ demo samples
def _samples() -> list[dict]:
    import json

    from app.demo.generate import DATA_DIR

    m = DATA_DIR / "manifest.json"
    if not m.exists():
        return []
    return json.loads(m.read_text(encoding="utf-8")).get("upload_samples", [])


@router.get("/demo/samples")
def demo_samples(p: Principal = Depends(require(Perm.INVOICE_READ))) -> dict:
    """Synthetic invoices shipped in data/demo/upload_samples (not pre-loaded by the seed)."""
    return {"items": [{"file": s["file"], "scenario": s["scenario"], "description": s["description"],
                       "language": s["language"]} for s in _samples()]}


class SampleIn(BaseModel):
    file: str


@router.post("/demo/samples/upload", status_code=202)
def upload_sample(body: SampleIn, p: Principal = Depends(require(Perm.INVOICE_UPLOAD)), db: Session = Depends(get_db)) -> dict:
    from app.demo.generate import DATA_DIR

    allowed = {s["file"] for s in _samples()}
    if body.file not in allowed:  # whitelist only: never a caller-supplied path
        raise HTTPException(404, "Unknown sample")
    path = DATA_DIR / body.file
    try:
        inv, job = create_invoice_upload(db, org_id=p.org_id, user=p.user, data=path.read_bytes(), filename=path.name)
    except DuplicateUpload as dup:
        raise HTTPException(409, {"message": "This exact file was already uploaded.",
                                  "invoice_id": str(dup.invoice_id) if dup.invoice_id else None}) from None
    return {"invoice_id": str(inv.id), "job_id": str(job.id), "status": inv.status}
