"""Deterministic post-processing of extractor output.

1. Provenance verification: every value must appear verbatim in the document text.
   Values that cannot be found are discarded (reported as missing) - the system never
   keeps a value the document does not contain, whichever extractor produced it.
2. Typed parsing: Decimal amounts, ISO dates, normalized currency and tax ID.
3. Source location: map each value to word bounding boxes for UI highlighting.
4. Arithmetic consistency checks (line totals, subtotal, tax, total) using Decimal.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from app.core.money import parse_amount, round_money
from app.services.documents.text_extraction import PageText
from app.services.extraction.parsing import normalize_currency, parse_date, parse_percent, parse_tax_id
from app.services.extraction.schema import (
    DATE_FIELDS,
    FIELD_NAMES,
    MONEY_FIELDS,
    FieldSource,
    InvoiceExtraction,
    NormalizedInvoice,
    NormalizedLine,
    ValidationIssue,
)

REQUIRED_FIELDS = ["supplier_name", "invoice_number", "invoice_date", "total"]
TOL = Decimal("0.02")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[‎‏‪-‮⁦-⁩]", "", s)
    s = s.replace("״", '"').replace("׳", "'").replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", "", s).lower()


def _locate(value: str, pages: list[PageText], prefer_page: int | None) -> FieldSource | None:
    """Find the value in the document; return page, line text and union bbox of matching words."""
    nv = _norm(value)
    if not nv:
        return None
    ordered = sorted(pages, key=lambda p: (p.page_no != prefer_page, p.page_no))
    for p in ordered:
        if nv not in _norm(p.text):
            continue
        lines: dict[int, list] = {}
        for w in p.words:
            lines.setdefault(w.l, []).append(w)
        for _, words in sorted(lines.items()):
            joined = _norm("".join(w.t for w in words))
            if nv not in joined:
                continue
            hits = [w for w in words if _norm(w.t) and (_norm(w.t) in nv or nv in _norm(w.t))] or words
            bbox = [min(w.b[0] for w in hits), min(w.b[1] for w in hits),
                    max(w.b[2] for w in hits), max(w.b[3] for w in hits)]
            line_text = " ".join(w.t for w in sorted(words, key=lambda w: -w.b[0]))
            src_line = next((ln for ln in p.text.splitlines() if nv in _norm(ln)), line_text)
            return FieldSource(page=p.page_no, text=src_line, bbox=bbox, verified=True)
        src_line = next((ln for ln in p.text.splitlines() if nv in _norm(ln)), None)
        # OCR words in visual (right-to-left) order, or one value split over two OCR line groups
        candidates = [list(reversed(ws)) for _, ws in sorted(lines.items())] + [p.words]
        for seq in candidates:
            hits = _cover(seq, nv)
            if hits:
                bbox = [min(w.b[0] for w in hits), min(w.b[1] for w in hits),
                        max(w.b[2] for w in hits), max(w.b[3] for w in hits)]
                return FieldSource(page=p.page_no, text=src_line, bbox=bbox, verified=True)
        # mixed-direction runs reordered visually, or a token garbled by OCR: most of the
        # value's tokens on one OCR line are enough for a highlight (the value itself was
        # already verified against the page text above)
        hits = _token_line_hits(lines, value)
        if hits:
            bbox = [min(w.b[0] for w in hits), min(w.b[1] for w in hits),
                    max(w.b[2] for w in hits), max(w.b[3] for w in hits)]
            return FieldSource(page=p.page_no, text=src_line, bbox=bbox, verified=True)
        # words missing or garbled by OCR: page-level provenance only
        return FieldSource(page=p.page_no, text=src_line, bbox=None, verified=True)
    return None


def _token_line_hits(lines: dict[int, list], value: str, min_share: float = 0.75) -> list | None:
    tokens = [t for t in (_norm(x) for x in value.split()) if t]
    if len(tokens) < 2:
        return None
    best: list = []
    for _, words in sorted(lines.items()):
        free = list(words)
        hits = []
        for t in tokens:
            w = next((w for w in free if _norm(w.t) == t), None)
            if w is not None:
                free.remove(w)
                hits.append(w)
        if len(hits) > len(best):
            best = hits
    return best if len(best) >= max(2, min_share * len(tokens)) else None


def _cover(words: list, nv: str) -> list | None:
    """Consecutive words whose normalized texts concatenate exactly to ``nv``."""
    norms = [_norm(w.t) for w in words]
    for i in range(len(words)):
        acc = ""
        for j in range(i, len(words)):
            acc += norms[j]
            if acc == nv:
                return words[i:j + 1]
            if not nv.startswith(acc):
                break
    return None


def normalize(extraction: InvoiceExtraction, pages: list[PageText], method: str,
              language: str | None = None) -> NormalizedInvoice:
    out = NormalizedInvoice(method=method, language=language)
    for name in FIELD_NAMES:
        f = getattr(extraction, name)
        if not f.value or not str(f.value).strip():
            continue
        raw = str(f.value).strip()
        src = _locate(raw, pages, f.page)
        if src is None:
            out.issues.append(ValidationIssue(
                code="UNVERIFIED_VALUE", field=name, severity="warning",
                message=f"Extractor returned '{raw[:60]}' for {name}, but it does not appear in the document; discarded.",
            ))
            continue
        out.sources[name] = src
        if name in MONEY_FIELDS:
            val = parse_amount(raw)
        elif name in DATE_FIELDS:
            val = parse_date(raw)
        elif name == "tax_rate":
            val = parse_percent(raw)
        elif name == "currency":
            val = normalize_currency(raw)
        elif name == "supplier_tax_id":
            val = parse_tax_id(raw)
        else:
            val = raw
        if val is None:
            out.issues.append(ValidationIssue(code="UNPARSEABLE_VALUE", field=name,
                                              message=f"Could not parse '{raw[:60]}' as {name}."))
            continue
        setattr(out, name, val)

    for i, ln in enumerate(extraction.line_items, start=1):
        src = _locate(ln.source_text or ln.description, pages, ln.page)
        if src is None or src.bbox is None:  # the whole row cannot be boxed: box its description
            desc_src = _locate(ln.description, pages, ln.page)
            if desc_src is not None and (src is None or desc_src.bbox is not None):
                src = desc_src if src is None else src.model_copy(update={"bbox": desc_src.bbox, "page": desc_src.page})
        if src is None:
            out.issues.append(ValidationIssue(code="UNVERIFIED_LINE", field=f"line_{i}",
                                              message=f"Line '{ln.description[:50]}' not found in document; discarded."))
            continue
        out.lines.append(NormalizedLine(
            line_no=len(out.lines) + 1,
            description=ln.description.strip(),
            sku=(ln.sku or None),
            quantity=parse_amount(ln.quantity),
            unit_price=parse_amount(ln.unit_price),
            discount=parse_amount(ln.discount),
            line_total=parse_amount(ln.line_total),
            source=src,
        ))

    out.missing_fields = [f for f in REQUIRED_FIELDS if getattr(out, f) in (None, "")]
    if out.currency is None:
        out.missing_fields.append("currency")
    out.issues.extend(check_arithmetic(out))
    return out


def check_arithmetic(inv: NormalizedInvoice) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for ln in inv.lines:
        if ln.quantity is not None and ln.unit_price is not None and ln.line_total is not None:
            expected = round_money(ln.quantity * ln.unit_price - (ln.discount or Decimal(0)))
            if abs(expected - ln.line_total) > TOL:
                issues.append(ValidationIssue(
                    code="LINE_ARITHMETIC", field=f"line_{ln.line_no}",
                    message=f"Line {ln.line_no}: {ln.quantity} × {ln.unit_price} − {ln.discount or 0} = {expected}, "
                            f"but the document shows {ln.line_total}.",
                ))
    totals = [ln.line_total for ln in inv.lines if ln.line_total is not None]
    if inv.subtotal is not None and totals and len(totals) == len(inv.lines):
        s = sum(totals, Decimal(0))
        if abs(s - inv.subtotal) > TOL:
            issues.append(ValidationIssue(code="SUBTOTAL_MISMATCH", field="subtotal",
                                          message=f"Line totals sum to {s}, subtotal printed as {inv.subtotal}."))
    if inv.subtotal is not None and inv.tax_amount is not None and inv.total is not None:
        expected = inv.subtotal - (inv.discount_total or Decimal(0)) + inv.tax_amount
        if abs(expected - inv.total) > TOL:
            issues.append(ValidationIssue(code="TOTAL_MISMATCH", field="total",
                                          message=f"Subtotal − discount + tax = {expected}, total printed as {inv.total}."))
    if inv.subtotal is not None and inv.tax_amount is not None and inv.tax_rate is not None:
        expected = round_money((inv.subtotal - (inv.discount_total or Decimal(0))) * inv.tax_rate / Decimal(100))
        if abs(expected - inv.tax_amount) > Decimal("0.05"):
            issues.append(ValidationIssue(code="TAX_RATE_MISMATCH", field="tax_amount",
                                          message=f"{inv.tax_rate}% of the net amount is {expected}, "
                                                  f"tax printed as {inv.tax_amount}."))
    return issues
