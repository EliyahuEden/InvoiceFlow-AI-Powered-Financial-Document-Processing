"""Exports: the invoice list (same filters as the inbox) and approved invoices for accounting, as CSV or Excel."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.api.routes.invoices import invoice_query, open_exception_counts
from app.models import Approval, Invoice, PurchaseOrder, Supplier, User
from app.services import audit
from app.services import export as ex
from app.services.rbac import Perm

router = APIRouter(prefix="/api/export", tags=["export"])

INVOICE_COLUMNS = ["invoice_number", "supplier", "supplier_tax_id", "invoice_date", "due_date", "currency", "subtotal",
                   "tax_total", "total", "allocation_number", "po_reference", "status", "open_exceptions"]
ACCOUNTING_COLUMNS = ["supplier_tax_id", "supplier", "invoice_number", "invoice_date", "due_date", "approved_date",
                      "currency", "net", "vat_rate", "vat", "total", "allocation_number", "po_number", "approved_by"]
HEBREW = {
    "invoice_number": "מספר חשבונית", "supplier": "ספק", "supplier_tax_id": "ח.פ. ספק", "invoice_date": "תאריך חשבונית",
    "due_date": "תאריך לתשלום", "currency": "מטבע", "subtotal": "סכום לפני מע\"מ", "tax_total": "מע\"מ", "total": "סה\"כ",
    "allocation_number": "מספר הקצאה", "po_reference": "הזמנת רכש", "status": "סטטוס", "open_exceptions": "חריגות פתוחות",
    "approved_date": "תאריך אישור", "net": "סכום נטו", "vat_rate": "שיעור מע\"מ", "vat": "מע\"מ", "po_number": "הזמנת רכש",
    "approved_by": "אושר על ידי",
}


def _send(fmt: str, name: str, header: list[str], rows: list[list], lang: str) -> Response:
    labels = [HEBREW.get(h, h) for h in header] if lang == "he" else header
    stamp = date.today().isoformat()
    if fmt == "xlsx":
        body = ex.to_xlsx(labels, rows, sheet=name, rtl=lang == "he")
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        body, media = ex.to_csv(labels, rows), "text/csv; charset=utf-8"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.{fmt}"', "Cache-Control": "no-store"})


def _fmt(fmt: str) -> str:
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(404, "Use .csv or .xlsx")
    return fmt


@router.get("/invoices.{fmt}")
def export_invoices(fmt: str, q: str | None = None, status: str | None = None, supplier_id: uuid.UUID | None = None,
                    sort: str = "-created_at", lang: str = "en",
                    p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> Response:
    fmt = _fmt(fmt)
    found = db.execute(invoice_query(p.org_id, q, status, supplier_id, sort).limit(ex.MAX_ROWS)).all()
    exc = open_exception_counts(db, p.org_id)
    rows = [[i.invoice_number, s.name if s else i.supplier_name_raw, s.tax_id if s else i.supplier_tax_id_raw,
             i.invoice_date, i.due_date, i.currency, i.subtotal, i.tax_total, i.total, i.allocation_number,
             i.po_reference, i.status, exc.get(i.id, 0)] for i, s, _ in found]
    audit.record(db, org_id=p.org_id, action="export.invoices", entity_type="export", entity_id=None,
                 actor_id=p.user.id, actor_label=p.user.email,
                 meta={"rows": len(rows), "format": fmt, "filters": {"q": q, "status": status,
                                                                    "supplier_id": str(supplier_id) if supplier_id else None}})
    return _send(fmt, "invoices", INVOICE_COLUMNS, rows, lang)


@router.get("/accounting.{fmt}")
def export_accounting(fmt: str, approved_from: date | None = None, approved_to: date | None = None, lang: str = "en",
                      p: Principal = Depends(require(Perm.APPROVAL_DECIDE)), db: Session = Depends(get_db)) -> Response:
    """Invoices approved for payment, one row each, ready to post in the accounting system."""
    fmt = _fmt(fmt)
    last = (select(Approval.invoice_id, func.max(Approval.decided_at).label("approved_at"))
            .where(Approval.organization_id == p.org_id, Approval.status == "approved")
            .group_by(Approval.invoice_id).subquery())
    approver = (select(Approval.invoice_id, User.email)
                .join(User, User.id == Approval.decided_by)
                .join(last, (last.c.invoice_id == Approval.invoice_id) & (last.c.approved_at == Approval.decided_at))
                .subquery())
    stmt = (select(Invoice, Supplier, PurchaseOrder.po_number, last.c.approved_at, approver.c.email)
            .join(last, last.c.invoice_id == Invoice.id)
            .outerjoin(approver, approver.c.invoice_id == Invoice.id)
            .outerjoin(Supplier, Supplier.id == Invoice.supplier_id)
            .outerjoin(PurchaseOrder, PurchaseOrder.id == Invoice.purchase_order_id)
            .where(Invoice.organization_id == p.org_id, Invoice.status == "approved")
            .order_by(last.c.approved_at, Invoice.invoice_number))
    if approved_from:
        stmt = stmt.where(func.date(last.c.approved_at) >= approved_from)
    if approved_to:
        stmt = stmt.where(func.date(last.c.approved_at) <= approved_to)
    rows = []
    for i, s, po_number, approved_at, email in db.execute(stmt.limit(ex.MAX_ROWS)).all():
        net = (i.subtotal - (i.discount_total or 0)) if i.subtotal is not None else None
        rows.append([s.tax_id if s else i.supplier_tax_id_raw, s.name if s else i.supplier_name_raw, i.invoice_number,
                     i.invoice_date, i.due_date, approved_at.date() if approved_at else None, i.currency, net,
                     i.tax_rate, i.tax_total, i.total, i.allocation_number, po_number or i.po_reference, email])
    audit.record(db, org_id=p.org_id, action="export.accounting", entity_type="export", entity_id=None,
                 actor_id=p.user.id, actor_label=p.user.email,
                 meta={"rows": len(rows), "format": fmt, "approved_from": approved_from.isoformat() if approved_from else None,
                       "approved_to": approved_to.isoformat() if approved_to else None})
    return _send(fmt, "accounting", ACCOUNTING_COLUMNS, rows, lang)
