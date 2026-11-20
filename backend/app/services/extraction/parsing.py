"""Deterministic parsers for printed values (dates, tax IDs, percentages)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.core.money import parse_amount

_EN_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_HE_MONTHS = {"ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7,
              "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12}


def _year(y: str) -> int:
    v = int(y)
    return 2000 + v if v < 100 else v


def parse_date(raw: str | None) -> date | None:
    """Parse dates as printed on Israeli/international invoices (day-first)."""
    if not raw:
        return None
    s = raw.strip()
    try:
        if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", s):
            return date(_year(m[3]), int(m[2]), int(m[1]))
        if m := re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", s):
            return date(int(m[3]), _EN_MONTHS[m[2].lower()], int(m[1]))
        if m := re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s):
            return date(int(m[3]), _EN_MONTHS[m[1].lower()], int(m[2]))
        for name, num in _HE_MONTHS.items():
            if m := re.search(rf"(\d{{1,2}})\s+ב?{name}\s+(\d{{4}})", s):
                return date(int(m[2]), num, int(m[1]))
    except (ValueError, KeyError):
        return None
    return None


def parse_tax_id(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if 8 <= len(digits) <= 10 else None


def parse_percent(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", raw)
    if m:
        return Decimal(m[1].replace(",", "."))
    return parse_amount(raw)


def normalize_currency(raw: str | None) -> str | None:
    from app.core.money import detect_currency

    if not raw:
        return None
    code = detect_currency(raw)
    if code:
        return code
    up = raw.strip().upper()
    return up if re.fullmatch(r"[A-Z]{3}", up) else None
