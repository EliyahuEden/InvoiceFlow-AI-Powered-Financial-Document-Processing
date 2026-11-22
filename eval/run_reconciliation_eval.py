"""Reconciliation benchmark on controlled scenarios (+ optional end-to-end over demo PDFs).

    backend/.venv/Scripts/python eval/run_reconciliation_eval.py

Each case starts from a correct invoice for a purchase order of the synthetic world and
injects exactly one fault (or a near-miss that must NOT be flagged). Expected findings
are defined by the scenario, independently of the engine. Metrics are reported per
finding type; they are deliberately not merged into one accuracy number.
"""
from __future__ import annotations

import json
import random
import uuid
from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal

from common import DATA, prf, write_result

from app.core.money import round_money
from app.demo.spec import PURCHASE_ORDERS, SUPPLIERS
from app.services.reconciliation import engine as E

SEED = 7
ACTIONABLE = lambda f: f.severity in ("critical", "warning")  # noqa: E731


def world() -> tuple[E.Context, dict, dict]:
    sup_ids = {s.key: uuid.uuid5(uuid.NAMESPACE_URL, f"sup:{s.key}") for s in SUPPLIERS}
    suppliers = [E.SupplierData(sup_ids[s.key], s.name, s.name_en, list(s.aliases), s.tax_id) for s in SUPPLIERS]
    pos, received, receipt_count, po_by_no = [], {}, {}, {}
    for p in PURCHASE_ORDERS:
        pid = uuid.uuid5(uuid.NAMESPACE_URL, f"po:{p.number}")
        lines = [E.POLineData(uuid.uuid5(uuid.NAMESPACE_URL, f"pol:{p.number}:{i}"), i + 1, ln.description, ln.quantity,
                              ln.unit_price, ln.sku) for i, ln in enumerate(p.lines)]
        po = E.POData(pid, p.number, sup_ids[p.supplier], p.currency, "open", lines)
        pos.append(po)
        po_by_no[p.number] = (po, p)
        receipt_count[pid] = len(p.receipts)
        for _, _, qtys in p.receipts:
            for idx, q in qtys.items():
                received[lines[idx].id] = received.get(lines[idx].id, Decimal(0)) + q
    ctx = E.Context(suppliers, pos, received, receipt_count, {}, [], E.Tolerances())
    return ctx, po_by_no, {s.key: s for s in SUPPLIERS}


def clean_invoice(po: E.POData, spec_po, sups: dict, received: dict, rng: random.Random) -> E.InvoiceData:
    sup = sups[spec_po.supplier]
    lines = []
    for i, pl in enumerate(po.lines, start=1):
        qty = received.get(pl.id, pl.quantity) if received.get(pl.id) else pl.quantity
        lines.append(E.InvLine(uuid.uuid4(), i, pl.description, pl.sku, qty, pl.unit_price, Decimal(0),
                               round_money(qty * pl.unit_price)))
    sub = sum((ln.line_total for ln in lines), Decimal(0))
    tax = round_money(sub * Decimal("0.18"))
    return E.InvoiceData(uuid.uuid4(), sup.name, sup.tax_id, f"INV-{rng.randint(10000, 99999)}", None, spec_po.currency,
                         po.number, sub, Decimal(0), tax, sub + tax, lines)


def retotal(inv: E.InvoiceData) -> E.InvoiceData:
    for ln in inv.lines:
        ln.line_total = round_money(ln.quantity * ln.unit_price - (ln.discount or 0))
    sub = sum((ln.line_total for ln in inv.lines), Decimal(0))
    tax = round_money(sub * Decimal("0.18"))
    return replace(inv, subtotal=sub, tax_amount=tax, total=sub + tax)


