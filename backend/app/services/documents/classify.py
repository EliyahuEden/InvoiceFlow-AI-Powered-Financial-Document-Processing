"""Is this document a supplier invoice at all?

Accounts-payable inboxes also receive order and booking confirmations, quotes, receipts, credit
notes, delivery notes, customs declarations and statements. Only the document's title decides,
read from its header (the first lines), in this order: credit note (its Hebrew title contains the
word for invoice), then any invoice title, then the other kinds. Anything unclear is treated as an
invoice, so a real invoice is never hidden; the reviewer sees the matched title as evidence.
"""
from __future__ import annotations

import re

HEADER_LINES = 12

# (kind, patterns) checked in order; the first match wins
KINDS: list[tuple[str | None, list[str]]] = [
    ("credit_note", [r"חשבונית\s*זיכוי", r"credit\s*note"]),
    (None, [r"חשבונית\s*מס", r"חשבונית", r"\btax\s*invoice\b", r"\binvoice\b"]),
    ("proforma", [r"חשבון\s*עסקה", r"\bpro[\s-]?forma\b"]),
    ("order_confirmation", [r"אישור\s*הזמנה", r"\b(?:order|booking|reservation)\s*confirmation\b"]),
    ("quote", [r"הצעת\s*מחיר", r"\bquotation\b", r"\bquote\b"]),
    ("delivery_note", [r"תעודת\s*משלוח", r"\bdelivery\s*note\b", r"\bpacking\s*slip\b"]),
    ("customs_declaration", [r"רשימון", r"הצהרת\s*יבוא", r"\bcustoms\s*declaration\b"]),
    ("statement", [r"כרטסת", r"\bstatement\s*of\s*account\b"]),
    ("receipt", [r"(?<![\w\"״/-])קבלה", r"\breceipt\b"]),
    # an order printout: an order number and (since invoices were checked first) no invoice title
    ("order_confirmation", [r"הזמנה\s*מספר", r"\border\s*(?:number|no\.?)\b"]),
]
COMPILED = [(kind, [re.compile(p, re.IGNORECASE) for p in pats]) for kind, pats in KINDS]


def classify_document(text: str) -> tuple[str, str] | None:
    """(kind, matched title) for a document that is not a supplier invoice, else None."""
    header = "\n".join([ln for ln in text.splitlines() if ln.strip()][:HEADER_LINES])
    if not header:
        return None
    for kind, patterns in COMPILED:
        for pat in patterns:
            m = pat.search(header)
            if m:
                return None if kind is None else (kind, m.group(0).strip())
    return None
