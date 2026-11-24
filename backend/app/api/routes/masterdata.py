"""Suppliers, purchase orders and goods receipts."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Principal, dec, get_db, money, page_params, paginated, price, require
from app.models import GoodsReceipt, GRLine, Invoice, Organization, POLine, PurchaseOrder, ReconciliationRun, Supplier
from app.services import audit, email, supplier_banking
from app.services.rbac import Perm

router = APIRouter(prefix="/api", tags=["master data"])


# ------------------------------------------------------------------ suppliers
class SupplierIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=300)
    name_en: str | None = Field(None, max_length=300)
    tax_id: str | None = Field(None, pattern=r"^\d{8,10}$")
    email: str | None = Field(None, max_length=320)
    phone: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    default_currency: str = Field("ILS", pattern=r"^[A-Z]{3}$")
    payment_terms: str | None = Field(None, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    status: str = Field("active", pattern="^(active|blocked|inactive)$")


def supplier_out(s: Supplier, stats: dict | None = None) -> dict:
    return {"id": str(s.id), "name": s.name, "name_en": s.name_en, "tax_id": s.tax_id, "email": s.email,
            "phone": s.phone, "address": s.address, "default_currency": s.default_currency,
            "payment_terms": s.payment_terms, "aliases": s.aliases, "status": s.status,
            "created_at": s.created_at.isoformat(), **(stats or {})}


@router.get("/suppliers")
def list_suppliers(q: str | None = None, status: str | None = None, pg=Depends(page_params),
                   p: Principal = Depends(require(Perm.MASTERDATA_READ)), db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = select(Supplier).where(Supplier.organization_id == p.org_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Supplier.name.ilike(like), Supplier.name_en.ilike(like), Supplier.tax_id.ilike(like)))
    if status:
        stmt = stmt.where(Supplier.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Supplier.name).offset((page - 1) * size).limit(size)).all()
    counts = dict(db.execute(select(Invoice.supplier_id, func.count()).where(Invoice.organization_id == p.org_id)
                             .group_by(Invoice.supplier_id)).all())
    open_po = dict(db.execute(select(PurchaseOrder.supplier_id, func.count())
                              .where(PurchaseOrder.organization_id == p.org_id,
                                     PurchaseOrder.status.in_(["open", "partially_received"]))
                              .group_by(PurchaseOrder.supplier_id)).all())
    return paginated([supplier_out(s, {"invoice_count": counts.get(s.id, 0), "open_po_count": open_po.get(s.id, 0)})
                      for s in rows], total, page, size)


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: uuid.UUID, p: Principal = Depends(require(Perm.MASTERDATA_READ)),
                 db: Session = Depends(get_db)) -> dict:
    s = db.scalars(select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == p.org_id)).first()
    if not s:
        raise HTTPException(404, "Supplier not found")
    pos = db.scalars(select(PurchaseOrder).where(PurchaseOrder.supplier_id == s.id).order_by(PurchaseOrder.order_date.desc())
                     .options(selectinload(PurchaseOrder.lines))).all()
    invs = db.scalars(select(Invoice).where(Invoice.supplier_id == s.id).order_by(Invoice.created_at.desc()).limit(20)).all()
    return {**supplier_out(s),
            "purchase_orders": [po_summary(po) for po in pos],
            "invoices": [{"id": str(i.id), "invoice_number": i.invoice_number, "status": i.status,
                          "total": money(i.total), "currency": i.currency,
                          "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None} for i in invs]}


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, p: Principal = Depends(require(Perm.MASTERDATA_WRITE)),
                    db: Session = Depends(get_db)) -> dict:
    s = Supplier(organization_id=p.org_id, **body.model_dump())
    db.add(s)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "A supplier with this tax ID already exists") from exc
    audit.record(db, org_id=p.org_id, action="supplier.created", entity_type="supplier", entity_id=s.id,
                 actor_id=p.user.id, actor_label=p.user.email, after=body.model_dump())
    return supplier_out(s)


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: uuid.UUID, body: SupplierIn, p: Principal = Depends(require(Perm.MASTERDATA_WRITE)),
                    db: Session = Depends(get_db)) -> dict:
    s = db.scalars(select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == p.org_id)).first()
    if not s:
        raise HTTPException(404, "Supplier not found")
    before = supplier_out(s)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.flush()
    audit.record(db, org_id=p.org_id, action="supplier.updated", entity_type="supplier", entity_id=s.id,
                 actor_id=p.user.id, actor_label=p.user.email, before=before, after=supplier_out(s))
    return supplier_out(s)


def _bank_supplier(db: Session, p: Principal, supplier_id: uuid.UUID, *, lock: bool = False) -> Supplier:
    stmt = select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == p.org_id)
    supplier = db.scalar(stmt.with_for_update() if lock else stmt)
    if supplier is None:
        raise HTTPException(404, "Supplier not found")
    return supplier


@router.get("/suppliers/{supplier_id}/bank-account")
def get_bank_account(supplier_id: uuid.UUID, p: Principal = Depends(require(Perm.MASTERDATA_READ)),
                     db: Session = Depends(get_db)) -> dict:
    return supplier_banking.public_state(_bank_supplier(db, p, supplier_id))


@router.post("/suppliers/{supplier_id}/bank-account", status_code=201)
def propose_bank_account(supplier_id: uuid.UUID, body: supplier_banking.BankDetails, background: BackgroundTasks,
                         p: Principal = Depends(require(Perm.MASTERDATA_WRITE)), db: Session = Depends(get_db)) -> dict:
    supplier = _bank_supplier(db, p, supplier_id, lock=True)
    try:
        details = body.normalized()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    changed = supplier_banking.propose(db, supplier, p.user, details)
    notices = supplier_banking.admin_notices(db, p.org, [supplier.name] if changed else [])
    state = supplier_banking.public_state(supplier)
    db.commit()
    for message in notices:
        background.add_task(email.send, message)
    return state


class BankReviewIn(BaseModel):
    decision: Literal["confirm", "reject"]


@router.post("/suppliers/{supplier_id}/bank-account/{change_id}/review")
def review_bank_account(supplier_id: uuid.UUID, change_id: uuid.UUID, body: BankReviewIn, background: BackgroundTasks,
                        p: Principal = Depends(require(Perm.APPROVAL_DECIDE)), db: Session = Depends(get_db)) -> dict:
    supplier = _bank_supplier(db, p, supplier_id, lock=True)
    supplier_banking.review(db, supplier, p.org, p.user, change_id, body.decision == "confirm")
    notices = supplier_banking.admin_notices(db, p.org, [supplier.name])
    state = supplier_banking.public_state(supplier)
    db.commit()
    for message in notices:
        background.add_task(email.send, message)
    return state


# ------------------------------------------------------------------ purchase orders
class POLineIn(BaseModel):
    sku: str | None = Field(None, max_length=80)
    description: str = Field(..., min_length=1, max_length=1000)
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    unit: str | None = None


class POIn(BaseModel):
    supplier_id: uuid.UUID
    po_number: str = Field(..., min_length=1, max_length=50)
    order_date: date
    currency: str = Field("ILS", pattern=r"^[A-Z]{3}$")
    notes: str | None = None
    lines: list[POLineIn] = Field(..., min_length=1, max_length=500)


def po_summary(po: PurchaseOrder) -> dict:
    total = sum((ln.quantity * ln.unit_price for ln in po.lines), Decimal(0))
    return {"id": str(po.id), "po_number": po.po_number, "supplier_id": str(po.supplier_id),
            "order_date": po.order_date.isoformat(), "currency": po.currency, "status": po.status,
            "line_count": len(po.lines), "total": money(total)}


@router.get("/purchase-orders")
def list_pos(q: str | None = None, status: str | None = None, supplier_id: uuid.UUID | None = None,
             pg=Depends(page_params), p: Principal = Depends(require(Perm.MASTERDATA_READ)),
             db: Session = Depends(get_db)) -> dict:
    page, size = pg
    stmt = select(PurchaseOrder).where(PurchaseOrder.organization_id == p.org_id)
    if q:
        stmt = stmt.join(Supplier, Supplier.id == PurchaseOrder.supplier_id).where(
            or_(PurchaseOrder.po_number.ilike(f"%{q}%"), Supplier.name.ilike(f"%{q}%"), Supplier.name_en.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.po_number.desc())
                      .options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier))
                      .offset((page - 1) * size).limit(size)).all()
    return paginated([{**po_summary(po), "supplier_name": po.supplier.name, "supplier_name_en": po.supplier.name_en}
                      for po in rows], total, page, size)


@router.get("/purchase-orders/{po_id}")
def get_po(po_id: uuid.UUID, p: Principal = Depends(require(Perm.MASTERDATA_READ)), db: Session = Depends(get_db)) -> dict:
    po = db.scalars(select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.organization_id == p.org_id)
                    .options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier))).first()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    grs = db.scalars(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == po.id)
                     .options(selectinload(GoodsReceipt.lines)).order_by(GoodsReceipt.received_date)).all()
    received: dict[uuid.UUID, Decimal] = {}
    for g in grs:
        for gl in g.lines:
            received[gl.po_line_id] = received.get(gl.po_line_id, Decimal(0)) + gl.quantity_received
    invs = db.scalars(select(Invoice).where(Invoice.purchase_order_id == po.id)
                      .options(selectinload(Invoice.lines))).all()
    billed: dict[uuid.UUID, Decimal] = {}
    eligible = {inv.id: inv for inv in invs if inv.status not in ("rejected", "failed", "voided", "credit_note")}
    po_lines = {line.id for line in po.lines}
    if eligible:
        runs = db.scalars(select(ReconciliationRun).where(ReconciliationRun.invoice_id.in_(eligible))
                          .distinct(ReconciliationRun.invoice_id)
                          .order_by(ReconciliationRun.invoice_id, ReconciliationRun.created_at.desc(),
                                    ReconciliationRun.id.desc()))
        for run in runs:
            if any(f["type"] == "DUPLICATE_INVOICE" for f in run.result.get("findings", [])):
                continue
            quantities = {line.line_no: line.quantity for line in eligible[run.invoice_id].lines}
            for match in run.result.get("line_matches", []):
                if match.get("method") not in ("sku", "description") or not match.get("po_line_id"):
                    continue
                line_id = uuid.UUID(match["po_line_id"])
                quantity = quantities.get(match["invoice_line_no"])
                if line_id in po_lines and quantity is not None:
                    billed[line_id] = billed.get(line_id, Decimal(0)) + quantity
    return {**po_summary(po), "supplier_name": po.supplier.name, "supplier_name_en": po.supplier.name_en,
            "notes": po.notes,
            "lines": [{"id": str(ln.id), "line_no": ln.line_no, "sku": ln.sku, "description": ln.description,
                       "unit": ln.unit,
                       "quantity": dec(ln.quantity), "unit_price": price(ln.unit_price),
                       "line_total": money(ln.quantity * ln.unit_price),
                       "received": dec(received.get(ln.id, Decimal(0))),
                       "invoiced": dec(billed.get(ln.id, Decimal(0)))} for ln in po.lines],
            "goods_receipts": [{"id": str(g.id), "gr_number": g.gr_number, "received_date": g.received_date.isoformat(),
                                "received_by": g.received_by,
                                "lines": [{"po_line_id": str(gl.po_line_id), "quantity_received": dec(gl.quantity_received)}
                                          for gl in g.lines]} for g in grs],
            "invoices": [{"id": str(i.id), "invoice_number": i.invoice_number, "status": i.status,
                          "total": money(i.total)} for i in invs]}


@router.post("/purchase-orders", status_code=201)
def create_po(body: POIn, p: Principal = Depends(require(Perm.MASTERDATA_WRITE)), db: Session = Depends(get_db)) -> dict:
    sup = db.scalars(select(Supplier).where(Supplier.id == body.supplier_id, Supplier.organization_id == p.org_id)).first()
    if not sup:
        raise HTTPException(422, "Unknown supplier")
    po = PurchaseOrder(organization_id=p.org_id, supplier_id=sup.id, po_number=body.po_number, order_date=body.order_date,
                       currency=body.currency, notes=body.notes, created_by=p.user.id, status="open")
    db.add(po)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "PO number already exists") from exc
    for i, ln in enumerate(body.lines, start=1):
        db.add(POLine(organization_id=p.org_id, purchase_order_id=po.id, line_no=i, **ln.model_dump()))
    db.flush()
    db.refresh(po)
    audit.record(db, org_id=p.org_id, action="purchase_order.created", entity_type="purchase_order", entity_id=po.id,
                 actor_id=p.user.id, actor_label=p.user.email, after=body.model_dump(mode="json"))
    return po_summary(po)


class POUpdateIn(BaseModel):
    order_date: date | None = None
    notes: str | None = Field(None, max_length=5000)
    lines: list[POLineIn] | None = Field(None, min_length=1, max_length=500)


class POTransitionIn(BaseModel):
    action: Literal["close", "cancel"]
    reason: str = Field(..., min_length=1, max_length=1000)


def _po_for_write(db: Session, p: Principal, po_id: uuid.UUID) -> PurchaseOrder:
    po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.organization_id == p.org_id)
                   .with_for_update().options(selectinload(PurchaseOrder.lines)))
    if po is None:
        raise HTTPException(404, "Purchase order not found")
    if po.status in ("closed", "cancelled"):
        raise HTTPException(409, "The purchase order is closed or cancelled")
    return po


def _po_has_history(db: Session, po: PurchaseOrder) -> bool:
    receipt = select(GoodsReceipt.id).where(GoodsReceipt.purchase_order_id == po.id).exists()
    invoice = select(Invoice.id).where(Invoice.purchase_order_id == po.id).exists()
    return bool(db.scalar(select(or_(receipt, invoice))))


def _po_audit_state(po: PurchaseOrder) -> dict:
    return {**po_summary(po), "notes": po.notes, "lines": [
        {"sku": line.sku, "description": line.description, "quantity": str(line.quantity),
         "unit_price": str(line.unit_price), "unit": line.unit} for line in po.lines
    ]}


@router.patch("/purchase-orders/{po_id}")
def update_po(po_id: uuid.UUID, body: POUpdateIn, p: Principal = Depends(require(Perm.MASTERDATA_WRITE)),
              db: Session = Depends(get_db)) -> dict:
    # Reconciliation shares this lock while choosing and linking an order.
    db.get(Organization, p.org_id, with_for_update=True)
    po = _po_for_write(db, p, po_id)
    if (body.lines is not None or body.order_date is not None) and _po_has_history(db, po):
        raise HTTPException(409, "A linked receipt or invoice prevents changes to order lines or dates")
    before = _po_audit_state(po)
    if "notes" in body.model_fields_set:
        po.notes = body.notes
    if body.order_date is not None:
        po.order_date = body.order_date
    if body.lines is not None:
        po.lines = [POLine(organization_id=p.org_id, line_no=i, **line.model_dump()) for i, line in enumerate(body.lines, 1)]
    db.flush()
    audit.record(db, org_id=p.org_id, action="purchase_order.updated", entity_type="purchase_order", entity_id=po.id,
                 actor_id=p.user.id, actor_label=p.user.email, before=before, after=_po_audit_state(po))
    return po_summary(po)


@router.post("/purchase-orders/{po_id}/transition")
def transition_po(po_id: uuid.UUID, body: POTransitionIn, p: Principal = Depends(require(Perm.MASTERDATA_WRITE)),
                  db: Session = Depends(get_db)) -> dict:
    if not body.reason.strip():
        raise HTTPException(422, "Provide a reason for this change")
    db.get(Organization, p.org_id, with_for_update=True)
    po = _po_for_write(db, p, po_id)
    if body.action == "cancel" and _po_has_history(db, po):
        raise HTTPException(409, "An order with receipts or invoices can only be closed")
    before = {"status": po.status}
    po.status = "closed" if body.action == "close" else "cancelled"
    audit.record(db, org_id=p.org_id, action=f"purchase_order.{po.status}", entity_type="purchase_order", entity_id=po.id,
                 actor_id=p.user.id, actor_label=p.user.email, before=before, after={"status": po.status},
                 meta={"reason": body.reason.strip()})
    return po_summary(po)


class GRLineIn(BaseModel):
    po_line_id: uuid.UUID
    quantity_received: Decimal = Field(..., ge=0)


class GRIn(BaseModel):
    gr_number: str = Field(..., min_length=1, max_length=50)
    received_date: date
    received_by: str | None = None
    notes: str | None = None
    lines: list[GRLineIn] = Field(..., min_length=1)


@router.post("/purchase-orders/{po_id}/goods-receipts", status_code=201)
def create_gr(po_id: uuid.UUID, body: GRIn, p: Principal = Depends(require(Perm.MASTERDATA_WRITE)),
              db: Session = Depends(get_db)) -> dict:
    po = _po_for_write(db, p, po_id)
    valid = {ln.id for ln in po.lines}
    if any(ln.po_line_id not in valid for ln in body.lines):
        raise HTTPException(422, "Receipt lines must belong to this purchase order")
    gr = GoodsReceipt(organization_id=p.org_id, purchase_order_id=po.id, gr_number=body.gr_number,
                      received_date=body.received_date, received_by=body.received_by, notes=body.notes)
    db.add(gr)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "Goods receipt number already exists") from exc
    for ln in body.lines:
        db.add(GRLine(organization_id=p.org_id, goods_receipt_id=gr.id, po_line_id=ln.po_line_id,
                      quantity_received=ln.quantity_received))
    po.status = "partially_received"
    db.flush()
    audit.record(db, org_id=p.org_id, action="goods_receipt.created", entity_type="goods_receipt", entity_id=gr.id,
                 actor_id=p.user.id, actor_label=p.user.email, after=body.model_dump(mode="json"),
                 meta={"po_id": str(po.id)})
    return {"id": str(gr.id), "gr_number": gr.gr_number}
