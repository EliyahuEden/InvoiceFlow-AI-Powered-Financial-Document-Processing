"""Deterministic reconciliation engine: one test per rule, plus tolerance boundaries."""
from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal

import pytest

from app.services.reconciliation import engine as E

S1, S2, S3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def ctx(**kw) -> E.Context:
    l1, l2 = uuid.uuid4(), uuid.uuid4()
    po = E.POData(uuid.uuid4(), "PO-1", S1, "ILS", "open", [
        E.POLineData(l1, 1, "פולי קפה אספרסו 1 ק\"ג", Decimal("60"), Decimal("118.00"), "HC-ESP"),
        E.POLineData(l2, 2, "כוסות נייר 8oz", Decimal("4"), Decimal("210.00"), "HC-CUP"),
    ])
    amb = E.POData(uuid.uuid4(), "PO-2", S2, "ILS", "open", [
        E.POLineData(uuid.uuid4(), 1, "ניקיון חודשי - אגף א", Decimal("1"), Decimal("6800"), None),
        E.POLineData(uuid.uuid4(), 2, "ניקיון חודשי - אגף ב", Decimal("1"), Decimal("5900"), None),
    ])
    base = E.Context(
        suppliers=[E.SupplierData(S1, "חרמון קלייה בע\"מ", "Hermon Coffee", [], "515000238"),
                   E.SupplierData(S2, "כרמל שירותי ניקיון בע\"מ", None, ["כרמל קלין סרוויס"], "513000451"),
                   E.SupplierData(S3, "כרמל קלין-טק בע\"מ", None, [], "517000562")],
        purchase_orders=[po, amb], received={l1: Decimal("60"), l2: Decimal("4")},
        receipt_count={po.id: 1, amb.id: 1}, previously_invoiced={}, prior_invoices=[])
    return replace(base, **kw), po


def invoice(po: E.POData, **kw) -> E.InvoiceData:
    lines = [E.InvLine(uuid.uuid4(), i, pl.description, pl.sku, pl.quantity, pl.unit_price, Decimal(0),
                       (pl.quantity * pl.unit_price).quantize(Decimal("0.01"))) for i, pl in enumerate(po.lines, 1)]
    sub = sum((ln.line_total for ln in lines), Decimal(0))
    inv = E.InvoiceData(uuid.uuid4(), "חרמון קלייה בע\"מ", "515000238", "HC-1", None, "ILS", "PO-1", sub, Decimal(0),
                        (sub * Decimal("0.18")).quantize(Decimal("0.01")), None, lines)
    inv.total = inv.subtotal + inv.tax_amount
    for k, v in kw.items():
        setattr(inv, k, v)
    return inv


def types(res: E.Result) -> set[str]:
    return {f.type for f in res.findings if f.severity != "info"}


def test_clean_invoice_matches():
    c, po = ctx()
    res = E.reconcile(invoice(po), c)
    assert res.outcome == "matched" and types(res) == set()
    assert all(m.method == "sku" for m in res.line_matches)


def test_price_mismatch_with_amount_at_risk():
    c, po = ctx()
    inv = invoice(po)
    inv.lines[0].unit_price = Decimal("124.00")
    inv.lines[0].line_total = Decimal("7440.00")
    res = E.reconcile(inv, c)
    f = next(f for f in res.findings if f.type == "PRICE_MISMATCH")
    assert f.expected == "118.00" and f.actual == "124.00" and Decimal(f.amount_at_risk) == Decimal("360.00")


@pytest.mark.parametrize("price,flag", [("119.18", False), ("119.19", True)])  # 1% of 118 = 1.18
def test_price_tolerance_boundary(price, flag):
    c, po = ctx()
    inv = invoice(po)
    inv.lines[0].unit_price = Decimal(price)
    inv.lines[0].line_total = (Decimal(price) * 60).quantize(Decimal("0.01"))
    assert ("PRICE_MISMATCH" in types(E.reconcile(inv, c))) is flag


def test_quantity_exceeds_received_three_way_only():
    c, po = ctx()
    c.received[po.lines[0].id] = Decimal("50")
    assert "QUANTITY_EXCEEDS_RECEIVED" in types(E.reconcile(invoice(po), c))
    assert "QUANTITY_EXCEEDS_RECEIVED" not in types(E.reconcile(invoice(po), c, mode="two_way"))


def test_cumulative_quantity_uses_previous_invoices():
    c, po = ctx()
    c = replace(c, previously_invoiced={po.lines[1].id: Decimal("2")})
    assert {"QUANTITY_EXCEEDS_ORDERED", "QUANTITY_EXCEEDS_RECEIVED"} <= types(E.reconcile(invoice(po), c))


