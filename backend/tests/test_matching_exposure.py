"""Audit FIN-05 (Unicode-safe, unique, order-independent matching) and FIN-07 (one exposure per line)."""
from __future__ import annotations

import uuid
from decimal import Decimal as Dc

import pytest

from app.services.reconciliation import engine as E
from app.services.reconciliation.text_match import normalize_doc_number

S1, S2 = uuid.uuid4(), uuid.uuid4()
SUPPLIERS = [E.SupplierData(S1, "חרמון קלייה בע\"מ", "Hermon Coffee", [], "515000238"),
             E.SupplierData(S2, "תבור ציוד משרדי בע\"מ", "Tavor Office", [], "514000127")]


def po(number, lines, supplier=S1, status="open"):  # noqa: ANN001, ANN201
    return E.POData(uuid.uuid4(), number, supplier, "ILS", status,
                    [E.POLineData(uuid.uuid4(), i, d, Dc(q), Dc(p), sku) for i, (d, q, p, sku) in enumerate(lines, 1)])


def inv(lines, po_ref=None):  # noqa: ANN001, ANN201
    ls = [E.InvLine(uuid.uuid4(), i, d, sku, Dc(q), Dc(p), Dc(0), (Dc(q) * Dc(p)).quantize(Dc("0.01")))
          for i, (d, q, p, sku) in enumerate(lines, 1)]
    sub = sum((x.line_total for x in ls), Dc(0))
    tax = (sub * Dc("0.18")).quantize(Dc("0.01"))
    return E.InvoiceData(uuid.uuid4(), "חרמון קלייה בע\"מ", "515000238", "INV-1", None, "ILS", po_ref, sub, Dc(0), tax,
                         sub + tax, ls)


def run(invoice, pos, received=None, previously=None, mode="three_way"):  # noqa: ANN001, ANN201
    receipts = {p.id: 1 for p in pos}
    rec = received if received is not None else {pl.id: pl.quantity for p in pos for pl in p.lines}
    ctx = E.Context(SUPPLIERS, pos, rec, receipts, previously or {}, [])
    return E.reconcile(invoice, ctx, mode=mode)


def both_orders(invoice, pos, **kw):  # noqa: ANN001, ANN201
    """FIN-05: the outcome must not depend on the order records come back from the database."""
    a, b = run(invoice, list(pos), **kw), run(invoice, list(reversed(pos)), **kw)
    key = lambda r: (r.purchase_order_id, sorted((f.type, f.invoice_line_no) for f in r.findings),  # noqa: E731
                     [(m.invoice_line_no, m.po_line_id, m.method) for m in r.line_matches])
    assert key(a) == key(b)
    return a


# ---------------------------------------------------------------- FIN-05
def test_hebrew_identifiers_are_kept_when_normalizing():
    assert normalize_doc_number("הז-2026/12") == "הז202612"
    assert normalize_doc_number("PO-2026-1001") == normalize_doc_number("po 2026 1001")
    assert normalize_doc_number("קפה-א") != normalize_doc_number("קפה-ב")


def test_hebrew_only_skus_match_their_own_line_only():
    p = po("PO-1", [("פולי קפה כהה", 10, 100, "קפה-א"), ("פולי קפה בהיר", 10, 90, "קפה-ב")])
    r = both_orders(inv([("פולי קפה בהיר", 10, 90, "קפה-ב")], "PO-1"), [p])
    m = r.line_matches[0]
    assert (m.method, m.po_line_no) == ("sku", 2)


def test_a_hebrew_only_po_reference_is_not_matched_to_another_hebrew_po():
    a = po("הזמנה-א", [("קפה", 10, 100, None)])
    b = po("הזמנה-ב", [("קפה", 10, 100, None)])
    r = both_orders(inv([("קפה", 10, 100, None)], "הזמנה-ב"), [a, b])
    assert r.purchase_order_id == str(b.id)


def test_a_reference_shared_by_two_suppliers_resolves_to_the_invoice_supplier():
    ours = po("PO-1001", [("קפה", 10, 100, None)], supplier=S1)
    theirs = po("PO 1001", [("נייר", 10, 20, None)], supplier=S2)
    r = both_orders(inv([("קפה", 10, 100, None)], "PO-1001"), [theirs, ours])
    assert r.purchase_order_id == str(ours.id)