def cases(ctx: E.Context, po_by_no: dict, sups: dict) -> list[tuple[str, E.InvoiceData, set[str], E.Context]]:
    rng = random.Random(SEED)
    out = []
    received_pos = [(po, sp) for po, sp in po_by_no.values() if ctx.receipt_count[po.id] and
                    all(ctx.received.get(pl.id, 0) >= pl.quantity for pl in po.lines)]
    partial = [(po, sp) for po, sp in po_by_no.values() if ctx.receipt_count[po.id] and
               any(ctx.received.get(pl.id, 0) < pl.quantity for pl in po.lines)]
    no_gr = [(po, sp) for po, sp in po_by_no.values() if ctx.receipt_count[po.id] == 0]

    def base(pair):  # noqa: ANN001, ANN202
        return clean_invoice(pair[0], pair[1], sups, ctx.received, rng)

    for rep in range(3):
        for pair in received_pos:
            po, _ = pair
            out.append(("clean", base(pair), set(), ctx))
            # near miss: +0.5% price, within the 1% tolerance -> must not be flagged
            inv = base(pair)
            ln = rng.choice(inv.lines)
            ln.unit_price = round_money(ln.unit_price * Decimal("1.005"))
            out.append(("price_within_tolerance", retotal(inv), set(), ctx))
            inv = base(pair)
            ln = rng.choice(inv.lines)
            ln.unit_price = round_money(ln.unit_price * Decimal(str(1 + rng.uniform(0.03, 0.15))))
            out.append(("price_mismatch", retotal(inv), {"PRICE_MISMATCH"}, ctx))
            inv = base(pair)
            ln = rng.choice(inv.lines)
            ln.quantity = ln.quantity + rng.randint(1, 5)
            out.append(("quantity_over", retotal(inv), {"QUANTITY_EXCEEDS_ORDERED", "QUANTITY_EXCEEDS_RECEIVED"}, ctx))
            inv = base(pair)
            prior = E.PriorInvoice(uuid.uuid4(), next(s.id for s in ctx.suppliers if s.tax_id == inv.supplier_tax_id_raw),
                                   inv.invoice_number, None, inv.total, "approved")
            out.append(("duplicate", inv, {"DUPLICATE_INVOICE"}, replace(ctx, prior_invoices=[prior])))
            inv = base(pair)
            inv.po_reference = f"PO-2026-{rng.randint(5000, 5999)}"
            out.append(("missing_po_reference_unknown", inv, {"MISSING_PURCHASE_ORDER"}, ctx))
            inv = base(pair)
            inv.currency = "USD" if inv.currency == "ILS" else "ILS"
            out.append(("currency_mismatch", inv, {"CURRENCY_MISMATCH"}, ctx))
            inv = base(pair)
            inv.total = inv.total + Decimal(rng.choice([10, 100, 250]))
            out.append(("total_error", inv, {"TOTAL_MISMATCH"}, ctx))
            inv = base(pair)
            inv.lines.append(E.InvLine(uuid.uuid4(), len(inv.lines) + 1, "Express delivery surcharge / דמי משלוח אקספרס", None,
                                       Decimal(1), Decimal("180.00"), Decimal(0), Decimal("180.00")))
            out.append(("item_not_on_po", retotal(inv), {"ITEM_NOT_ON_PO"}, ctx))
            # robustness: SKU missing and the leading word dropped (the distinguishing attributes such as
            # colour stay, so the line remains unambiguous) -> still matches by description
            inv = base(pair)
            for ln in inv.lines:
                ln.sku = None
                words = ln.description.split()
                if len(words) > 3:
                    ln.description = " ".join(words[1:])
            out.append(("no_sku_paraphrase", inv, set(), ctx))
            inv = base(pair)
            inv.supplier_tax_id_raw = None  # identified by exact name only
            out.append(("supplier_by_name", inv, set(), ctx))
            # Israel allocation number. Labels use the published amounts directly (NIS 5,000 from 2026-06-01,
            # 20,000 in 2025), not the engine's table, so the rule is checked independently.
            def needs_number(inv: E.InvoiceData, limit: int) -> bool:
                return inv.currency == "ILS" and inv.tax_amount > 0 and inv.total - inv.tax_amount > limit
            inv = base(pair)
            inv.invoice_date, inv.allocation_number = date(2026, 9, 1), str(rng.randint(100_000_000, 999_999_999))
            out.append(("allocation_present", inv, set(), ctx))
            inv = base(pair)
            inv.invoice_date = date(2026, 9, 1)
            out.append(("allocation_missing" if needs_number(inv, 5000) else "allocation_not_required", inv,
                        {"MISSING_ALLOCATION_NUMBER"} if needs_number(inv, 5000) else set(), ctx))
            inv = base(pair)
            inv.invoice_date, inv.allocation_number = date(2026, 9, 1), str(rng.randint(10_000, 99_999))
            out.append(("allocation_invalid" if needs_number(inv, 5000) else "allocation_not_required", inv,
                        {"MISSING_ALLOCATION_NUMBER"} if needs_number(inv, 5000) else set(), ctx))
            inv = base(pair)
            inv.invoice_date = date(2025, 6, 1)  # the 2025 threshold was NIS 20,000
            out.append(("allocation_missing_2025" if needs_number(inv, 20000) else "allocation_below_2025_threshold", inv,
                        {"MISSING_ALLOCATION_NUMBER"} if needs_number(inv, 20000) else set(), ctx))
        for pair in partial:
            inv = base(pair)  # billed == received, below ordered: clean partial invoice
            out.append(("clean_partial_delivery", inv, set(), ctx))
            inv = clean_invoice(pair[0], pair[1], sups, {}, rng)  # bills full ordered qty
            out.append(("quantity_exceeds_received", inv, {"QUANTITY_EXCEEDS_RECEIVED"}, ctx))
        for pair in no_gr:
            out.append(("missing_goods_receipt", base(pair), {"MISSING_GOODS_RECEIPT"}, ctx))
        # supplier problems
        inv = base(received_pos[rep % len(received_pos)])
        inv.supplier_name_raw, inv.supplier_tax_id_raw = "כרמל קלין", None
        out.append(("ambiguous_supplier", inv, {"AMBIGUOUS_SUPPLIER"}, ctx))
        inv = base(received_pos[(rep + 1) % len(received_pos)])
        inv.supplier_name_raw, inv.supplier_tax_id_raw = rng.choice(["גלבוע שיווק בע\"מ", "Negev Lighting Ltd"]), "599999990"
        out.append(("unknown_supplier", inv, {"UNRECOGNIZED_SUPPLIER"}, ctx))
        # ambiguous description against the two-wing cleaning PO
        cpo = po_by_no["PO-2026-1006"]
        inv = clean_invoice(cpo[0], cpo[1], sups, ctx.received, rng)
        inv.lines = [E.InvLine(uuid.uuid4(), 1, rng.choice(["שירותי ניקיון חודשיים - אגף", "ניקיון חודשי אגף"]), None,
                               Decimal(1), Decimal("6800.00"), Decimal(0), Decimal("6800.00"))]
        out.append(("ambiguous_description", retotal(inv), {"AMBIGUOUS_DESCRIPTION"}, ctx))
    return out


