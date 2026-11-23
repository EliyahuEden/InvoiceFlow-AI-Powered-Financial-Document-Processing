"""Bulk import of suppliers, purchase orders and goods receipts from CSV or Excel.

Preview first (nothing written), then commit: all or nothing, only when the preview has no errors. Errors name the
spreadsheet row (the header is row 1) and the column. Existing suppliers are updated; existing orders and receipts are
skipped, never changed, because invoices may already be matched to them."""
from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}


def csv(text: str, encoding: str = "utf-8-sig") -> bytes:
    return text.strip().encode(encoding) + b"\n"


def send(client, h, kind: str, data: bytes, *, commit: bool = False, name: str = "data.csv"):  # noqa: ANN001, ANN201
    return client.post(f"/api/import/{kind}?commit={'true' if commit else 'false'}", headers={**h, **CSRF},
                       files={"file": (name, data, "text/csv" if name.endswith(".csv") else
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


SUPPLIERS = """
name,name_en,tax_id,email,phone,address,default_currency,payment_terms
גליל משקאות בע"מ,Galil Drinks,516222333,ap@galil-drinks.example,04-6000000,כרמיאל,ILS,שוטף + 60
Northwind Paper Ltd,,599000111,,,,USD,Net 30
"""


def test_preview_writes_nothing_and_commit_creates_the_rows(client, as_user):
    h = as_user("procurement@kinneret.example")
    preview = send(client, h, "suppliers", csv(SUPPLIERS))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["errors"] == [] and body["summary"] == {"create": 2, "update": 0, "skip": 0}
    names = {s["name"] for s in client.get("/api/suppliers?page_size=100", headers=h).json()["items"]}
    assert "Northwind Paper Ltd" not in names                                    # preview wrote nothing
    done = send(client, h, "suppliers", csv(SUPPLIERS), commit=True)
    assert done.status_code == 200 and done.json()["summary"]["create"] == 2
    names = {s["name"] for s in client.get("/api/suppliers?page_size=100", headers=h).json()["items"]}
    assert {"Northwind Paper Ltd", 'גליל משקאות בע"מ'} <= names
    audit = client.get("/api/audit?action=import.suppliers", headers=h).json()["items"]
    assert audit and audit[0]["meta"]["create"] == 2


def test_an_existing_supplier_is_updated_by_tax_id(client, as_user):
    h = as_user("procurement@kinneret.example")
    data = csv("name,tax_id,payment_terms\nחרמון קלייה בע\"מ,515000230,שוטף + 45")
    assert send(client, h, "suppliers", data).json()["summary"] == {"create": 0, "update": 1, "skip": 0}
    send(client, h, "suppliers", data, commit=True)
    hermon = next(s for s in client.get("/api/suppliers?page_size=100", headers=h).json()["items"] if s["tax_id"] == "515000230")
    assert hermon["payment_terms"] == "שוטף + 45"


def test_errors_name_the_row_and_column_and_block_the_commit(client, as_user):
    h = as_user("procurement@kinneret.example")
    data = csv("name,tax_id,default_currency\nGood Supplier Ltd,598000001,ILS\n,598000002,ILS\nBad Tax Ltd,12,ILS\nBad Currency Ltd,598000003,shekel")
    errors = send(client, h, "suppliers", data).json()["errors"]
    assert {(e["row"], e["column"]) for e in errors} == {(3, "name"), (4, "tax_id"), (5, "default_currency")}
    refused = send(client, h, "suppliers", data, commit=True)
    assert refused.status_code == 422
    names = {s["name"] for s in client.get("/api/suppliers?page_size=100", headers=h).json()["items"]}
    assert "Good Supplier Ltd" not in names                                       # all or nothing


PURCHASE_ORDERS = """
po_number,supplier_tax_id,order_date,currency,sku,description,quantity,unit_price
PO-2026-2001,515000230,05/11/2026,ILS,HC-ESP-1KG,פולי קפה אספרסו 1 ק"ג,40,118.00
PO-2026-2001,515000230,05/11/2026,ILS,HC-CUP-8OZ,כוסות נייר 8oz,6,210.00
PO-2026-1001,515000230,2026-09-01,ILS,X,Already exists,1,1
"""


def test_purchase_order_rows_are_grouped_into_orders_and_existing_ones_are_skipped(client, as_user):
    h = as_user("procurement@kinneret.example")
    body = send(client, h, "purchase-orders", csv(PURCHASE_ORDERS)).json()
    assert body["errors"] == [] and body["summary"] == {"create": 1, "update": 0, "skip": 1}
    assert send(client, h, "purchase-orders", csv(PURCHASE_ORDERS), commit=True).status_code == 200
    pos = client.get("/api/purchase-orders?page_size=100", headers=h).json()["items"]
    po = next(p for p in pos if p["po_number"] == "PO-2026-2001")
    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=h).json()
    assert len(detail["lines"]) == 2 and detail["order_date"] == "2026-11-05"


def test_an_order_for_an_unknown_supplier_is_an_error(client, as_user):
    h = as_user("procurement@kinneret.example")
    data = csv("po_number,supplier_tax_id,order_date,description,quantity,unit_price\nPO-X-1,599999999,2026-11-01,Item,1,10")
    errors = send(client, h, "purchase-orders", data).json()["errors"]
    assert errors and errors[0]["row"] == 2 and errors[0]["column"] == "supplier_tax_id"


def test_goods_receipts_reference_the_order_and_its_line(client, as_user):
    h = as_user("procurement@kinneret.example")
    send(client, h, "purchase-orders", csv(PURCHASE_ORDERS), commit=True)
    data = csv("gr_number,po_number,received_date,sku,quantity_received\n"
               "GR-2026-2001,PO-2026-2001,07/11/2026,HC-ESP-1KG,40\n"
               "GR-2026-2001,PO-2026-2001,07/11/2026,HC-CUP-8OZ,6\n"
               "GR-2026-2002,PO-2026-2001,08/11/2026,NOT-ON-PO,1")
    body = send(client, h, "goods-receipts", data).json()
    assert [(e["row"], e["column"]) for e in body["errors"]] == [(4, "sku")]
    ok = csv("gr_number,po_number,received_date,sku,quantity_received\n"
             "GR-2026-2001,PO-2026-2001,07/11/2026,HC-ESP-1KG,40\n"
             "GR-2026-2001,PO-2026-2001,07/11/2026,HC-CUP-8OZ,6")
    assert send(client, h, "goods-receipts", ok, commit=True).json()["summary"] == {"create": 1, "update": 0, "skip": 0}
    assert send(client, h, "goods-receipts", ok).json()["summary"] == {"create": 0, "update": 0, "skip": 1}


def test_excel_files_work_like_csv(client, as_user):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in [["name", "tax_id", "default_currency"], ["Excel Supplier Ltd", 597000001, "ILS"]]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    h = as_user("procurement@kinneret.example")
    body = send(client, h, "suppliers", buf.getvalue(), name="suppliers.xlsx").json()
    assert body["errors"] == [] and body["summary"]["create"] == 1


def test_hebrew_windows_encoding_and_semicolons_are_read(client, as_user):
    h = as_user("procurement@kinneret.example")
    data = csv("name;tax_id;default_currency\nספק בקידוד חלונות;596000001;ILS", encoding="cp1255")
    body = send(client, h, "suppliers", data).json()
    assert body["errors"] == [] and body["rows"][0]["name"] == "ספק בקידוד חלונות"


def test_templates_download_with_headers(client, as_user):
    h = as_user("procurement@kinneret.example")
    r = client.get("/api/import/purchase-orders/template.csv", headers=h)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert r.content.startswith(b"\xef\xbb\xbf")                                 # BOM, so Excel shows Hebrew
    assert r.content.decode("utf-8-sig").splitlines()[0].startswith("po_number,supplier_tax_id,order_date")


def test_read_only_users_cannot_import(client, as_user):
    assert send(client, as_user("viewer@kinneret.example"), "suppliers", csv(SUPPLIERS)).status_code == 403


def test_another_business_cannot_order_from_this_businesss_suppliers(client, as_user):
    other = as_user("admin@yarden.example")
    data = csv("po_number,supplier_tax_id,order_date,description,quantity,unit_price\nPO-Y-9,515000230,2026-11-01,Item,1,10")
    errors = send(client, other, "purchase-orders", data).json()["errors"]
    assert errors and errors[0]["column"] == "supplier_tax_id"
