"""Bulk import of suppliers, purchase orders and goods receipts from CSV or Excel.

`plan_*` reads and validates every row without writing anything; `apply_*` writes a plan that has no errors, inside the
caller's transaction (so the whole import commits or none of it does). Rows are numbered as in the spreadsheet: the
header is row 1. Existing suppliers are updated (only the columns that have a value); existing purchase orders and goods
receipts are skipped and never changed, because invoices may already be matched to them.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app.models import GoodsReceipt, GRLine, POLine, PurchaseOrder, Supplier, User
from app.services import supplier_banking

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000

TEMPLATES: dict[str, tuple[list[str], list[str]]] = {
    "suppliers": (["name", "name_en", "tax_id", "email", "phone", "address", "default_currency", "payment_terms",
                   "bank_code", "branch_code", "account_number", "iban"],
                  ['גליל משקאות בע"מ', "Galil Drinks Ltd", "516222333", "ap@example.co.il", "04-6000000", "כרמיאל",
                   "ILS", "שוטף + 60", "", "", "", ""]),
    "purchase-orders": (["po_number", "supplier_tax_id", "order_date", "currency", "sku", "description", "quantity",
                         "unit_price", "unit", "supplier_name"],
                        ["PO-2026-2001", "516222333", "05/11/2026", "ILS", "GD-WATER-6", "מים מינרליים 6 יח'", "40",
                         "18.50", "pack", ""]),
    "goods-receipts": (["gr_number", "po_number", "received_date", "sku", "line_no", "quantity_received", "received_by"],
                       ["GR-2026-2001", "PO-2026-2001", "07/11/2026", "GD-WATER-6", "", "40", "Warehouse"]),
}


class ImportError_(ValueError):
    """The file itself cannot be read (not one bad row)."""


@dataclass
class Plan:
    kind: str
    rows: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)  # {"action": create|update|skip, "key": ..., ...}

    def error(self, row: int, column: str, code: str, message: str) -> None:
        self.errors.append({"row": row, "column": column, "code": code, "message": message})

    @property
    def summary(self) -> dict:
        return {a: sum(1 for i in self.items if i["action"] == a) for a in ("create", "update", "skip")}

    def response(self) -> dict:
        return {"kind": self.kind, "summary": self.summary, "errors": self.errors[:200], "error_count": len(self.errors),
                "rows": self.rows[:50], "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in self.items[:200]]}


# ------------------------------------------------------------------ reading
def read_table(data: bytes, filename: str) -> list[tuple[int, dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise ImportError_("The file is larger than 5 MB; split it into smaller files.")
    if filename.lower().endswith(".xlsx") or data[:2] == b"PK":
        rows = _read_xlsx(data)
    else:
        rows = _read_csv(data)
    if not rows:
        raise ImportError_("The file has no header row.")
    header = [_norm_header(h) for h in rows[0]]
    out: list[tuple[int, dict[str, str]]] = []
    for i, values in enumerate(rows[1:], start=2):
        record = {h: (values[j].strip() if j < len(values) and values[j] is not None else "") for j, h in enumerate(header) if h}
        if any(record.values()):
            out.append((i, record))
        if len(out) > MAX_ROWS:
            raise ImportError_(f"More than {MAX_ROWS} rows; split the file.")
    return out


def _norm_header(h: object) -> str:
    return re.sub(r"\s+", "_", str(h or "").strip().lstrip("﻿").lower())


def _read_csv(data: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "cp1255"):  # Excel on Hebrew Windows saves CSV as cp1255
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportError_("The file is not UTF-8 or Windows-1255 text.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _read_xlsx(data: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - corrupt or not really an Excel file
        raise ImportError_("The Excel file could not be read.") from exc
    try:
        ws = wb.worksheets[0]
        return [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y")


def parse_date(value: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_number(value: str) -> Decimal | None:
    cleaned = value.replace(",", "").replace("₪", "").replace("$", "").replace("€", "").strip()
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


def _validate(plan: Plan, row: int, model: type[BaseModel], values: dict) -> BaseModel | None:
    try:
        return model(**values)
    except ValidationError as exc:
        for e in exc.errors():
            column = str(e["loc"][0]) if e["loc"] else "row"
            empty = e["type"] == "missing" or (e["type"] == "string_too_short" and e.get("input") in ("", None))
            code = "required" if empty else f"invalid_{column}"
            plan.error(row, column, code, f"{column}: {e['msg']}")
        return None


# ------------------------------------------------------------------ suppliers
def plan_suppliers(db: Session, org_id: uuid.UUID, table: list[tuple[int, dict[str, str]]]) -> Plan:
    from app.api.routes.masterdata import SupplierIn

    plan = Plan("suppliers")
    existing = db.scalars(select(Supplier).where(Supplier.organization_id == org_id)).all()
    by_tax = {s.tax_id: s for s in existing if s.tax_id}
    by_name = {s.name.strip().casefold(): s for s in existing}
    seen: set[str] = set()
    for row, rec in table:
        values = {k: v for k, v in rec.items() if k in SupplierIn.model_fields and v != ""}
        bank_values = {k: rec[k] for k in supplier_banking.BankDetails.model_fields if rec.get(k)}
        bank_details = None
        if bank_values:
            try:
                bank_details = supplier_banking.BankDetails(**bank_values).normalized()
            except ValueError:
                plan.error(row, "bank_code", "invalid_bank_details", "Enter a valid bank, branch and account number or a foreign IBAN.")
        values.setdefault("name", "")
        if "default_currency" in values:
            values["default_currency"] = values["default_currency"].upper()
        model = _validate(plan, row, SupplierIn, values)
        plan.rows.append({"row": row, **{k: rec.get(k, "") for k in ("name", "tax_id", "default_currency")}})
        if model is None:
            continue
        key = model.tax_id or model.name.strip().casefold()
        if key in seen:
            plan.error(row, "tax_id" if model.tax_id else "name", "duplicate_in_file", "This supplier appears twice in the file.")
            continue
        seen.add(key)
        match = by_tax.get(model.tax_id) if model.tax_id else by_name.get(model.name.strip().casefold())
        given = {k for k in values if k in model.model_fields_set}
        plan.items.append({"action": "update" if match else "create", "key": model.name, "row": row,
                           "_model": model, "_match": match, "_given": given, "_bank_details": bank_details})
    return plan


def apply_suppliers(db: Session, org_id: uuid.UUID, plan: Plan, user: User) -> list[str]:
    bank_ids = [item["_match"].id for item in plan.items if item["_match"] and item["_bank_details"]]
    if bank_ids:
        db.scalars(select(Supplier).where(Supplier.id.in_(bank_ids), Supplier.organization_id == org_id)
                   .order_by(Supplier.id).with_for_update().execution_options(populate_existing=True)).all()
    changed = []
    for item in plan.items:
        model, match = item["_model"], item["_match"]
        if match is None:
            match = Supplier(organization_id=org_id, **model.model_dump())
            db.add(match)
        else:
            for k in item["_given"]:
                setattr(match, k, getattr(model, k))
        if item["_bank_details"]:
            db.flush()
            if supplier_banking.propose(db, match, user, item["_bank_details"]):
                changed.append(match.name)
    db.flush()
    return changed


# ------------------------------------------------------------------ purchase orders
def plan_purchase_orders(db: Session, org_id: uuid.UUID, table: list[tuple[int, dict[str, str]]]) -> Plan:
    from app.api.routes.masterdata import POLineIn

    plan = Plan("purchase-orders")
    suppliers = db.scalars(select(Supplier).where(Supplier.organization_id == org_id)).all()
    by_tax = {s.tax_id: s for s in suppliers if s.tax_id}
    by_name = {s.name.strip().casefold(): s for s in suppliers}
    existing = set(db.scalars(select(PurchaseOrder.po_number).where(PurchaseOrder.organization_id == org_id)).all())
    groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for row, rec in table:
        number = rec.get("po_number", "")
        plan.rows.append({"row": row, **{k: rec.get(k, "") for k in ("po_number", "supplier_tax_id", "description", "quantity", "unit_price")}})
        if not number:
            plan.error(row, "po_number", "required", "po_number is required.")
            continue
        groups.setdefault(number, []).append((row, rec))
    for number, rows in groups.items():
        first_row, first = rows[0]
        if number in existing:
            plan.items.append({"action": "skip", "key": number, "row": first_row, "reason": "exists"})
            continue
        ok = True
        for row, rec in rows[1:]:  # the order's own fields must agree on every line
            for col in ("supplier_tax_id", "supplier_name", "order_date", "currency"):
                if rec.get(col, "") != first.get(col, ""):
                    plan.error(row, col, "inconsistent", f"{col} differs from the first line of {number}.")
                    ok = False
        tax, name = first.get("supplier_tax_id", ""), first.get("supplier_name", "")
        supplier = by_tax.get(tax) if tax else by_name.get(name.strip().casefold()) if name else None
        if supplier is None:
            plan.error(first_row, "supplier_tax_id" if tax or not name else "supplier_name", "unknown_supplier",
                       "No supplier with this tax ID or name in this business; import suppliers first.")
            ok = False
        order_date = parse_date(first.get("order_date", ""))
        if order_date is None:
            plan.error(first_row, "order_date", "invalid_date", "order_date must be a date like 05/11/2026 or 2026-11-05.")
            ok = False
        currency = (first.get("currency") or (supplier.default_currency if supplier else "ILS")).upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            plan.error(first_row, "currency", "invalid_default_currency", "currency must be a 3-letter code like ILS.")
            ok = False
        lines = []
        for row, rec in rows:
            values = {"sku": rec.get("sku") or None, "description": rec.get("description", ""), "unit": rec.get("unit") or None}
            for col in ("quantity", "unit_price"):
                n = parse_number(rec.get(col, ""))
                if n is None:
                    plan.error(row, col, "invalid_number", f"{col} must be a number.")
                    ok = False
                values[col] = n if n is not None else Decimal(0)
            line = _validate(plan, row, POLineIn, values)
            ok = ok and line is not None
            lines.append(line)
        if ok:
            plan.items.append({"action": "create", "key": number, "row": first_row, "lines": len(lines),
                               "_supplier": supplier, "_date": order_date, "_currency": currency, "_lines": lines})
    return plan


def apply_purchase_orders(db: Session, org_id: uuid.UUID, user_id: uuid.UUID, plan: Plan) -> None:
    for item in plan.items:
        if item["action"] != "create":
            continue
        po = PurchaseOrder(organization_id=org_id, supplier_id=item["_supplier"].id, po_number=item["key"],
                           order_date=item["_date"], currency=item["_currency"], created_by=user_id, status="open")
        db.add(po)
        db.flush()
        for i, line in enumerate(item["_lines"], start=1):
            db.add(POLine(organization_id=org_id, purchase_order_id=po.id, line_no=i, **line.model_dump()))
    db.flush()


# ------------------------------------------------------------------ goods receipts
def plan_goods_receipts(db: Session, org_id: uuid.UUID, table: list[tuple[int, dict[str, str]]]) -> Plan:
    plan = Plan("goods-receipts")
    pos = {po.po_number: po for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.organization_id == org_id)
                                                 .options(selectinload(PurchaseOrder.lines))).all()}
    existing = set(db.scalars(select(GoodsReceipt.gr_number).where(GoodsReceipt.organization_id == org_id)).all())
    groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for row, rec in table:
        number = rec.get("gr_number", "")
        plan.rows.append({"row": row, **{k: rec.get(k, "") for k in ("gr_number", "po_number", "sku", "quantity_received")}})
        if not number:
            plan.error(row, "gr_number", "required", "gr_number is required.")
            continue
        groups.setdefault(number, []).append((row, rec))
    for number, rows in groups.items():
        first_row, first = rows[0]
        if number in existing:
            plan.items.append({"action": "skip", "key": number, "row": first_row, "reason": "exists"})
            continue
        ok = True
        for row, rec in rows[1:]:
            for col in ("po_number", "received_date"):
                if rec.get(col, "") != first.get(col, ""):
                    plan.error(row, col, "inconsistent", f"{col} differs from the first line of {number}.")
                    ok = False
        po = pos.get(first.get("po_number", ""))
        if po is None:
            plan.error(first_row, "po_number", "unknown_po", "No purchase order with this number in this business.")
            continue
        if po.status in ("closed", "cancelled"):
            plan.error(first_row, "po_number", "closed_po", "The purchase order is closed or cancelled.")
            continue
        received = parse_date(first.get("received_date", ""))
        if received is None:
            plan.error(first_row, "received_date", "invalid_date", "received_date must be a date like 07/11/2026.")
            ok = False
        lines = []
        for row, rec in rows:
            sku, line_no = rec.get("sku", ""), rec.get("line_no", "")
            match = next((pl for pl in po.lines if (sku and pl.sku == sku) or (line_no and str(pl.line_no) == line_no)), None)
            if match is None:
                plan.error(row, "sku" if sku or not line_no else "line_no", "unknown_line",
                           f"{po.po_number} has no line with this SKU or line number.")
                ok = False
                continue
            qty = parse_number(rec.get("quantity_received", ""))
            if qty is None or qty < 0:
                plan.error(row, "quantity_received", "invalid_number", "quantity_received must be a number of at least 0.")
                ok = False
                continue
            lines.append((match.id, qty))
        if ok:
            plan.items.append({"action": "create", "key": number, "row": first_row, "po_number": po.po_number,
                               "_po": po, "_date": received, "_by": first.get("received_by") or None, "_lines": lines})
    return plan


def apply_goods_receipts(db: Session, org_id: uuid.UUID, plan: Plan) -> None:
    ids = [item["_po"].id for item in plan.items if item["action"] == "create"]
    current = {po.id: po for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.id.in_(ids),
                                                                          PurchaseOrder.organization_id == org_id)
                                               .order_by(PurchaseOrder.id).with_for_update()
                                               .options(selectinload(PurchaseOrder.lines))
                                               .execution_options(populate_existing=True))} if ids else {}
    for item in plan.items:
        if item["action"] != "create":
            continue
        po = current.get(item["_po"].id)
        if not po or po.status in ("closed", "cancelled") or not {line_id for line_id, _ in item["_lines"]} <= {line.id for line in po.lines}:
            raise HTTPException(409, "A purchase order changed during import. Check the spreadsheet again")
        gr = GoodsReceipt(organization_id=org_id, purchase_order_id=po.id, gr_number=item["key"],
                          received_date=item["_date"], received_by=item["_by"])
        db.add(gr)
        db.flush()
        for po_line_id, qty in item["_lines"]:
            db.add(GRLine(organization_id=org_id, goods_receipt_id=gr.id, po_line_id=po_line_id, quantity_received=qty))
        po.status = "partially_received"  # as when a receipt is entered by hand
    db.flush()


PLANNERS = {"suppliers": plan_suppliers, "purchase-orders": plan_purchase_orders, "goods-receipts": plan_goods_receipts}
