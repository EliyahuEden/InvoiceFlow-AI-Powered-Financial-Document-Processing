"""Rule-based invoice extractor (offline baseline).

A transparent, deterministic baseline built from a bilingual label lexicon and table
heuristics. It runs with no external model, powers the clearly-labelled offline demo
mode, and is the baseline the LLM extractor is benchmarked against. It is *not*
presented as AI.

Labels are tried first. Where they are missing or contradict each other, layout-agnostic
rules take over, so an unfamiliar template degrades gracefully instead of failing:

- line items: any row whose numbers satisfy quantity x unit price = line total, wherever
  those columns are; the money-formatted factor is the price;
- totals: three amounts with subtotal + tax = total (subtotal = sum of the lines when known);
- PO numbers that identify themselves (``PO-…``), 9-digit tax IDs, and the first document
  number and date in the header block;
- supplier name: the header segment that carries a company suffix (Ltd, בע"מ, …).

Known limitation: free-form documents without a tabular line layout need the LLM extractor.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from decimal import Decimal
from itertools import permutations

from app.core.money import parse_amount
from app.services.extraction.schema import ExtractedField, ExtractedLine, InvoiceExtraction

NUM_TOKEN = re.compile(r"^[-(]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?$|^[-(]?\d+(?:\.\d+)?\)?$")
SKU_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
DOCNUM = r"([A-Z]{0,5}[-/]?[A-Z0-9]*\d[A-Z0-9\-/]*)"
DATE_RE = (r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"
           r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})")
PO_TOKEN = re.compile(r"\bPO[-\s]?\d[\w\-/]*")
HEADER_DOCNUM = re.compile(r"^[A-Z]{1,5}-?\d{3,}[A-Z0-9\-/]*$")
TAX_ID_TOKEN = re.compile(r"(?<![\d\-])\d{9}(?![\d\-])")
COMPANY_SUFFIX = re.compile(r"בע\"מ|בע״מ|\b(?:Ltd|Limited|Inc|LLC|GmbH|Corp|Co)\b\.?", re.IGNORECASE)
CENT = Decimal("0.01")
HEADER_BLOCK = 10  # lines at the top of page 1 searched by the label-free header fallbacks

LABELS: dict[str, list[str]] = {
    "invoice_number": ["חשבונית מס מספר", "מספר חשבונית", "חשבונית מס / קבלה מספר", "חשבונית מס", "חשבונית",
                       "Invoice Number", "Invoice No.", "Invoice No", "Invoice #", "Invoice"],
    "invoice_date": ["תאריך הפקה", "תאריך חשבונית", "תאריך", "Invoice Date", "Date of issue", "Date"],
    "due_date": ["תאריך פירעון", "לתשלום עד", "Due Date", "Payment due"],
    "po_reference": ["מס' הזמנה", "מספר הזמנה", "הזמנת רכש", "הזמנה", "PO Number", "PO No", "Purchase Order",
                     "Your reference", "PO"],
    "payment_terms": ["תנאי תשלום", "תשלום", "Payment Terms", "Terms"],
    "supplier_tax_id": ["עוסק מורשה", "ח.פ.", "ח.פ", "ע.מ.", "ע.מ", "Company No.", "Company No", "VAT No.", "VAT No",
                        "Reg. No", "Tax ID"],
}
CUSTOMER_MARKERS = ["לכבוד", "לקוח", "עבור", "Bill to", "Customer", "Sold to", "Ship to"]
TITLE_WORDS = ["חשבונית מס / קבלה", "חשבונית מס", "TAX INVOICE", "Invoice", "INVOICE"]

TOTAL_LABELS = ["סה\"כ לחיוב", "סה\"כ לתשלום", "סה\"כ כולל מע\"מ", "לתשלום", "Total Due", "Amount due", "Grand Total",
                "Balance due", "Total"]
SUBTOTAL_LABELS = ["סה\"כ לפני מע\"מ", "סה\"כ חייב מע\"מ", "סכום ביניים", "סה\"כ ללא מע\"מ", "Subtotal", "Sub-total", "Net amount", "סה\"כ"]
TAX_LABELS = ["מע\"מ", "VAT", "Tax"]
DISCOUNT_LABELS = ["הנחה כללית", "סה\"כ הנחה", "Discount total", "Total discount"]
HEADER_WORDS = ["מק\"ט", "תיאור", "פריט", "כמות", "מחיר", "סכום", "סה\"כ", "SKU", "Item", "Description", "Qty",
                "Quantity", "Price", "Unit Price", "Amount", "Discount", "הנחה"]


@dataclass
class _Line:
    page: int
    text: str


def _lines(pages: list[tuple[int, str]]) -> list[_Line]:
    return [_Line(p, ln.strip()) for p, txt in pages for ln in txt.splitlines() if ln.strip()]


def _field(value: str | None, line: _Line | None) -> ExtractedField:
    if value is None or line is None:
        return ExtractedField()
    return ExtractedField(value=value.strip(), source_text=line.text, page=line.page)


def _is_customer_line(text: str) -> bool:
    return any(m.lower() in text.lower() for m in CUSTOMER_MARKERS)


def _after_label(text: str, label: str) -> str | None:
    idx = text.lower().find(label.lower())
    if idx < 0:
        return None
    # label must start at a word boundary
    if idx > 0 and text[idx - 1].isalnum():
        return None
    rest = text[idx + len(label):]
    if rest and rest[0].isalnum() and label[-1].isalnum():
        return None
    if rest[:1] == "-" and rest[1:2].isdigit():
        return None  # "PO-2026-…": the label word is part of the value itself
    return rest.lstrip(" :#.-\t")


def _segment_at(text: str, idx: int) -> str:
    """The column segment (text between runs of 2+ spaces) that contains position idx."""
    start = max((m.end() for m in re.finditer(r"\s{2,}", text[:idx])), default=0)
    m = re.search(r"\s{2,}", text[idx:])
    return text[start: idx + m.start() if m else len(text)]


def _find_labeled(lines: list[_Line], key: str, pattern: str, skip_customer: bool = True) -> ExtractedField:
    for label in LABELS[key]:
        for ln in lines:
            # Header lines often share a row with the customer block ("עבור: …  תאריך חשבונית: …"),
            # so only the label's own column decides whether it belongs to the customer.
            idx = ln.text.lower().find(label.lower())
            if skip_customer and idx >= 0 and _is_customer_line(_segment_at(ln.text, idx)):
                continue
            rest = _after_label(ln.text, label)
            if rest is None:
                continue
            m = re.match(pattern, rest)
            if m:
                return _field(m.group(1), ln)
    return ExtractedField()


def _clean_num(tok: str) -> str:
    return tok.replace("₪", "").replace("$", "").replace("€", "").strip()


def _numbers_at_end(text: str) -> tuple[list[str], str]:
    tokens = text.split()
    nums: list[str] = []
    while tokens:
        tok = _clean_num(tokens[-1])
        if tok and NUM_TOKEN.match(tok):
            nums.insert(0, tok)
            tokens.pop()
        elif tok in ("", "ILS", "USD", "EUR", "₪", "$"):
            tokens.pop()
        else:
            break
    return nums, " ".join(tokens)


_NOT_TAX_LINE = ["לפני מע\"מ", "ללא מע\"מ", "כולל מע\"מ", "חייב מע\"מ", "לצורכי מע\"מ", "עוסק מורשה"]


def _amount_for_labels(lines: list[_Line], labels: list[str], exclude: set[int]) -> tuple[ExtractedField, int | None]:
    is_tax = labels is TAX_LABELS
    for label in labels:
        for i, ln in enumerate(lines):
            if i in exclude or _is_customer_line(ln.text):
                continue
            if is_tax and any(x in ln.text for x in _NOT_TAX_LINE):
                continue
            rest = _after_label(ln.text, label)
            if rest is None:
                continue
            if re.match(r"^(No\.?|Number|Reg|ID|#)(\b|\s|$)", rest, re.IGNORECASE):
                continue  # "VAT No. 5160..." is an identifier, not an amount
            # Avoid treating "סה"כ לתשלום" as subtotal label "סה"כ" etc.
            if label in ("סה\"כ", "Total", "Tax") and re.match(r"^[א-תA-Za-z]", rest.replace("(", "")):
                if not (label == "Tax" and rest.startswith("(")):
                    continue
            nums, _ = _numbers_at_end(rest.replace("%", "% "))
            nums = [n for n in nums if "%" not in n]
            if nums and not _is_identifier(nums[-1]):
                return _field(nums[-1], ln), i
    return ExtractedField(), None


def _is_header(text: str) -> bool:
    return sum(1 for w in HEADER_WORDS if w.lower() in text.lower()) >= 3


# ------------------------------------------------------------------ line items
def _is_identifier(tok: str) -> bool:
    """A long bare digit run (tax / company / phone number) is an identifier, never an amount."""
    return bool(re.fullmatch(r"\d{7,}", tok))


_LEAD_ID = re.compile(r"\d{4,}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")


def _clean_description(tokens: list[str], sku_column: bool) -> tuple[str, str | None]:
    """Drop leading identifier / date columns (delivery-note number, date, numeric SKU) that some
    layouts print before the description; a 4-10 digit code right before it is the SKU when the
    table has a SKU column. Numbers inside the description stay."""
    lead: list[str] = []
    while tokens and _LEAD_ID.fullmatch(tokens[0]):
        lead.append(tokens.pop(0))
    sku = lead[-1] if sku_column and lead and re.fullmatch(r"\d{4,10}", lead[-1]) else None
    return " ".join(tokens).strip(" |"), sku


def _is_money(tok: str) -> bool:
    return bool(re.search(r"\.\d{2}\)?$", tok))


def _qty_price(a: str, b: str) -> tuple[str, str] | None:
    """Order two factors as (quantity, price) when their formatting says so; None if ambiguous."""
    if _is_money(a) != _is_money(b):
        return (b, a) if _is_money(a) else (a, b)
    return None


def _arith_ok(q: str, p: str, t: str, d: str | None = None) -> bool:
    qv, pv, tv = parse_amount(q), parse_amount(p), parse_amount(t)
    dv = parse_amount(d) if d else Decimal(0)
    if qv is None or pv is None or tv is None or dv is None:
        return False
    return abs(qv * pv - dv - tv) <= CENT


def _description(tokens: list[str], skip: set[int]) -> str:
    """Longest run of remaining tokens that contains a word: numbers inside a description stay."""
    best: list[str] = []
    run: list[str] = []
    for i, tok in enumerate([*tokens, None]):
        if tok is None or i in skip:
            if any(re.search(r"[^\W\d_]", w) for w in run) and len(run) > len(best):
                best = run
            run = []
        else:
            run.append(tok)
    return " ".join(best).strip(" |")


def _row_by_arithmetic(text: str, sku_column: bool = False) -> tuple[str, str | None, str, str, str] | None:
    """(description, sku, qty, price, total) for a row in any column order, or None.

    Prefers the right-most consistent triple (description numbers usually sit to its left)."""
    tokens = text.split()
    sku_i = next((i for i, t in enumerate(tokens) if SKU_RE.fullmatch(t.strip(",;"))), None)
    nums = [(i, _clean_num(t)) for i, t in enumerate(tokens) if i != sku_i and NUM_TOKEN.match(_clean_num(t) or "x")]
    best: tuple[int, tuple] | None = None
    for (i, a), (j, b), (k, c) in permutations(nums, 3):
        if i > j or not _arith_ok(a, b, c):
            continue
        tv = parse_amount(c)
        if tv is None or tv <= 0 or parse_amount(a) == 0 or parse_amount(b) == 0:
            continue
        score = i + j + k
        if best is None or score > best[0]:
            best = (score, (i, a, j, b, k, c))
    if best is None:
        return None
    i, a, j, b, k, c = best[1]
    desc, num_sku = _clean_description(
        _description(tokens, {i, j, k} | ({sku_i} if sku_i is not None else set())).split(), sku_column)
    if not desc:
        return None
    q, p = _qty_price(a, b) or (a, b)
    return desc, tokens[sku_i].strip(",;") if sku_i is not None else num_sku, q, p, c


def _parse_lines(lines: list[_Line], used: set[int]) -> list[ExtractedLine]:
    out: list[ExtractedLine] = []
    has_header = any(_is_header(ln.text) for ln in lines)
    in_table = not has_header  # without a recognisable header every row is a candidate
    n_cols = 3
    sku_column = False
    stop_labels = SUBTOTAL_LABELS + TOTAL_LABELS + TAX_LABELS
    for i, ln in enumerate(lines):
        if _is_header(ln.text):
            in_table = True
            n_cols = 4 if ("discount" in ln.text.lower() or "הנחה" in ln.text) else 3
            sku_column = any(w in ln.text for w in ("מק\"ט", "SKU", "Code", "Item code"))
            continue
        if not in_table:
            continue
        if i in used or any(ln.text.startswith(lbl) for lbl in stop_labels):
            in_table = not has_header
            continue
        row = _row_from_columns(ln.text, n_cols, sku_column) if has_header else None
        if row is None or not _arith_ok(row[2], row[3], row[5], row[4]):
            alt = _row_by_arithmetic(ln.text, sku_column)
            if alt is not None:
                desc, sku, q, p, t = alt
                row = (desc, sku, q, p, None, t)
        if row is None:
            continue
        desc, sku, q, p, d, t = row
        out.append(ExtractedLine(description=desc, sku=sku, quantity=q, unit_price=p, discount=d,
                                 line_total=t, source_text=ln.text, page=ln.page))
    return out


def _row_from_columns(text: str, n_cols: int, sku_column: bool = False) -> tuple[str, str | None, str, str, str | None, str] | None:
    """Legacy layout: description first, then quantity, price, [discount,] total at the end."""
    nums, rest = _numbers_at_end(text)
    if len(nums) < n_cols or not rest:
        return None
    nums = nums[-n_cols:]
    sku_m = SKU_RE.search(rest)
    sku = sku_m.group(0) if sku_m else None
    desc, num_sku = _clean_description((rest.replace(sku, " ") if sku else rest).split(), sku_column)
    sku = sku or num_sku
    if not desc:
        return None
    qty_s, price_s, *more = nums
    disc_s = more[0] if n_cols == 4 else None
    total_s = more[-1]
    if any(parse_amount(x) is None for x in (qty_s, price_s, total_s)):
        return None
    qty_s, price_s = _qty_price(qty_s, price_s) or (qty_s, price_s)
    return desc, sku, qty_s, price_s, disc_s, total_s


# ------------------------------------------------------------------ totals
def _resolve_totals(out: InvoiceExtraction, lines: list[_Line], item_lines: set[int]) -> None:
    """If the labelled subtotal / tax / total are missing or inconsistent, find three amounts
    below the line items with subtotal + tax = total (subtotal = sum of lines when known)."""
    vals = {k: parse_amount(getattr(out, k).value) if getattr(out, k).value else None
            for k in ("subtotal", "tax_amount", "total", "discount_total")}
    disc = vals["discount_total"] or Decimal(0)
    if None not in (vals["subtotal"], vals["tax_amount"], vals["total"]) and \
            abs(vals["subtotal"] - disc + vals["tax_amount"] - vals["total"]) <= CENT:
        return
    start = max(item_lines) + 1 if item_lines else 0
    cands: list[tuple[int, str, Decimal]] = []
    for i in range(start, len(lines)):
        if i in item_lines or _is_customer_line(lines[i].text):
            continue
        nums, _ = _numbers_at_end(lines[i].text.replace("%", "% "))
        nums = [n for n in nums if "%" not in n and _is_money(n)]
        if nums and (v := parse_amount(nums[-1])) is not None:
            cands.append((i, nums[-1], v))
    item_sum = sum((parse_amount(ln.line_total) or Decimal(0) for ln in out.line_items), Decimal(0)) \
        if out.line_items else None
    found = None
    for (si, ss, sv), (ti, ts, tv), (gi, gs, gv) in permutations(cands, 3):
        if not (si < ti < gi) or tv >= sv or abs(sv - disc + tv - gv) > CENT:
            continue
        if item_sum is not None and abs(item_sum - sv) > CENT and abs(item_sum - gv) > CENT:
            continue  # lines are net (sum = subtotal) or VAT-inclusive (sum = total)
        found = ((si, ss), (ti, ts), (gi, gs))
        break
    if found is None:
        return
    (si, ss), (ti, ts), (gi, gs) = found
    out.subtotal, out.tax_amount, out.total = _field(ss, lines[si]), _field(ts, lines[ti]), _field(gs, lines[gi])
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", lines[ti].text)
    out.tax_rate = _field(f"{m.group(1)}%", lines[ti]) if m else ExtractedField()


# ------------------------------------------------------------------ header fallbacks
def _header(lines: list[_Line]) -> list[_Line]:
    if not lines:
        return []
    return [ln for ln in lines if ln.page == lines[0].page][:HEADER_BLOCK]


def _broken(text: str) -> bool:
    """Unmapped glyphs: a PDF font without a Unicode mapping yields private-use or control chars."""
    return any(unicodedata.category(c) in ("Co", "Cn", "Cs", "Cc") or c == "\ufffd" for c in text)


def _supplier_name(lines: list[_Line]) -> ExtractedField:
    first = _header(lines)[:3]
    for ln in first:  # a segment with a company suffix is the name, whatever else shares the line
        for seg in re.split(r"\s{2,}", ln.text):
            if COMPANY_SUFFIX.search(seg) and not _is_customer_line(seg):
                name = seg.strip(" -|")
                if _broken(name):
                    # the same name usually appears again (signature, footer) in a complete font
                    target = re.sub(r"\s+", " ", "".join(c for c in name if not _broken(c)))
                    for other in lines:
                        for cand in re.split(r"\s{2,}", other.text):
                            cand = cand.strip(" -|")
                            if cand != name and COMPANY_SUFFIX.search(cand) and not _broken(cand)                                     and SequenceMatcher(None, target, cand).ratio() >= 0.85:
                                return ExtractedField(value=cand, source_text=other.text, page=other.page)
                return ExtractedField(value=name, source_text=ln.text, page=ln.page)
    for ln in first:
        name = ln.text
        for tw in TITLE_WORDS:
            name = name.replace(tw, " ")
        name = re.sub(r"\s{2,}", " ", name).strip(" -|")
        if len(name) >= 3 and not re.search(r"\d{4}", name):
            return ExtractedField(value=name, source_text=ln.text, page=ln.page)
    return ExtractedField()


def _po_reference(lines: list[_Line]) -> ExtractedField:
    for ln in lines:
        if not _is_customer_line(ln.text) and (m := PO_TOKEN.search(ln.text)):
            return _field(m.group(0).rstrip(".,;"), ln)
    return _find_labeled(lines, "po_reference", r"(PO[-\s]?[A-Z0-9][A-Z0-9\-]*|\d[\d\-]{3,})")


def _header_docnum(lines: list[_Line], exclude: set[str]) -> ExtractedField:
    for ln in _header(lines):
        if _is_customer_line(ln.text):
            continue
        for tok in ln.text.split():
            tok = tok.strip(",;:")
            if HEADER_DOCNUM.match(tok) and not tok.startswith("PO") and tok not in exclude:
                return _field(tok, ln)
    return ExtractedField()


def _header_date(lines: list[_Line]) -> ExtractedField:
    due = [lbl.lower() for lbl in LABELS["due_date"]]
    for ln in _header(lines):
        if _is_customer_line(ln.text) or any(d in ln.text.lower() for d in due):
            continue
        if m := re.search(DATE_RE, ln.text):
            return _field(m.group(1), ln)
    return ExtractedField()


def _header_tax_id(lines: list[_Line], exclude: set[str]) -> ExtractedField:
    for ln in _header(lines):
        if _is_customer_line(ln.text):
            continue
        for m in TAX_ID_TOKEN.finditer(ln.text):
            if m.group(0) not in exclude:
                return _field(m.group(0), ln)
    return ExtractedField()


def extract(pages: list[tuple[int, str]], exclude_tax_ids: set[str] | None = None) -> InvoiceExtraction:
    lines = _lines(pages)
    out = InvoiceExtraction()
    exclude_tax_ids = exclude_tax_ids or set()

    # --- header fields: labels first, then label-free fallbacks in the header block
    out.po_reference = _po_reference(lines)
    out.invoice_number = _find_labeled(lines, "invoice_number", DOCNUM)
    if not out.invoice_number.value:
        out.invoice_number = _header_docnum(lines, {out.po_reference.value or ""})
    out.invoice_date = _find_labeled(lines, "invoice_date", DATE_RE)
    if not out.invoice_date.value:
        out.invoice_date = _header_date(lines)
    out.due_date = _find_labeled(lines, "due_date", r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})")
    terms = _find_labeled(lines, "payment_terms", r"(.+)$")
    if terms.value:
        terms.value = re.split(r"\s{2,}", terms.value)[0].strip()
    out.payment_terms = terms

    for label in LABELS["supplier_tax_id"]:
        found = False
        for ln in lines:
            if _is_customer_line(ln.text):
                continue
            rest = _after_label(ln.text, label)
            if rest is None:
                continue
            m = re.match(r"([\d\-\s]{8,13})", rest)
            if m:
                digits = re.sub(r"\D", "", m.group(1))
                if 8 <= len(digits) <= 10 and digits not in exclude_tax_ids:
                    out.supplier_tax_id = _field(m.group(1).strip(), ln)
                    found = True
                    break
        if found:
            break
    if not out.supplier_tax_id.value:
        out.supplier_tax_id = _header_tax_id(lines, exclude_tax_ids)

    out.supplier_name = _supplier_name(lines)

    # --- totals (labels)
    used: set[int] = set()
    out.total, ti = _amount_for_labels(lines, TOTAL_LABELS, used)
    if ti is not None:
        used.add(ti)
    out.tax_amount, xi = _amount_for_labels(lines, TAX_LABELS, used)
    if xi is not None:
        used.add(xi)
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", lines[xi].text)
        if m:
            out.tax_rate = ExtractedField(value=f"{m.group(1)}%", source_text=lines[xi].text, page=lines[xi].page)
    out.subtotal, si = _amount_for_labels(lines, SUBTOTAL_LABELS, used)
    if si is not None:
        used.add(si)
    out.discount_total, _ = _amount_for_labels(lines, DISCOUNT_LABELS, used)

    # --- line items, then totals checked against them
    out.line_items = _parse_lines(lines, used)
    item_idx = {i for i, ln in enumerate(lines) for it in out.line_items if it.source_text == ln.text}
    _resolve_totals(out, lines, item_idx)

    # --- currency
    total_line = next((ln for ln in lines if out.total.source_text and ln.text == out.total.source_text), None)
    for ln in ([total_line] if total_line else []) + lines:
        m = re.search(r"₪|\bILS\b|\bNIS\b|ש\"ח|\$|\bUSD\b|€|\bEUR\b", ln.text)
        if m:
            out.currency = ExtractedField(value=m.group(0), source_text=ln.text, page=ln.page)
            break
    return out
