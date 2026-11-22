"""Israel's allocation number (מספר הקצאה): without it a buyer may not deduct the input VAT on a tax invoice above
the threshold in force on the invoice date (gov.il: NIS 20,000 in 2025, 10,000 from 2026-01-01, 5,000 from 2026-06-01)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.reconciliation import engine as E
from tests.test_reconciliation_engine import ctx, invoice

AUTUMN_2026 = date(2026, 9, 1)  # threshold 5,000; the helper invoice is 7,920 before VAT with 1,425.60 VAT


def finding(res: E.Result) -> E.Finding | None:
    return next((f for f in res.findings if f.type == "MISSING_ALLOCATION_NUMBER"), None)


@pytest.mark.parametrize(("day", "threshold"), [
    (date(2024, 4, 30), None),
    (date(2024, 5, 5), Decimal("25000")),
    (date(2025, 6, 1), Decimal("20000")),
    (date(2026, 1, 1), Decimal("10000")),
    (date(2026, 5, 31), Decimal("10000")),
    (date(2026, 6, 1), Decimal("5000")),
    (date(2027, 3, 1), Decimal("5000")),
])
def test_threshold_in_force_on_the_invoice_date(day, threshold):
    assert E.allocation_threshold(day) == threshold


@pytest.mark.parametrize(("raw", "clean"), [
    ("123456789", "123456789"), ("123-456-789", "123456789"), (" 123 456 789 ", "123456789"),
    ("12345678", None), ("1234567890", None), ("ABC456789", None), ("", None), (None, None),
])
def test_allocation_number_format(raw, clean):
    assert E.normalize_allocation_number(raw) == clean


def test_missing_number_above_the_threshold_is_flagged_with_the_vat_at_risk():
    c, po = ctx()
    res = E.reconcile(invoice(po, invoice_date=AUTUMN_2026), c)
    f = finding(res)
    assert f is not None and f.message_key == "MISSING_ALLOCATION_NUMBER"
    assert f.amount_at_risk == "1425.60"                 # the VAT that cannot be deducted
    assert f.params == {"amount": "7920.00", "threshold": "5000.00", "vat": "1425.60"}
    assert "MISSING_ALLOCATION_NUMBER" not in E.BLOCKING  # a reviewer decides; approving needs a justification
    assert res.outcome != "matched"


def test_a_valid_number_clears_the_finding():
    c, po = ctx()
    assert finding(E.reconcile(invoice(po, invoice_date=AUTUMN_2026, allocation_number="123456789"), c)) is None


def test_a_malformed_number_is_flagged_as_invalid():
    c, po = ctx()
    f = finding(E.reconcile(invoice(po, invoice_date=AUTUMN_2026, allocation_number="12345"), c))
    assert f is not None and f.message_key == "MISSING_ALLOCATION_NUMBER_INVALID"
    assert f.params["number"] == "12345"


def test_below_the_threshold_on_the_invoice_date_needs_no_number():
    c, po = ctx()
    assert finding(E.reconcile(invoice(po, invoice_date=date(2025, 6, 1)), c)) is None   # 7,920 < 20,000
    small = invoice(po, invoice_date=AUTUMN_2026)
    small.lines = small.lines[1:]
    small.subtotal = Decimal("840.00")
    small.tax_amount = Decimal("151.20")
    small.total = Decimal("991.20")
    assert finding(E.reconcile(small, c)) is None


def test_no_vat_or_foreign_currency_or_no_date_needs_no_number():
    c, po = ctx()
    exempt = invoice(po, invoice_date=AUTUMN_2026)
    exempt.tax_amount, exempt.total = Decimal("0"), exempt.subtotal   # an exempt dealer charges no VAT
    assert finding(E.reconcile(exempt, c)) is None
    assert finding(E.reconcile(invoice(po, invoice_date=AUTUMN_2026, currency="USD"), c)) is None
    assert finding(E.reconcile(invoice(po, invoice_date=None), c)) is None


# ---------------------------------------------------------------- reading it from the invoice
@pytest.mark.parametrize("text", [
    "חשבונית מס 4512\nתאריך: 01/09/2026\nמספר הקצאה: 123456789\nסה\"כ לתשלום 9,345.60",
    "חשבונית מס 4512\nמס' הקצאה 123-456-789\nסה\"כ לתשלום 9,345.60",
    "Tax Invoice 4512\nDate: 2026-09-01\nAllocation number: 123456789\nTotal 9,345.60",
    "Tax Invoice 4512\nAllocation No. 123 456 789\nTotal 9,345.60",
])
def test_rules_read_the_allocation_number(text):
    from app.services.extraction import rule_based

    value = rule_based.extract([(1, text)]).allocation_number.value
    assert E.normalize_allocation_number(value) == "123456789"


def test_no_label_means_no_allocation_number():
    from app.services.extraction import rule_based

    out = rule_based.extract([(1, "חשבונית מס 4512\nמספר הזמנה: PO-2026-1001\nסה\"כ לתשלום 9,345.60")])
    assert not out.allocation_number.value


# ---------------------------------------------------------------- the Copilot finds them
@pytest.mark.parametrize("question", [
    "אילו חשבוניות חסר בהן מספר הקצאה?", "Which invoices are missing an allocation number?",
    "show invoices without allocation numbers",
])
def test_the_offline_copilot_routes_allocation_questions(question):
    from app.services import copilot_offline as O
    from tests.test_copilot_paraphrases import CTX, TODAY

    fn, args = O.route(CTX, question, TODAY)
    assert fn is O.ans_findings and args.get("finding_type") == "MISSING_ALLOCATION_NUMBER"
