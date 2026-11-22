"""Localizable finding messages: every engine finding carries a message key and the
parameters its template needs, and the frontend templates (he + en) use exactly those
parameters. The English `message` stays as the audit-log / API fallback."""
from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.reconciliation import engine as E
from tests.test_reconciliation_engine import S1, S2, ctx, invoice

DICTIONARIES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "i18n" / "dictionaries.ts"


def _scenarios() -> list[E.Result]:
    """One run per message key, so the contract is checked on real engine output."""
    out: list[E.Result] = []
    c, po = ctx()

    inv = invoice(po)  # price + quantity-vs-ordered + quantity-vs-received
    inv.lines[0].unit_price = Decimal("124.00")
    inv.lines[0].line_total = Decimal("7440.00")
    out.append(E.reconcile(inv, replace(c, previously_invoiced={po.lines[1].id: Decimal("2")})))

    out.append(E.reconcile(invoice(po, total=Decimal("1")), c))  # total
    inv = invoice(po)
    inv.lines[0].line_total += 5
    out.append(E.reconcile(inv, c))  # line total + subtotal
    out.append(E.reconcile(invoice(po, total=None, invoice_number=None), c))  # incomplete
    out.append(E.reconcile(invoice(po, security_flags=["ignore previous instructions"]), c))
    out.append(E.reconcile(invoice(po, document_kind=("quote", "הצעת מחיר")), c))
    twin = replace(po, id=uuid.uuid4(), number="PO 1")  # same reference after normalization
    out.append(E.reconcile(invoice(po), replace(c, purchase_orders=[po, twin])))
    copy = replace(po, id=uuid.uuid4(), number="PO-9")  # equal line coverage, no reference
    out.append(E.reconcile(invoice(po, po_reference=None), replace(c, purchase_orders=[po, copy])))
    out.append(E.reconcile(invoice(po, currency="USD"), c))
    out.append(E.reconcile(invoice(po, currency=None), c))
    out.append(E.reconcile(invoice(po), replace(c, receipt_count={})))
    out.append(E.reconcile(invoice(po, po_reference="PO-404"), c))
    other = replace(po, id=uuid.uuid4(), number="PO-9", supplier_id=S2)
    out.append(E.reconcile(invoice(po, po_reference="PO-9"), replace(c, purchase_orders=[*c.purchase_orders, other])))
    closed = replace(po, status="closed")
    out.append(E.reconcile(invoice(po), replace(c, purchase_orders=[closed, c.purchase_orders[1]])))
    out.append(E.reconcile(invoice(po, po_reference=None, lines=[
        E.InvLine(uuid.uuid4(), 1, "Express delivery", None, Decimal(1), Decimal(50), Decimal(0), Decimal(50))]), c))

    partial = invoice(po)
    partial.lines = partial.lines[:1]
    partial.subtotal = partial.lines[0].line_total
    partial.tax_amount = (partial.subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
    partial.total = partial.subtotal + partial.tax_amount
    out.append(E.reconcile(partial, c))  # unbilled PO lines

    inv = invoice(po)
    inv.lines.append(E.InvLine(uuid.uuid4(), 3, "Express delivery", None, Decimal(1), Decimal(50), Decimal(0), Decimal(50)))
    inv.subtotal += 50
    inv.total = inv.subtotal + inv.tax_amount
    out.append(E.reconcile(inv, c))  # item not on PO

    amb = E.InvoiceData(uuid.uuid4(), "כרמל שירותי ניקיון בע\"מ", "513000451", "CC-1", None, "ILS", "PO-2",
                        Decimal("6800"), Decimal(0), Decimal("1224"), Decimal("8024"),
                        [E.InvLine(uuid.uuid4(), 1, "שירותי ניקיון חודשיים - אגף", None, Decimal(1),
                                   Decimal("6800"), Decimal(0), Decimal("6800"))])
    out.append(E.reconcile(amb, c))

    out.append(E.reconcile(invoice(po, supplier_name_raw="כרמל קלין", supplier_tax_id_raw=None), c))
    out.append(E.reconcile(invoice(po, supplier_name_raw="Negev Lighting", supplier_tax_id_raw="599999990"), c))
    blocked = [replace(s, status="blocked") if s.id == S1 else s for s in c.suppliers]
    out.append(E.reconcile(invoice(po), replace(c, suppliers=blocked)))

    out.append(E.reconcile(invoice(po), replace(c, prior_invoices=[
        E.PriorInvoice(uuid.uuid4(), S1, "hc-1", None, None, "approved")])))
    out.append(E.reconcile(invoice(po, document_sha256="abc"), replace(c, prior_invoices=[
        E.PriorInvoice(uuid.uuid4(), None, "OTHER", None, None, "approved", document_sha256="abc")])))
    inv = invoice(po, invoice_date=date(2026, 3, 1))
    out.append(E.reconcile(inv, replace(c, prior_invoices=[
        E.PriorInvoice(uuid.uuid4(), S1, "HC-0", date(2026, 2, 20), inv.total, "approved")])))
    out.append(E.reconcile(invoice(po, invoice_date=date(2026, 9, 1)), c))  # no allocation number above 5,000
    out.append(E.reconcile(invoice(po, invoice_date=date(2026, 9, 1), allocation_number="12345"), c))  # malformed
    return out


@pytest.fixture(scope="module")
def findings() -> list[E.Finding]:
    return [f for r in _scenarios() for f in r.findings]


def test_scenarios_cover_every_message_key(findings):
    assert {f.message_key for f in findings} == set(E.MESSAGE_PARAMS)


def test_every_finding_carries_the_params_its_template_needs(findings):
    for f in findings:
        assert f.message_key in E.MESSAGE_PARAMS, f.message_key
        assert set(f.params) == E.MESSAGE_PARAMS[f.message_key], (f.message_key, f.params)
        assert all(v is None or isinstance(v, (str, int)) for v in f.params.values()), f.params


def test_price_mismatch_params_are_display_ready(findings):
    f = next(f for f in findings if f.type == "PRICE_MISMATCH")
    assert f.params == {"line": 1, "invoice_price": "124.00", "po_price": "118.00", "po": "PO-1",
                        "pct": "+5.08", "tolerance_pct": "1.0", "tolerance_abs": "0.05"}


def _templates(locale: str) -> dict[str, str]:
    src = DICTIONARIES.read_text(encoding="utf-8")
    block = re.search(rf"const {locale}(?:: Dict)? = \{{.*?\n  findingMessage: \{{(.*?)\n  \}},", src, re.S)
    assert block, f"findingMessage block missing for {locale}"
    return dict(re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', block.group(1)))


@pytest.mark.parametrize("locale", ["en", "he"])
def test_frontend_templates_use_exactly_the_engine_params(locale):
    templates = _templates(locale)
    assert set(templates) == set(E.MESSAGE_PARAMS)
    for key, text in templates.items():
        assert set(re.findall(r"\{(\w+)\}", text)) == E.MESSAGE_PARAMS[key], (locale, key, text)


def test_amounts_from_numeric_18_4_columns_are_shown_as_money():
    # prices come from NUMERIC(18,4) columns as Decimal("5380.0000")
    c, po = ctx()
    po.lines[0].unit_price = Decimal("5380.0000")
    inv = invoice(po)
    inv.lines[0].unit_price = Decimal("5650.0000")
    inv.lines[0].line_total = Decimal("339000.0000")
    f = next(f for f in E.reconcile(inv, c).findings if f.type == "PRICE_MISMATCH")
    assert (f.params["invoice_price"], f.params["po_price"]) == ("5650.00", "5380.00")
    assert "5650.0000" not in f.message
    assert (f.expected, f.actual, f.difference) == ("5380.00", "5650.00", "270.00")


def test_sub_cent_prices_keep_their_precision():
    c, po = ctx()
    po.lines[0].unit_price = Decimal("0.1250")
    inv = invoice(po)
    inv.lines[0].unit_price = Decimal("0.2375")
    inv.lines[0].line_total = Decimal("14.25")
    f = next(f for f in E.reconcile(inv, c).findings if f.type == "PRICE_MISMATCH")
    assert (f.params["invoice_price"], f.params["po_price"]) == ("0.2375", "0.125")
