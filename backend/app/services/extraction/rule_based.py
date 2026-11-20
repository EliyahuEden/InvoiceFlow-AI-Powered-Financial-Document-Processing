"""Rule-based invoice extractor (offline baseline).

A transparent, deterministic baseline built from a bilingual label lexicon and table
heuristics. It runs with no external model, powers the clearly-labelled offline demo
mode, and is the baseline the LLM extractor is benchmarked against. It is *not*
presented as AI. Known limitation: it depends on recognisable labels and on rows that
end with numeric columns; free-form layouts need the LLM extractor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.money import parse_amount
from app.services.extraction.schema import ExtractedField, ExtractedLine, InvoiceExtraction

NUM_TOKEN = re.compile(r"^[-(]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?$|^[-(]?\d+(?:\.\d+)?\)?$")
SKU_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
DOCNUM = r"([A-Z]{0,5}[-/]?[A-Z0-9]*\d[A-Z0-9\-/]*)"

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

TOTAL_LABELS = ["סה\"כ לתשלום", "סה\"כ כולל מע\"מ", "לתשלום", "Total Due", "Amount due", "Grand Total",
                "Balance due", "Total"]
SUBTOTAL_LABELS = ["סה\"כ לפני מע\"מ", "סכום ביניים", "סה\"כ ללא מע\"מ", "Subtotal", "Sub-total", "Net amount", "סה\"כ"]
TAX_LABELS = ["מע\"מ", "VAT", "Tax"]
DISCOUNT_LABELS = ["הנחה כללית", "Discount total", "Total discount"]
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
    return rest.lstrip(" :#.-\t")


def _find_labeled(lines: list[_Line], key: str, pattern: str, skip_customer: bool = True) -> ExtractedField:
    for label in LABELS[key]:
        for ln in lines:
            if skip_customer and _is_customer_line(ln.text):
                continue
            rest = _after_label(ln.text, label)
            if rest is None:
                continue
            m = re.match(pattern, rest)
            if m:
                return _field(m.group(1), ln)
    return ExtractedField()


def _numbers_at_end(text: str) -> tuple[list[str], str]:
    tokens = text.split()
    nums: list[str] = []
    while tokens:
        tok = tokens[-1].replace("₪", "").replace("$", "").strip()
        if tok and NUM_TOKEN.match(tok):
            nums.insert(0, tok)
            tokens.pop()
        elif tok in ("", "ILS", "USD", "EUR", "₪", "$"):
            tokens.pop()
        else:
            break
    return nums, " ".join(tokens)


_NOT_TAX_LINE = ["לפני מע\"מ", "ללא מע\"מ", "כולל מע\"מ", "עוסק מורשה"]


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
            if nums:
                return _field(nums[-1], ln), i
    return ExtractedField(), None


def _is_header(text: str) -> bool:
    return sum(1 for w in HEADER_WORDS if w.lower() in text.lower()) >= 3


def extract(pages: list[tuple[int, str]], exclude_tax_ids: set[str] | None = None) -> InvoiceExtraction:
    lines = _lines(pages)
    out = InvoiceExtraction()
    exclude_tax_ids = exclude_tax_ids or set()

    # --- header fields
    out.invoice_number = _find_labeled(lines, "invoice_number", DOCNUM)
    out.invoice_date = _find_labeled(
        lines, "invoice_date",
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})",
    )
    out.due_date = _find_labeled(lines, "due_date", r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})")
    out.po_reference = _find_labeled(lines, "po_reference", r"(PO[-\s]?[A-Z0-9][A-Z0-9\-]*|\d[\d\-]{3,})")
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

    # --- supplier name: first line of page 1, minus document-title words
    first_page = [ln for ln in lines if ln.page == lines[0].page] if lines else []
    for ln in first_page[:3]:
        name = ln.text
        for tw in TITLE_WORDS:
            name = name.replace(tw, " ")
        name = re.sub(r"\s{2,}", " ", name).strip(" -|")
        if len(name) >= 3 and not re.search(r"\d{4}", name):
            out.supplier_name = ExtractedField(value=name, source_text=ln.text, page=ln.page)
            break

    # --- totals
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
    out.discount_total, _ = _amount_for_labels(lines, DISCOUNT_LABELS, used | ({si} if si is not None else set()))

    # --- currency
    cur_line = lines[ti] if ti is not None else None
    for ln in ([cur_line] if cur_line else []) + lines:
        m = re.search(r"₪|\bILS\b|\bNIS\b|ש\"ח|\$|\bUSD\b|€|\bEUR\b", ln.text)
        if m:
            out.currency = ExtractedField(value=m.group(0), source_text=ln.text, page=ln.page)
            break

    # --- line items: rows between a table header and the totals block
    in_table = False
    n_cols = 3
    stop_labels = SUBTOTAL_LABELS + TOTAL_LABELS + TAX_LABELS
    for i, ln in enumerate(lines):
        if _is_header(ln.text):
            in_table = True
            n_cols = 4 if ("discount" in ln.text.lower() or "הנחה" in ln.text) else 3
            continue
        if not in_table:
            continue
        if i in used or any(ln.text.startswith(lbl) for lbl in stop_labels):
            in_table = False
            continue
        nums, rest = _numbers_at_end(ln.text)
        if len(nums) < n_cols or not rest:
            continue
        nums = nums[-n_cols:]
        sku_m = SKU_RE.search(rest)
        sku = sku_m.group(0) if sku_m else None
        desc = (rest.replace(sku, " ") if sku else rest)
        desc = re.sub(r"\s{2,}", " ", desc).strip()
        if not desc:
            continue
        qty_s, price_s, *more = nums
        disc_s = more[0] if n_cols == 4 else None
        total_s = more[-1]
        q, p, t = parse_amount(qty_s), parse_amount(price_s), parse_amount(total_s)
        if q is None or p is None or t is None:
            continue
        out.line_items.append(ExtractedLine(
            description=desc, sku=sku, quantity=qty_s, unit_price=price_s, discount=disc_s,
            line_total=total_s, source_text=ln.text, page=ln.page,
        ))
    return out
