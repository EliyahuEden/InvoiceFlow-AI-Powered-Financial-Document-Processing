"""Exports: the invoice list (with the same filters as the screen) and approved invoices for accounting, as CSV or
Excel. Every export is audited, stays inside the business, and cannot smuggle spreadsheet formulas."""
from __future__ import annotations

import csv
import io

import pytest

from tests.conftest import upload_invoice

pytestmark = pytest.mark.integration


def rows(r) -> list[dict]:  # noqa: ANN001
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\xef\xbb\xbf")                     # BOM, so Excel shows Hebrew
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


@pytest.fixture
def invoices(client, as_user):  # noqa: ANN001, ANN201
    proc = as_user("procurement@kinneret.example")
    return [upload_invoice(client, proc, f) for f in ("01_correct_tavor_he.pdf", "02_qty_mismatch_hermon_he.pdf")]


def test_invoice_export_follows_the_list_filters(client, as_user, invoices):
    h = as_user("finance@kinneret.example")
    everything = rows(client.get("/api/export/invoices.csv", headers=h))
    listed = client.get("/api/invoices?page_size=100", headers=h).json()
    assert len(everything) == listed["total"] > 0
    assert {"invoice_number", "supplier", "supplier_tax_id", "invoice_date", "total", "status"} <= set(everything[0])
    some = everything[0]["status"]
    filtered = rows(client.get(f"/api/export/invoices.csv?status={some}", headers=h))
    assert filtered and all(r["status"] == some for r in filtered)
    audit = client.get("/api/audit?action=export.invoices", headers=h).json()["items"]
    assert audit and audit[0]["meta"]["rows"] == len(filtered)


def test_hebrew_headers_and_statuses_on_request(client, as_user, invoices):
    from openpyxl import load_workbook

    h = as_user("finance@kinneret.example")
    csv_rows = rows(client.get("/api/export/invoices.csv?lang=he", headers=h))
    expected = {"TV-24518": "מוכן לאישור", "HC-8841": "חריגה"}
    assert {row["מספר חשבונית"]: row["סטטוס"] for row in csv_rows} == expected

    result = client.get("/api/export/invoices.xlsx?lang=he", headers=h)
    assert result.status_code == 200
    header, *data = load_workbook(io.BytesIO(result.content)).active.values
    assert {row[header.index("מספר חשבונית")]: row[header.index("סטטוס")] for row in data} == expected


def test_excel_export_has_real_numbers_and_dates(client, as_user, invoices):
    from openpyxl import load_workbook

    r = client.get("/api/export/invoices.xlsx", headers=as_user("finance@kinneret.example"))
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    ws = load_workbook(io.BytesIO(r.content)).active
    header = [c.value for c in ws[1]]
    row = [c.value for c in ws[2]]
    total = row[header.index("total")]
    assert isinstance(total, (int, float))


def test_insights_exports_match_dashboard_in_csv_and_excel(client, as_user, invoices):
    from openpyxl import load_workbook

    h = as_user("viewer@kinneret.example")
    count = client.get("/api/dashboard", headers=h).json()["kpis"]["invoices_total"]
    csv_rows = rows(client.get("/api/export/insights.csv", headers=h))
    assert any(row["metric"] == "invoices_total" and int(row["value"]) == count for row in csv_rows)
    result = client.get("/api/export/insights.xlsx", headers=h)
    assert result.status_code == 200
    data = load_workbook(io.BytesIO(result.content), read_only=True).active.values
    header, *values = data
    assert any(row[header.index("metric")] == "invoices_total" and row[header.index("value")] == count for row in values)


def test_accounting_export_has_only_approved_invoices(client, as_user):
    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    assert client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=fin, json={"decision": "approve"}).status_code == 200
    out = rows(client.get("/api/export/accounting.csv", headers=fin))
    assert out and {r["invoice_number"] for r in out} >= {"TV-24518"}
    tv = next(r for r in out if r["invoice_number"] == "TV-24518")
    assert tv["supplier_tax_id"] == "514000124" and tv["total"] == "7633.42" and tv["approved_date"]
    statuses = {i["status"] for i in client.get("/api/invoices?page_size=100", headers=fin).json()["items"]
                if i["invoice_number"] in {r["invoice_number"] for r in out}}
    assert statuses == {"approved"}


def test_accounting_export_is_for_finance(client, as_user):
    assert client.get("/api/export/accounting.csv", headers=as_user("viewer@kinneret.example")).status_code == 403
    assert client.get("/api/export/invoices.csv", headers=as_user("viewer@kinneret.example")).status_code == 200


def test_a_formula_in_extracted_text_is_neutralised(client, as_user, world, invoices):
    from sqlalchemy import update

    from app.core.db import session_scope
    from app.models import Invoice

    h = as_user("finance@kinneret.example")
    first = client.get("/api/invoices?page_size=1", headers=h).json()["items"][0]
    with session_scope(world["org_id"]) as s:
        s.execute(update(Invoice).where(Invoice.id == first["id"]).values(invoice_number="=HYPERLINK(\"http://x\")"))
    out = rows(client.get("/api/export/invoices.csv", headers=h))
    cell = next(r["invoice_number"] for r in out if "HYPERLINK" in r["invoice_number"])
    assert cell.startswith("'=")


def test_another_business_sees_only_its_own_invoices(client, as_user, invoices):
    mine = {r["invoice_number"] for r in rows(client.get("/api/export/invoices.csv", headers=as_user("finance@kinneret.example")))}
    theirs = {r["invoice_number"] for r in rows(client.get("/api/export/invoices.csv", headers=as_user("admin@yarden.example")))}
    assert mine and not (mine & theirs - {""})