def test_two_purchase_orders_with_the_same_reference_are_ambiguous():
    a = po("PO-1001", [("קפה", 10, 100, None)])
    b = po("PO 1001", [("קפה", 10, 100, None)])
    r = both_orders(inv([("קפה", 10, 100, None)], "PO-1001"), [a, b])
    assert r.purchase_order_id is None and r.outcome == "blocked"
    f = next(f for f in r.findings if f.type == "AMBIGUOUS_PURCHASE_ORDER")
    assert f.params == {"reference": "PO-1001", "count": 2}


def test_two_open_orders_that_cover_the_lines_equally_are_not_picked_by_order():
    a = po("PO-1", [("פולי קפה אספרסו", 10, 100, "HC-ESP")])
    b = po("PO-2", [("פולי קפה אספרסו", 10, 100, "HC-ESP")])
    r = both_orders(inv([("פולי קפה אספרסו", 10, 100, "HC-ESP")]), [a, b])
    assert r.purchase_order_id is None
    f = next(f for f in r.findings if f.type == "AMBIGUOUS_PURCHASE_ORDER")
    assert f.message_key == "AMBIGUOUS_PURCHASE_ORDER_INFERRED" and f.params == {"count": 2}


def test_a_repeated_sku_is_resolved_by_unit_price():
    p = po("PO-1", [("נייר A4 לבן", 10, 20, "PAP-A4"), ("נייר A4 לבן מבצע", 10, 18, "PAP-A4")])
    r = both_orders(inv([("נייר A4 לבן", 10, 18, "PAP-A4")], "PO-1"), [p])
    assert r.line_matches[0].po_line_no == 2


def test_a_repeated_sku_without_a_price_match_is_ambiguous():
    p = po("PO-1", [("נייר A4 לבן", 10, 20, "PAP-A4"), ("נייר A4 לבן מבצע", 10, 18, "PAP-A4")])
    r = both_orders(inv([("נייר A4", 10, 19, "PAP-A4")], "PO-1"), [p])
    assert r.line_matches[0].method == "ambiguous"
    assert "AMBIGUOUS_DESCRIPTION" in {f.type for f in r.findings}


# ---------------------------------------------------------------- FIN-07
def _risk(r, line=1):  # noqa: ANN001, ANN202
    return sum((Dc(f.amount_at_risk) for f in r.findings if f.invoice_line_no == line and f.amount_at_risk), Dc(0))


def test_a_line_over_both_ordered_and_received_is_counted_once():
    p = po("PO-1", [("קפה", 60, 118, "HC")])
    r = run(inv([("קפה", 80, 118, "HC")], "PO-1"), [p], received={p.lines[0].id: Dc(40)})
    types = {f.type for f in r.findings}
    assert {"QUANTITY_EXCEEDS_ORDERED", "QUANTITY_EXCEEDS_RECEIVED"} <= types
    assert _risk(r) == Dc("4720.00")  # 40 unbilled-for units × 118, not (20 + 40) × 118


def test_price_and_quantity_excess_on_one_line_do_not_overlap():
    p = po("PO-1", [("קפה", 80, 118, "HC")])
    r = run(inv([("קפה", 80, 120, "HC")], "PO-1"), [p], received={p.lines[0].id: Dc(40)})
    # 40 unreceived units at the invoiced 120, plus the +2 price difference on the 40 received units
    assert _risk(r) == Dc("4880.00")


def test_risk_never_exceeds_what_this_invoice_bills_for_the_line():
    p = po("PO-1", [("קפה", 60, 100, "HC")])
    r = run(inv([("קפה", 10, 100, "HC")], "PO-1"), [p], previously={p.lines[0].id: Dc(100)})
    assert _risk(r) == Dc("1000.00")  # 10 × 100: earlier invoices' excess is not this invoice's money


def test_each_finding_still_states_its_own_rule():
    p = po("PO-1", [("קפה", 60, 118, "HC")])
    r = run(inv([("קפה", 80, 118, "HC")], "PO-1"), [p], received={p.lines[0].id: Dc(40)})
    ordered = next(f for f in r.findings if f.type == "QUANTITY_EXCEEDS_ORDERED")
    assert ordered.params == {"line": 1, "billed": "80", "ordered": "60"}
    assert ordered.evidence.get("risk_counted_in") == "QUANTITY_EXCEEDS_RECEIVED"


@pytest.mark.integration
def test_dashboard_risk_is_reported_per_currency(client, as_user):
    from tests.conftest import upload_invoice

    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    k = client.get("/api/dashboard", headers=fin).json()["kpis"]
    assert isinstance(k["amount_at_risk_by_currency"], dict) and "ILS" in k["amount_at_risk_by_currency"]
    assert k["amount_at_risk"] == k["amount_at_risk_by_currency"]["ILS"]  # base currency only, never a mixed sum