def evaluate() -> dict:
    ctx, po_by_no, sups = world()
    all_cases = cases(ctx, po_by_no, sups)
    types = sorted({t for _, _, exp, _ in all_cases for t in exp})
    counts = {t: [0, 0, 0] for t in types}
    other_fp: dict[str, int] = defaultdict(int)
    by_scenario: dict[str, dict] = defaultdict(lambda: {"n": 0, "exact": 0})
    clean_n = clean_fp = 0
    failures = []
    for scenario, inv, expected, c in all_cases:
        got = {f.type for f in E.reconcile(inv, c).findings if ACTIONABLE(f)}
        for t in types:
            if t in got and t in expected:
                counts[t][0] += 1
            elif t in got:
                counts[t][1] += 1
            elif t in expected:
                counts[t][2] += 1
        for t in got - set(types):
            other_fp[t] += 1
        exact = got == expected
        by_scenario[scenario]["n"] += 1
        by_scenario[scenario]["exact"] += exact
        if not expected:
            clean_n += 1
            clean_fp += bool(got)
        if not exact and len(failures) < 15:
            failures.append({"scenario": scenario, "expected": sorted(expected), "got": sorted(got)})
    return {
        "cases": len(all_cases),
        "per_type": [{"type": t, **prf(*counts[t])} for t in types],
        "unexpected_other_findings": dict(other_fp),
        "clean_cases": clean_n,
        "clean_case_false_alarm_rate": round(clean_fp / clean_n, 3) if clean_n else None,
        "exact_finding_set_match": round(sum(v["exact"] for v in by_scenario.values()) / len(all_cases), 3),
        "by_scenario": {k: {"n": v["n"], "exact_match": round(v["exact"] / v["n"], 3)} for k, v in sorted(by_scenario.items())},
        "failures": failures,
    }


