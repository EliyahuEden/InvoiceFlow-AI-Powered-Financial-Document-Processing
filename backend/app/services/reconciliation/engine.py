"""Deterministic two-way / three-way invoice reconciliation engine.

Pure functions over plain dataclasses: no database, no network, no LLM. Every finding
carries the expected value, the actual value, the difference, the rule that fired,
and the evidence (record ids) needed to audit it. All arithmetic is Decimal.

Finding types
-------------
UNRECOGNIZED_SUPPLIER, AMBIGUOUS_SUPPLIER, SUPPLIER_BLOCKED, DUPLICATE_INVOICE,
POSSIBLE_DUPLICATE, MISSING_PURCHASE_ORDER, PO_SUPPLIER_MISMATCH, PO_CLOSED,
CURRENCY_MISMATCH, CURRENCY_NOT_STATED, AMBIGUOUS_DESCRIPTION, ITEM_NOT_ON_PO,
PRICE_MISMATCH, QUANTITY_EXCEEDS_ORDERED, QUANTITY_EXCEEDS_RECEIVED,
MISSING_GOODS_RECEIPT, LINE_TOTAL_MISMATCH, SUBTOTAL_MISMATCH, TOTAL_MISMATCH,
UNBILLED_PO_LINES, INCOMPLETE_EXTRACTION, SUSPICIOUS_CONTENT
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from app.core.money import D, round_money, within_tolerance
from app.services.reconciliation.text_match import name_similarity, normalize_doc_number, similarity

ENGINE_VERSION = "recon-1.2"
ZERO = Decimal("0")

SEVERITY = {
    "UNRECOGNIZED_SUPPLIER": "critical", "AMBIGUOUS_SUPPLIER": "critical", "SUPPLIER_BLOCKED": "critical",
    "DUPLICATE_INVOICE": "critical", "POSSIBLE_DUPLICATE": "warning", "MISSING_PURCHASE_ORDER": "critical",
    "PO_SUPPLIER_MISMATCH": "critical", "PO_CLOSED": "warning", "CURRENCY_MISMATCH": "critical",
    "CURRENCY_NOT_STATED": "info", "AMBIGUOUS_DESCRIPTION": "warning", "ITEM_NOT_ON_PO": "critical",
    "PRICE_MISMATCH": "critical", "QUANTITY_EXCEEDS_ORDERED": "critical", "QUANTITY_EXCEEDS_RECEIVED": "critical",
    "MISSING_GOODS_RECEIPT": "critical", "LINE_TOTAL_MISMATCH": "warning", "SUBTOTAL_MISMATCH": "warning",
    "TOTAL_MISMATCH": "critical", "UNBILLED_PO_LINES": "info", "INCOMPLETE_EXTRACTION": "critical",
    "SUSPICIOUS_CONTENT": "warning",
}
BLOCKING = {"UNRECOGNIZED_SUPPLIER", "AMBIGUOUS_SUPPLIER", "DUPLICATE_INVOICE", "MISSING_PURCHASE_ORDER",
            "PO_SUPPLIER_MISMATCH", "SUPPLIER_BLOCKED", "INCOMPLETE_EXTRACTION"}

# Message templates are rendered by the client in the reader's language. Each finding carries a
# message key (its type, or a variant of it) plus these display-ready parameters. The English
# `message` is kept for the API, the audit log and the agent. The contract is enforced against
# frontend/src/lib/i18n/dictionaries.ts by tests/test_finding_messages.py.
MESSAGE_PARAMS: dict[str, set[str]] = {
    "UNRECOGNIZED_SUPPLIER": {"name", "tax_id"},
    "AMBIGUOUS_SUPPLIER": {"name", "count"},
    "SUPPLIER_BLOCKED": {"name"},
    "DUPLICATE_INVOICE": {"number"},
    "DUPLICATE_INVOICE_FILE": set(),
    "POSSIBLE_DUPLICATE": {"total", "number", "days"},
    "MISSING_PURCHASE_ORDER": {"reference"},
    "MISSING_PURCHASE_ORDER_NONE": set(),
    "PO_SUPPLIER_MISMATCH": {"po"},
    "PO_CLOSED": {"po", "status"},
    "CURRENCY_MISMATCH": {"invoice_currency", "po", "po_currency"},
    "CURRENCY_NOT_STATED": {"currency"},
    "AMBIGUOUS_DESCRIPTION": {"line", "description", "first", "second"},
    "ITEM_NOT_ON_PO": {"line", "description", "po"},
    "PRICE_MISMATCH": {"line", "invoice_price", "po_price", "po", "pct", "tolerance_pct", "tolerance_abs"},
    "QUANTITY_EXCEEDS_ORDERED": {"line", "billed", "ordered"},
    "QUANTITY_EXCEEDS_RECEIVED": {"line", "billed", "received"},
    "MISSING_GOODS_RECEIPT": {"po"},
    "LINE_TOTAL_MISMATCH": {"line", "quantity", "unit_price", "expected", "actual"},
    "SUBTOTAL_MISMATCH": {"sum", "subtotal"},
    "TOTAL_MISMATCH": {"expected", "total"},
    "UNBILLED_PO_LINES": {"count"},
    "INCOMPLETE_EXTRACTION": {"missing"},
    "SUSPICIOUS_CONTENT": set(),
}


def amt(v: Decimal | None) -> str | None:
    """Display form of an amount: 5380.0000 -> 5380.00, 0.1250 -> 0.125 (no precision lost)."""
    if v is None:
        return None
    n = v.normalize()
    return f"{v:.2f}" if -n.as_tuple().exponent <= 2 else format(n, "f")


def q(v: Decimal | None) -> str:
    """Human-readable quantity: 60.000 -> 60, 2.500 -> 2.5."""
    if v is None:
        return "?"
    n = v.normalize()
    return format(n, "f") if n == n.to_integral() or "E" not in str(n) else str(v)


# ------------------------------------------------------------------ inputs
@dataclass
class Tolerances:
    price_abs: Decimal = Decimal("0.05")
    price_pct: Decimal = Decimal("1.0")
    quantity_abs: Decimal = Decimal("0")
    total_abs: Decimal = Decimal("1.00")
    line_total_abs: Decimal = Decimal("0.05")
    duplicate_window_days: int = 60
    description_match_min: Decimal = Decimal("0.35")
    description_ambiguity_margin: Decimal = Decimal("0.08")

    @classmethod
    def from_settings(cls, d: dict) -> Tolerances:
        t = cls()
        for k, v in (d or {}).items():
            if hasattr(t, k):
                setattr(t, k, int(v) if k == "duplicate_window_days" else D(v))
        return t


@dataclass
class InvLine:
    id: uuid.UUID | None
    line_no: int
    description: str
    sku: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    discount: Decimal | None = None
    line_total: Decimal | None = None


@dataclass
class InvoiceData:
    id: uuid.UUID | None
    supplier_name_raw: str | None
    supplier_tax_id_raw: str | None
    invoice_number: str | None
    invoice_date: date | None
    currency: str | None
    po_reference: str | None
    subtotal: Decimal | None
    discount_total: Decimal | None
    tax_amount: Decimal | None
    total: Decimal | None
    lines: list[InvLine]
    document_sha256: str | None = None
    supplier_id: uuid.UUID | None = None  # set when a human confirmed the supplier
    security_flags: list[str] = field(default_factory=list)  # e.g. embedded prompt-injection text


@dataclass
class SupplierData:
    id: uuid.UUID
    name: str
    name_en: str | None = None
    aliases: list[str] = field(default_factory=list)
    tax_id: str | None = None
    status: str = "active"


@dataclass
class POLineData:
    id: uuid.UUID
    line_no: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    sku: str | None = None


@dataclass
class POData:
    id: uuid.UUID
    number: str
    supplier_id: uuid.UUID
    currency: str
    status: str
    lines: list[POLineData]


@dataclass
class PriorInvoice:
    id: uuid.UUID
    supplier_id: uuid.UUID | None
    invoice_number: str | None
    invoice_date: date | None
    total: Decimal | None
    status: str
    document_sha256: str | None = None


@dataclass
class Context:
    suppliers: list[SupplierData]
    purchase_orders: list[POData]
    received: dict[uuid.UUID, Decimal]            # po_line_id -> total received
    receipt_count: dict[uuid.UUID, int]           # po_id -> number of goods receipts
    previously_invoiced: dict[uuid.UUID, Decimal]  # po_line_id -> qty billed on other invoices
    prior_invoices: list[PriorInvoice]
    tolerances: Tolerances = field(default_factory=Tolerances)


# ------------------------------------------------------------------ outputs
@dataclass
class Finding:
    type: str
    message: str
    severity: str = ""
    invoice_line_id: str | None = None
    invoice_line_no: int | None = None
    po_line_id: str | None = None
    expected: str | None = None
    actual: str | None = None
    difference: str | None = None
    amount_at_risk: str | None = None
    evidence: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)  # values for the localized template, see MESSAGE_PARAMS
    message_key: str = ""

    def __post_init__(self) -> None:
        self.severity = self.severity or SEVERITY[self.type]
        self.message_key = self.message_key or self.type


@dataclass
class LineMatch:
    invoice_line_no: int
    invoice_line_id: str | None
    po_line_id: str | None
    po_line_no: int | None
    method: str            # sku | description | ambiguous | none
    score: float
    candidates: list[dict] = field(default_factory=list)


@dataclass
class Result:
    engine_version: str
    mode: str
    outcome: str
    supplier_id: str | None
    supplier_match: dict
    purchase_order_id: str | None
    po_match: dict
    findings: list[Finding]
    line_matches: list[LineMatch]
    checks: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ steps
def identify_supplier(inv: InvoiceData, suppliers: list[SupplierData]) -> tuple[SupplierData | None, dict, list[Finding]]:
    if inv.supplier_id:
        s = next((x for x in suppliers if x.id == inv.supplier_id), None)
        if s:
            return s, {"method": "confirmed", "score": 1.0}, []
    tax = (inv.supplier_tax_id_raw or "").strip()
    if tax:
        hits = [s for s in suppliers if s.tax_id and s.tax_id == tax]
        if len(hits) == 1:
            return hits[0], {"method": "tax_id", "score": 1.0, "tax_id": tax}, []
    name = inv.supplier_name_raw or ""
    scored = []
    for s in suppliers:
        best = max([name_similarity(name, n) for n in [s.name, s.name_en or "", *s.aliases] if n] or [0.0])
        scored.append((best, s))
    scored.sort(key=lambda x: -x[0])
    strong = [(sc, s) for sc, s in scored if sc >= 0.75]
    cands = [{"supplier_id": str(s.id), "name": s.name, "score": sc} for sc, s in scored[:3] if sc > 0.3]
    if len(strong) == 1 or (len(strong) > 1 and strong[0][0] - strong[1][0] >= 0.15):
        sc, s = strong[0]
        note = [] if sc >= 0.95 else []
        return s, {"method": "name", "score": sc, "candidates": cands}, note
    if len(strong) > 1:
        return None, {"method": "ambiguous", "candidates": cands}, [Finding(
            "AMBIGUOUS_SUPPLIER",
            f"Supplier '{name}' matches {len(strong)} suppliers and no tax ID is printed; a reviewer must choose.",
            actual=name, evidence={"candidates": cands}, params={"name": name, "count": len(strong)})]
    return None, {"method": "none", "candidates": cands}, [Finding(
        "UNRECOGNIZED_SUPPLIER", f"Supplier '{name or 'unknown'}' (tax ID {tax or 'not printed'}) is not in the supplier master.",
        actual=name or None, evidence={"tax_id": tax or None, "candidates": cands},
        params={"name": name or None, "tax_id": tax or None})]


def find_duplicates(inv: InvoiceData, supplier: SupplierData | None, ctx: Context) -> list[Finding]:
    out: list[Finding] = []
    num = normalize_doc_number(inv.invoice_number)
    for p in ctx.prior_invoices:
        if p.id == inv.id or p.status in ("rejected", "failed"):
            continue
        if inv.document_sha256 and p.document_sha256 == inv.document_sha256:
            out.append(Finding("DUPLICATE_INVOICE", "The identical file was already uploaded.",
                               evidence={"invoice_id": str(p.id), "rule": "same_file_sha256"},
                               message_key="DUPLICATE_INVOICE_FILE"))
            return out
        if supplier and p.supplier_id == supplier.id and num and normalize_doc_number(p.invoice_number) == num:
            out.append(Finding(
                "DUPLICATE_INVOICE",
                f"Invoice {inv.invoice_number} from this supplier was already received.",
                expected="unique (supplier, invoice number)", actual=inv.invoice_number,
                amount_at_risk=str(inv.total) if inv.total is not None else None,
                evidence={"invoice_id": str(p.id), "rule": "same_supplier_and_number"},
                params={"number": inv.invoice_number}))
            return out
    for p in ctx.prior_invoices:
        if p.id == inv.id or p.status in ("rejected", "failed") or not supplier or p.supplier_id != supplier.id:
            continue
        if (inv.total is not None and p.total == inv.total and inv.invoice_date and p.invoice_date
                and abs((inv.invoice_date - p.invoice_date).days) <= ctx.tolerances.duplicate_window_days):
            out.append(Finding(
                "POSSIBLE_DUPLICATE",
                f"Same supplier and same total ({amt(inv.total)}) as invoice {p.invoice_number} within "
                f"{ctx.tolerances.duplicate_window_days} days.",
                evidence={"invoice_id": str(p.id), "rule": "same_supplier_total_window"},
                params={"total": amt(inv.total), "number": p.invoice_number,
                        "days": ctx.tolerances.duplicate_window_days}))
    return out


def _line_score(il: InvLine, pl: POLineData) -> tuple[str, float]:
    if il.sku and pl.sku and normalize_doc_number(il.sku) == normalize_doc_number(pl.sku):
        return "sku", 1.0
    return "description", similarity(il.description, pl.description)


def resolve_po(inv: InvoiceData, supplier: SupplierData, ctx: Context) -> tuple[POData | None, dict, list[Finding]]:
    pos = ctx.purchase_orders
    if inv.po_reference:
        ref = normalize_doc_number(inv.po_reference)
        po = next((p for p in pos if normalize_doc_number(p.number) == ref), None)
        if po is None:
            return None, {"method": "reference", "reference": inv.po_reference}, [Finding(
                "MISSING_PURCHASE_ORDER", f"The invoice references {inv.po_reference}, which does not exist.",
                actual=inv.po_reference, evidence={"rule": "referenced_po_not_found"},
                params={"reference": inv.po_reference})]
        if po.supplier_id != supplier.id:
            return po, {"method": "reference"}, [Finding(
                "PO_SUPPLIER_MISMATCH", f"{po.number} belongs to a different supplier.",
                actual=inv.po_reference, evidence={"po_id": str(po.id)}, params={"po": po.number})]
        return po, {"method": "reference", "reference": inv.po_reference}, []
    # No reference: look for an open PO of this supplier whose lines cover the invoice.
    best, best_score = None, 0.0
    for p in pos:
        if p.supplier_id != supplier.id or p.status in ("closed", "cancelled"):
            continue
        scores = [max((_line_score(il, pl)[1] for pl in p.lines), default=0.0) for il in inv.lines]
        cover = sum(1 for s in scores if s >= float(ctx.tolerances.description_match_min)) / max(1, len(scores))
        if cover > best_score:
            best, best_score = p, cover
    if best is not None and best_score >= 0.75:
        return best, {"method": "inferred_from_lines", "coverage": best_score}, []
    return None, {"method": "none"}, [Finding(
        "MISSING_PURCHASE_ORDER", "No purchase order is referenced and no open PO of this supplier covers the invoice lines.",
        evidence={"rule": "no_po_reference_no_matching_open_po", "best_coverage": best_score},
        message_key="MISSING_PURCHASE_ORDER_NONE")]


def match_lines(inv: InvoiceData, po: POData, tol: Tolerances) -> tuple[list[LineMatch], list[Finding]]:
    matches: list[LineMatch] = []
    findings: list[Finding] = []
    used: set[uuid.UUID] = set()
    for il in inv.lines:
        scored = sorted(((*_line_score(il, pl), pl) for pl in po.lines if pl.id not in used),
                        key=lambda x: -x[1])
        cands = [{"po_line_id": str(pl.id), "po_line_no": pl.line_no, "description": pl.description,
                  "unit_price": str(pl.unit_price), "score": sc} for _, sc, pl in scored[:3]]
        if not scored or scored[0][1] < float(tol.description_match_min):
            matches.append(LineMatch(il.line_no, str(il.id) if il.id else None, None, None, "none",
                                     scored[0][1] if scored else 0.0, cands))
            findings.append(Finding("ITEM_NOT_ON_PO", f"Line {il.line_no} '{il.description}' does not match any line of {po.number}.",
                                    invoice_line_id=str(il.id) if il.id else None, invoice_line_no=il.line_no,
                                    amount_at_risk=str(il.line_total) if il.line_total is not None else None,
                                    evidence={"candidates": cands},
                                    params={"line": il.line_no, "description": il.description, "po": po.number}))
            continue
        method, score, pl = scored[0]
        if method != "sku" and len(scored) > 1 and scored[0][1] - scored[1][1] < float(tol.description_ambiguity_margin):
            # Deterministic tie-break hint only: a candidate with the identical unit price.
            price_hits = [c for c in cands[:2] if il.unit_price is not None and D(c["unit_price"]) == il.unit_price]
            hint = price_hits[0] if len(price_hits) == 1 else None
            matches.append(LineMatch(il.line_no, str(il.id) if il.id else None, None, None, "ambiguous", score, cands))
            findings.append(Finding(
                "AMBIGUOUS_DESCRIPTION",
                f"Line {il.line_no} '{il.description}' matches several PO lines almost equally "
                f"({cands[0]['description']} / {cands[1]['description']}).",
                invoice_line_id=str(il.id) if il.id else None, invoice_line_no=il.line_no,
                evidence={"candidates": cands[:2], "price_hint": hint},
                params={"line": il.line_no, "description": il.description,
                        "first": cands[0]["description"], "second": cands[1]["description"]}))
            continue
        used.add(pl.id)
        matches.append(LineMatch(il.line_no, str(il.id) if il.id else None, str(pl.id), pl.line_no, method, score, cands))
    return matches, findings


def tax_inclusive_factor(inv: InvoiceData, tol: Tolerances) -> Decimal | None:
    """Net/gross factor when line prices include VAT (retail invoices): the lines then sum to the
    total rather than the subtotal. Purchase orders are net, so prices are compared net."""
    totals = [il.line_total for il in inv.lines]
    if not totals or any(t is None for t in totals) or not inv.total or inv.tax_amount is None:
        return None
    s = sum(totals, ZERO)
    if abs(s - inv.total) <= tol.total_abs and (inv.subtotal is None or abs(s - inv.subtotal) > tol.total_abs):
        return (inv.total - inv.tax_amount) / inv.total
    return None


def check_lines(inv: InvoiceData, po: POData, matches: list[LineMatch], ctx: Context, mode: str,
                currency_ok: bool) -> list[Finding]:
    tol = ctx.tolerances
    out: list[Finding] = []
    po_lines = {str(pl.id): pl for pl in po.lines}
    by_no = {il.line_no: il for il in inv.lines}
    no_receipts = ctx.receipt_count.get(po.id, 0) == 0
    gross = tax_inclusive_factor(inv, tol)
    if mode == "three_way" and no_receipts:
        out.append(Finding("MISSING_GOODS_RECEIPT",
                           f"No goods receipt has been recorded for {po.number}; nothing can be confirmed as delivered.",
                           amount_at_risk=str(inv.subtotal) if inv.subtotal is not None else None,
                           evidence={"po_id": str(po.id), "rule": "three_way_requires_receipt"}, params={"po": po.number}))
    for m in matches:
        if not m.po_line_id:
            continue
        il, pl = by_no[m.invoice_line_no], po_lines[m.po_line_id]
        ref = dict(invoice_line_id=m.invoice_line_id, invoice_line_no=il.line_no, po_line_id=m.po_line_id)
        price = None if il.unit_price is None else (
            (il.unit_price * gross).quantize(Decimal("0.0001")) if gross else il.unit_price)
        if currency_ok and price is not None and not within_tolerance(pl.unit_price, price, tol.price_abs, tol.price_pct):
            diff = price - pl.unit_price
            pct = (diff / pl.unit_price * 100).quantize(Decimal("0.01")) if pl.unit_price else None
            qty = il.quantity or ZERO
            out.append(Finding(
                "PRICE_MISMATCH",
                f"Line {il.line_no}: unit price {amt(price)} vs {amt(pl.unit_price)} on {po.number} "
                f"({'+' if diff > 0 else ''}{pct}%), tolerance {tol.price_pct}% / {tol.price_abs}.",
                expected=amt(pl.unit_price), actual=amt(price), difference=amt(diff),
                amount_at_risk=str(round_money(max(diff, ZERO) * qty)),
                evidence={"pct": str(pct), "tolerance_pct": str(tol.price_pct), "tolerance_abs": str(tol.price_abs),
                          "compared_net_of_vat": gross is not None},
                params={"line": il.line_no, "invoice_price": amt(price), "po_price": amt(pl.unit_price),
                        "po": po.number, "pct": None if pct is None else f"{'+' if diff > 0 else ''}{pct}",
                        "tolerance_pct": str(tol.price_pct), "tolerance_abs": str(tol.price_abs)}, **ref))
        if il.quantity is not None:
            billed = il.quantity + ctx.previously_invoiced.get(pl.id, ZERO)
            if billed > pl.quantity + tol.quantity_abs:
                excess = billed - pl.quantity
                out.append(Finding(
                    "QUANTITY_EXCEEDS_ORDERED",
                    f"Line {il.line_no}: cumulative billed quantity {q(billed)} exceeds ordered {q(pl.quantity)}.",
                    expected=q(pl.quantity), actual=q(billed), difference=q(excess),
                    amount_at_risk=str(round_money(excess * (il.unit_price or pl.unit_price))),
                    evidence={"previously_invoiced": str(ctx.previously_invoiced.get(pl.id, ZERO))},
                    params={"line": il.line_no, "billed": q(billed), "ordered": q(pl.quantity)}, **ref))
            if mode == "three_way" and not no_receipts:
                received = ctx.received.get(pl.id, ZERO)
                if billed > received + tol.quantity_abs:
                    excess = billed - received
                    out.append(Finding(
                        "QUANTITY_EXCEEDS_RECEIVED",
                        f"Line {il.line_no}: billed {q(billed)} but only {q(received)} received on goods receipts.",
                        expected=q(received), actual=q(billed), difference=q(excess),
                        amount_at_risk=str(round_money(excess * (il.unit_price or pl.unit_price))),
                        evidence={"received": str(received),
                                  "previously_invoiced": str(ctx.previously_invoiced.get(pl.id, ZERO))},
                        params={"line": il.line_no, "billed": q(billed), "received": q(received)}, **ref))
    matched_ids = {m.po_line_id for m in matches if m.po_line_id}
    unbilled = [pl for pl in po.lines if str(pl.id) not in matched_ids and ctx.previously_invoiced.get(pl.id, ZERO) < pl.quantity]
    if unbilled and not any(m.method == "ambiguous" for m in matches):
        out.append(Finding("UNBILLED_PO_LINES", f"{len(unbilled)} PO line(s) not billed on this invoice (partial billing).",
                           evidence={"po_line_ids": [str(p.id) for p in unbilled]}, params={"count": len(unbilled)}))
    return out


def check_arithmetic(inv: InvoiceData, tol: Tolerances) -> list[Finding]:
    out: list[Finding] = []
    for il in inv.lines:
        if il.quantity is None or il.unit_price is None or il.line_total is None:
            continue
        expected = round_money(il.quantity * il.unit_price - (il.discount or ZERO))
        if abs(expected - il.line_total) > tol.line_total_abs:
            out.append(Finding("LINE_TOTAL_MISMATCH",
                               f"Line {il.line_no}: {q(il.quantity)} × {amt(il.unit_price)} = {amt(expected)}, invoice shows {amt(il.line_total)}.",
                               invoice_line_id=str(il.id) if il.id else None, invoice_line_no=il.line_no,
                               expected=amt(expected), actual=amt(il.line_total), difference=amt(il.line_total - expected),
                               params={"line": il.line_no, "quantity": q(il.quantity), "unit_price": amt(il.unit_price),
                                       "expected": amt(expected), "actual": amt(il.line_total)}))
    line_totals = [il.line_total for il in inv.lines]
    if inv.subtotal is not None and line_totals and all(t is not None for t in line_totals)             and tax_inclusive_factor(inv, tol) is None:  # VAT-inclusive lines legitimately sum to the total
        s = sum(line_totals, ZERO)
        if abs(s - inv.subtotal) > tol.total_abs:
            out.append(Finding("SUBTOTAL_MISMATCH", f"Lines sum to {amt(s)}; subtotal shows {amt(inv.subtotal)}.",
                               expected=amt(s), actual=amt(inv.subtotal), difference=amt(inv.subtotal - s),
                               params={"sum": amt(s), "subtotal": amt(inv.subtotal)}))
    if inv.subtotal is not None and inv.tax_amount is not None and inv.total is not None:
        expected = inv.subtotal - (inv.discount_total or ZERO) + inv.tax_amount
        if abs(expected - inv.total) > tol.total_abs:
            out.append(Finding("TOTAL_MISMATCH", f"Subtotal − discount + tax = {amt(expected)}; total shows {amt(inv.total)}.",
                               expected=amt(expected), actual=amt(inv.total), difference=amt(inv.total - expected),
                               amount_at_risk=str(max(inv.total - expected, ZERO)),
                               params={"expected": amt(expected), "total": amt(inv.total)}))
    return out


def reconcile(inv: InvoiceData, ctx: Context, mode: str = "three_way") -> Result:
    checks: list[dict] = []
    findings: list[Finding] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": passed, "detail": detail})

    missing = [n for n, v in (("invoice_number", inv.invoice_number), ("total", inv.total)) if v in (None, "")]
    if not inv.lines:
        missing.append("line_items")
    if missing:
        findings.append(Finding("INCOMPLETE_EXTRACTION",
                                f"Required data is missing ({', '.join(missing)}); correct the extraction before matching.",
                                evidence={"missing": missing}, params={"missing": ", ".join(missing)}))
    check("required_fields_present", not missing, ",".join(missing))
    if inv.security_flags:
        findings.append(Finding("SUSPICIOUS_CONTENT",
                                "The document contains instruction-like text aimed at automated systems. It was ignored; "
                                "a reviewer should verify the invoice with the supplier through a known channel.",
                                evidence={"snippets": inv.security_flags[:3]}))

    supplier, sup_match, f = identify_supplier(inv, ctx.suppliers)
    findings += f
    check("supplier_identified", supplier is not None, sup_match.get("method", ""))
    if supplier and supplier.status == "blocked":
        findings.append(Finding("SUPPLIER_BLOCKED", f"Supplier {supplier.name} is blocked for payment.",
                                params={"name": supplier.name}))

    dups = find_duplicates(inv, supplier, ctx)
    findings += dups
    check("not_duplicate", not any(d.type == "DUPLICATE_INVOICE" for d in dups))
    findings += check_arithmetic(inv, ctx.tolerances)
    check("document_arithmetic", not any(x.type.endswith("TOTAL_MISMATCH") for x in findings))

    po, po_match, matches = None, {"method": "skipped"}, []
    is_duplicate = any(d.type == "DUPLICATE_INVOICE" for d in dups)
    if is_duplicate:
        # A confirmed re-submission is blocked; matching its lines again would only add
        # cumulative-quantity noise caused by the original invoice.
        check("line_checks", True, "skipped: duplicate invoice")
    if supplier is not None and not is_duplicate:
        po, po_match, f = resolve_po(inv, supplier, ctx)
        findings += f
        check("purchase_order_found", po is not None and not f, po_match.get("method", ""))
    if po is not None and not any(x.type == "PO_SUPPLIER_MISMATCH" for x in findings):
        currency_ok = True
        if not inv.currency:
            findings.append(Finding("CURRENCY_NOT_STATED", f"Invoice does not state a currency; assuming PO currency "
                                                           f"{po.currency} for comparison only.",
                                    expected=po.currency, params={"currency": po.currency}))
        elif inv.currency != po.currency:
            currency_ok = False
            findings.append(Finding("CURRENCY_MISMATCH", f"Invoice currency {inv.currency} differs from {po.number} "
                                                         f"currency {po.currency}; price comparison skipped.",
                                    expected=po.currency, actual=inv.currency,
                                    amount_at_risk=str(inv.total) if inv.total is not None else None,
                                    params={"invoice_currency": inv.currency, "po": po.number,
                                            "po_currency": po.currency}))
        check("currency_consistent", currency_ok)
        if po.status in ("closed", "cancelled"):
            findings.append(Finding("PO_CLOSED", f"{po.number} is {po.status}.",
                                    params={"po": po.number, "status": po.status}))
        matches, f = match_lines(inv, po, ctx.tolerances)
        findings += f
        check("all_lines_matched", all(m.po_line_id for m in matches))
        findings += check_lines(inv, po, matches, ctx, mode, currency_ok)
        check("prices_within_tolerance", not any(x.type == "PRICE_MISMATCH" for x in findings))
        check("quantities_within_order", not any(x.type == "QUANTITY_EXCEEDS_ORDERED" for x in findings))
        if mode == "three_way":
            check("quantities_received", not any(x.type in ("QUANTITY_EXCEEDS_RECEIVED", "MISSING_GOODS_RECEIPT")
                                                 for x in findings))

    types = {x.type for x in findings}
    if types & BLOCKING:
        outcome = "blocked"
    elif any(x.severity in ("critical", "warning") for x in findings):
        outcome = "discrepancies"
    else:
        outcome = "matched"
    return Result(
        engine_version=ENGINE_VERSION, mode=mode, outcome=outcome,
        supplier_id=str(supplier.id) if supplier else None, supplier_match=sup_match,
        purchase_order_id=str(po.id) if po else None, po_match=po_match,
        findings=findings, line_matches=matches, checks=checks,
    )