def test_duplicate_by_supplier_and_number_and_by_file_hash():
    c, po = ctx()
    prior = E.PriorInvoice(uuid.uuid4(), S1, "hc-1", None, None, "approved")
    assert "DUPLICATE_INVOICE" in types(E.reconcile(invoice(po), replace(c, prior_invoices=[prior])))
    prior2 = E.PriorInvoice(uuid.uuid4(), None, "OTHER", None, None, "approved", document_sha256="abc")
    assert "DUPLICATE_INVOICE" in types(E.reconcile(invoice(po, document_sha256="abc"), replace(c, prior_invoices=[prior2])))
    rejected = E.PriorInvoice(uuid.uuid4(), S1, "HC-1", None, None, "rejected")
    assert "DUPLICATE_INVOICE" not in types(E.reconcile(invoice(po), replace(c, prior_invoices=[rejected])))


def test_missing_po_and_po_inference():
    c, po = ctx()
    assert "MISSING_PURCHASE_ORDER" in types(E.reconcile(invoice(po, po_reference="PO-404"), c))
    res = E.reconcile(invoice(po, po_reference=None), c)  # inferred from line coverage
    assert res.po_match["method"] == "inferred_from_lines" and types(res) == set()


def test_supplier_identification():
    c, po = ctx()
    assert E.reconcile(invoice(po, supplier_tax_id_raw=None), c).supplier_match["method"] == "name"
    amb = E.reconcile(invoice(po, supplier_name_raw="כרמל קלין", supplier_tax_id_raw=None), c)
    assert "AMBIGUOUS_SUPPLIER" in types(amb) and amb.outcome == "blocked"
    unk = E.reconcile(invoice(po, supplier_name_raw="Negev Lighting", supplier_tax_id_raw="599999990"), c)
    assert "UNRECOGNIZED_SUPPLIER" in types(unk)


def test_currency_mismatch_skips_price_checks():
    c, po = ctx()
    inv = invoice(po, currency="USD")
    inv.lines[0].unit_price = Decimal("500")
    t = types(E.reconcile(inv, c))
    assert "CURRENCY_MISMATCH" in t and "PRICE_MISMATCH" not in t


def test_missing_goods_receipt():
    c, po = ctx()
    c = replace(c, receipt_count={})
    assert "MISSING_GOODS_RECEIPT" in types(E.reconcile(invoice(po), c))


def test_ambiguous_description_and_item_not_on_po():
    c, _ = ctx()
    amb_po = c.purchase_orders[1]
    inv = E.InvoiceData(uuid.uuid4(), "כרמל שירותי ניקיון בע\"מ", "513000451", "CC-1", None, "ILS", "PO-2",
                        Decimal("6800"), Decimal(0), Decimal("1224"), Decimal("8024"),
                        [E.InvLine(uuid.uuid4(), 1, "שירותי ניקיון חודשיים - אגף", None, Decimal(1), Decimal("6800"), Decimal(0), Decimal("6800"))])
    res = E.reconcile(inv, c)
    f = next(f for f in res.findings if f.type == "AMBIGUOUS_DESCRIPTION")
    assert f.evidence["price_hint"]["po_line_no"] == 1  # deterministic hint only; still a finding
    assert amb_po.lines
    _, po = ctx()
    inv2 = invoice(po)
    inv2.lines.append(E.InvLine(uuid.uuid4(), 3, "Express delivery", None, Decimal(1), Decimal(50), Decimal(0), Decimal(50)))
    inv2.subtotal += 50
    inv2.total = inv2.subtotal + inv2.tax_amount
    assert "ITEM_NOT_ON_PO" in types(E.reconcile(inv2, c))


def test_arithmetic_and_incomplete_extraction():
    c, po = ctx()
    assert "TOTAL_MISMATCH" in types(E.reconcile(invoice(po, total=Decimal("1")), c))
    inv = invoice(po)
    inv.lines[0].line_total += 5
    assert {"LINE_TOTAL_MISMATCH", "SUBTOTAL_MISMATCH"} <= types(E.reconcile(inv, c))
    res = E.reconcile(invoice(po, total=None, invoice_number=None), c)
    assert "INCOMPLETE_EXTRACTION" in types(res) and res.outcome == "blocked"


def test_security_flags_become_a_finding():
    c, po = ctx()
    res = E.reconcile(invoice(po, security_flags=["ignore all previous instructions"]), c)
    assert "SUSPICIOUS_CONTENT" in types(res) and res.outcome == "discrepancies"


def test_trace_is_complete_and_serializable():
    import json

    c, po = ctx()
    d = E.reconcile(invoice(po), c).to_dict()
    json.dumps(d, default=str)
    assert {ch["check"] for ch in d["checks"]} >= {"supplier_identified", "purchase_order_found", "prices_within_tolerance"}