def end_to_end() -> dict:
    """Demo PDFs → text/OCR → rule-based extraction → engine. Measures compounding pipeline errors."""
    from app.services.documents.text_extraction import OCRUnavailable, extract_pages
    from app.services.extraction import rule_based
    from app.services.extraction.postprocess import normalize

    ctx, _, _ = world()
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    priors: list[E.PriorInvoice] = []
    rows, skipped = [], []
    tp = fp = fn = 0
    for m in manifest["invoices"]:
        data = (DATA / m["file"]).read_bytes()
        try:
            pages = extract_pages(data, "image/png" if m["file"].endswith(".png") else "application/pdf")
        except OCRUnavailable:
            skipped.append(m["file"])
            continue
        n = normalize(rule_based.extract([(p.page_no, p.text) for p in pages], {"520000019"}), pages, "rule_based")
        from app.services.extraction.injection import detect_injection

        inv = E.InvoiceData(uuid.uuid4(), n.supplier_name, n.supplier_tax_id, n.invoice_number, n.invoice_date, n.currency,
                            n.po_reference, n.subtotal, n.discount_total, n.tax_amount, n.total,
                            [E.InvLine(uuid.uuid4(), ln.line_no, ln.description, ln.sku, ln.quantity, ln.unit_price, ln.discount,
                                       ln.line_total) for ln in n.lines],
                            security_flags=detect_injection("\n".join(p.text for p in pages)),
                            allocation_number=n.allocation_number)
        res = E.reconcile(inv, replace(ctx, prior_invoices=list(priors)))
        got = {f.type for f in res.findings if ACTIONABLE(f)}
        expected = set(m["expected_findings"]) | ({"SUSPICIOUS_CONTENT"} if "SUSPICIOUS_INSTRUCTIONS" in m["expected_findings"] else set())
        expected.discard("SUSPICIOUS_INSTRUCTIONS")
        tp += len(got & expected)
        fp += len(got - expected)
        fn += len(expected - got)
        rows.append({"file": m["file"], "scenario": m["scenario"], "expected": sorted(expected), "got": sorted(got),
                     "exact": got == expected})
        if res.supplier_id:
            priors.append(E.PriorInvoice(uuid.uuid4(), uuid.UUID(res.supplier_id), n.invoice_number, n.invoice_date, n.total, "approved"))
    return {"documents": len(rows), "skipped_ocr": skipped, **prf(tp, fp, fn),
            "exact_scenarios": f"{sum(r['exact'] for r in rows)}/{len(rows)}", "rows": rows}


def main() -> None:
    res = evaluate()
    e2e = end_to_end()
    print("cases", res["cases"], "exact", res["exact_finding_set_match"], "clean false-alarm", res["clean_case_false_alarm_rate"])
    for r in res["per_type"]:
        print(f"  {r['type']:28s} P={r['precision']} R={r['recall']}")
    print("e2e", e2e["exact_scenarios"], "P", e2e["precision"], "R", e2e["recall"], "skipped", len(e2e["skipped_ocr"]))
    write_result("reconciliation", {
        "engine_version": E.ENGINE_VERSION, "controlled": res, "end_to_end": e2e,
        "command": "backend/.venv/Scripts/python eval/run_reconciliation_eval.py",
        "notes": ["Controlled cases test the deterministic engine in isolation with exact inputs.",
                  "End-to-end runs the full document pipeline (rule-based extraction) on the 13 demo PDFs, so extraction "
                  "and OCR errors propagate; OCR documents are skipped when Tesseract is unavailable.",
                  "Info-level findings (e.g. UNBILLED_PO_LINES) are excluded from scoring."],
    })


if __name__ == "__main__":
    main()
