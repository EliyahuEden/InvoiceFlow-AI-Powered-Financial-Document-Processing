"""Deterministic faithfulness checks for LLM investigation reports.

The reconciliation engine's findings are authoritative; the model only explains them. Before a
report is shown, every text is checked:

1. Numbers: each amount or percentage must appear in the findings, the invoice or the cited
   evidence, or be a difference or percentage of two finding/invoice numbers. Document numbers
   (PO-2026-1004), dates and small counts ("line 1", "2 findings") are not treated as amounts.
2. Currency: an amount known to be in the invoice currency must not be labelled with another one
   (a real model wrote "3,455.04 ILS" for a USD invoice).
3. Languages: every text must exist in Hebrew and English, and the Hebrew text must be Hebrew.
4. No internal evidence ids in the prose ("evidence 7"): citations are shown next to it.

Claims without numbers ("already paid") are not caught here; that needs an LLM judge.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from itertools import permutations

# an amount in prose: not glued to an identifier (PO-2026-1004, AR-77120) or a date (2026-01-01)
NUM = re.compile(r"(?<![\w\-./])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)(?!-\d)")
ANY_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
CURRENCY_WORDS = {
    "ILS": r"₪|ש\"ח|ש״ח|שקלים|שקל|ILS|NIS",
    "USD": r"\$|USD|דולר|dollars?",
    "EUR": r"€|EUR|אירו|euros?",
    "GBP": r"£|GBP",
}
CUR = "|".join(f"(?P<{code}>{pat})" for code, pat in CURRENCY_WORDS.items())
AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
PAIRS = [re.compile(rf"(?:{CUR})\s?(?P<amount>{AMOUNT})"), re.compile(rf"(?P<amount>{AMOUNT})\s?(?:{CUR})")]
HEBREW = re.compile(r"[֐-׿]")
# the evidence ids are internal; citations are shown next to the text, so the text names documents
EVIDENCE_REF = re.compile(r"(?:\bevidence|מסמך|הוכחה|ראיה|ראייה)\s*(?:#|מס'?\s*)?\d+", re.IGNORECASE)
SMALL_COUNT = Decimal(12)
TOL, PCT_TOL = Decimal("0.01"), Decimal("0.05")


def _dec(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def _fmt(d: Decimal) -> str:
    return f"{d.normalize():f}"


def _values(obj) -> list[Decimal]:  # noqa: ANN001
    return [d for d in (_dec(m) for m in ANY_NUM.findall(json.dumps(obj, ensure_ascii=False))) if d is not None]


def _finding_numbers(findings: list[dict], invoice: dict) -> list[Decimal]:
    base = []
    for f in findings:
        base += _values(f.get("params") or {}) + _values(f.get("amount_at_risk") or "")
    base += _values({k: invoice.get(k) for k in ("subtotal", "tax", "total")})
    return [d for d in dict.fromkeys(base) if d > SMALL_COUNT]


def _allowed(findings: list[dict], evidence: list[dict], invoice: dict) -> tuple[set[Decimal], set[Decimal]]:
    """(allowed amounts, allowed percentages)."""
    amounts = set(_values(findings) + _values(invoice)
                  + _values([[e.get("title"), e.get("text"), e.get("effective_date")] for e in evidence]))
    pcts = set(amounts)
    nums = _finding_numbers(findings, invoice)[:40]
    for a, b in permutations(nums, 2):
        amounts.add(abs(a - b))
        if b:
            for v in (a / b * 100, abs(a - b) / b * 100):
                pcts.update({round(v, 2), round(v, 1), round(v)})
    return amounts, pcts


def _near(x: Decimal, pool: set[Decimal], tol: Decimal) -> bool:
    return any(abs(x - p) <= tol for p in pool)


def _texts(report: dict):  # noqa: ANN202
    for key in ("headline", "summary", "recommendation"):
        yield key, report.get(key) or {}
    for ftype, text in (report.get("findings") or {}).items():
        yield f"finding {ftype}", text or {}


def check_report(report: dict, findings: list[dict], evidence: list[dict], invoice: dict) -> list[str]:
    """Return human-readable violations (empty when the report is faithful).

    ``report`` holds {"headline"|"summary"|"recommendation": {"he", "en"}} and optionally
    ``findings``: {finding_type: {"he", "en"}}."""
    amounts, pcts = _allowed(findings, evidence, invoice)
    inv_cur = (invoice.get("currency") or "").upper() or None
    invoice_amounts = set(_values([f.get("amount_at_risk") for f in findings])
                          + _values({k: invoice.get(k) for k in ("subtotal", "tax", "total")})
                          + _values([[ln.get("unit_price"), ln.get("line_total")] for ln in invoice.get("lines") or []]))
    out: list[str] = []
    for field, text in _texts(report):
        for lang in ("he", "en"):
            t = (text.get(lang) or "").strip()
            if not t:
                out.append(f"{field}: missing {lang} text")
                continue
            if lang == "he" and not HEBREW.search(t):
                out.append(f"{field}.he: the Hebrew text is not written in Hebrew")
            if EVIDENCE_REF.search(t):
                out.append(f"{field}.{lang}: mentions an internal evidence id; name the document instead "
                           f"(citations are shown separately)")
            t = EVIDENCE_REF.sub(" ", t)
            for whole, frac, pct in NUM.findall(t):
                n = _dec(whole + frac)
                if n is None or (not pct and not frac and n <= SMALL_COUNT):
                    continue
                if pct and (_near(n, pcts, PCT_TOL) or n <= SMALL_COUNT):
                    continue
                if not pct and _near(n, amounts, TOL):
                    continue
                out.append(f"{field}.{lang}: {'percentage' if pct else 'number'} {_fmt(n)} is not in the findings, "
                           f"invoice or evidence")
            if inv_cur:
                for pattern in PAIRS:
                    for m in pattern.finditer(t):
                        code = next(c for c in CURRENCY_WORDS if m.group(c))
                        n = _dec(m.group("amount"))
                        if n is not None and code != inv_cur and _near(n, invoice_amounts, TOL):
                            out.append(f"{field}.{lang}: amount {_fmt(n)} is in the invoice currency {inv_cur}, "
                                       f"not {code}")
    return list(dict.fromkeys(out))


def unsupported_numbers(text: str, sources: object, max_derived: int = 60) -> list[str]:
    """Numbers in free text (e.g. a Copilot answer) that do not appear in ``sources`` (the tool
    results) and are not a difference or percentage of two source numbers. Small counts, dates and
    document identifiers are ignored, as in check_report."""
    amounts = set(_values(sources))
    nums = [d for d in dict.fromkeys(amounts) if d > SMALL_COUNT][:max_derived]
    pcts = set(amounts)
    for a, b in permutations(nums, 2):
        amounts.add(abs(a - b))
        if b:
            for v in (a / b * 100, abs(a - b) / b * 100):
                pcts.update({round(v, 2), round(v, 1), round(v)})
    out = []
    for whole, frac, pct in NUM.findall(EVIDENCE_REF.sub(" ", text)):
        n = _dec(whole + frac)
        if n is None or (not frac and n <= SMALL_COUNT) or (pct and n <= SMALL_COUNT):
            continue
        if (pct and _near(n, pcts, PCT_TOL)) or (not pct and _near(n, amounts, TOL)):
            continue
        out.append(f"{'percentage' if pct else 'number'} {_fmt(n)} is not in the data the tools returned")
    return list(dict.fromkeys(out))
