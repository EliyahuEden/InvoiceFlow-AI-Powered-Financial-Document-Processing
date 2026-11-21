"""Rules-first extraction with a targeted LLM fallback.

The free rule-based extractor runs on every invoice. Its result is normalized and checked
(provenance, parsing, arithmetic); the LLM is called only when something is open, and is asked
only for those fields. Its answer is merged in only when it leaves fewer open problems than the
rules did, and every value still has to be printed in the document (postprocess.normalize).
Most invoices therefore cost no LLM call, and a weak or slow model can never make a clean
rules result worse.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.money import round_money
from app.services.documents.text_extraction import PageText
from app.services.extraction.llm_extractor import extract_with_llm
from app.services.extraction.parsing import parse_tax_id
from app.services.extraction.postprocess import TOL, normalize
from app.services.extraction.schema import FIELD_NAMES, InvoiceExtraction, NormalizedInvoice
from app.services.llm.provider import LLMResult

# Which fields to re-ask when a consistency check fails.
ISSUE_GAPS = {
    "TOTAL_MISMATCH": ["subtotal", "tax_amount", "total"],
    "SUBTOTAL_MISMATCH": ["subtotal", "line_items"],
    "LINE_ARITHMETIC": ["line_items"],
    "TAX_RATE_MISMATCH": ["tax_rate", "tax_amount"],
}


# Missing fields that do not call the model on their own: currency is often not printed at all or
# lost by OCR (the ₪ sign), and a text-only model cannot recover it. On the benchmark, 12 calls made
# only for a missing currency fixed nothing. It is still reported as missing to the reviewer.
NOT_ASKED_ALONE = {"currency"}


@dataclass
class HybridOutcome:
    extraction: InvoiceExtraction
    method: str
    gaps: list[str] = field(default_factory=list)
    filled: list[str] = field(default_factory=list)
    llm_result: LLMResult | None = None
    retries: int = 0
    error: str | None = None


def find_gaps(norm: NormalizedInvoice) -> list[str]:
    """Fields worth asking the LLM about: required fields that are missing, a missing item
    table, values the document does not contain, and figures that do not add up."""
    gaps: list[str] = []

    def add(name: str) -> None:
        if name not in gaps:
            gaps.append(name)

    for name in norm.missing_fields:
        if name not in NOT_ASKED_ALONE:
            add(name)
    if not norm.lines:
        add("line_items")
    for issue in norm.issues:
        if issue.code in ("UNVERIFIED_VALUE", "UNPARSEABLE_VALUE") and issue.field in FIELD_NAMES:
            add(issue.field)
        for name in ISSUE_GAPS.get(issue.code, []):
            add(name)
    if norm.total is not None and not _total_confirmed(norm):
        for name in ("subtotal", "tax_amount", "total"):
            if name == "total" or getattr(norm, name) is None:
                add(name)
    return gaps


def _total_confirmed(norm: NormalizedInvoice) -> bool:
    """Whether anything on the invoice backs up the total. With subtotal and VAT both read,
    check_arithmetic already compares them; otherwise the total needs another witness."""
    if norm.subtotal is not None and norm.tax_amount is not None:
        return True
    near = lambda a, b: abs(a - b) <= TOL  # noqa: E731
    if norm.subtotal is not None and near(norm.subtotal - (norm.discount_total or 0), norm.total):
        return True  # VAT-free receipt
    if norm.subtotal is not None and norm.tax_rate is not None and near(
            round_money((norm.subtotal - (norm.discount_total or 0)) * (1 + norm.tax_rate / 100)), norm.total):
        return True
    totals = [ln.line_total for ln in norm.lines]
    return bool(totals) and None not in totals and near(sum(totals), norm.total)  # VAT-inclusive lines


def _apply(base: InvoiceExtraction, answer: InvoiceExtraction, names: list[str]) -> InvoiceExtraction:
    update: dict = {}
    for name in names:
        if name == "line_items":
            if answer.line_items:
                update["line_items"] = answer.line_items
        elif (v := getattr(answer, name)).value and str(v.value).strip():
            update[name] = v
    return base.model_copy(update=update)


def _line_key(norm: NormalizedInvoice) -> list[tuple]:
    return [(ln.description, ln.quantity, ln.unit_price, ln.line_total) for ln in norm.lines]


def extract_rules_first(llm, pages: list[PageText], rules_ex: InvoiceExtraction,  # noqa: ANN001
                        exclude_tax_ids: set[str] | None = None) -> HybridOutcome:
    def check(ex: InvoiceExtraction) -> tuple[NormalizedInvoice, int]:
        n = normalize(ex, pages, "rule_based")
        return n, len(find_gaps(n))

    rules_norm, _ = check(rules_ex)
    gaps = find_gaps(rules_norm)
    if not gaps or llm is None:
        return HybridOutcome(rules_ex, "rule_based", gaps)
    try:
        answer, result, retries = extract_with_llm(llm, pages, fields=gaps)
    except Exception as exc:  # noqa: BLE001 - any provider failure keeps the rules result
        return HybridOutcome(rules_ex, "rule_based", gaps, error=str(exc))
    if answer.supplier_tax_id.value and parse_tax_id(answer.supplier_tax_id.value) in (exclude_tax_ids or set()):
        answer.supplier_tax_id = rules_ex.supplier_tax_id  # never the customer's own tax ID

    best, (best_norm, best_open) = rules_ex, (rules_norm, len(gaps))
    candidate = _apply(rules_ex, answer, gaps)
    norm, open_ = check(candidate)
    if open_ < best_open:
        best, best_norm, best_open = candidate, norm, open_
    else:  # the answer as a whole did not help: keep any single field that does
        for name in gaps:
            candidate = _apply(best, answer, [name])
            norm, open_ = check(candidate)
            if open_ < best_open:
                best, best_norm, best_open = candidate, norm, open_

    filled = [name for name in gaps
              if (_line_key(best_norm) != _line_key(rules_norm) if name == "line_items"
                  else getattr(best_norm, name) is not None and getattr(best_norm, name) != getattr(rules_norm, name))]
    method = f"rules+llm:{llm.model}"[:40] if filled else "rule_based"
    return HybridOutcome(best, method, gaps, filled, result, retries)
