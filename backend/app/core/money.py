"""Exact monetary arithmetic.

All money is represented as ``decimal.Decimal`` (stored as NUMERIC(18,4)). Floats are
never used for money. Parsing accepts the formats that appear on Israeli and
international invoices: ``1,234.56``, ``1.234,56``, ``₪ 1,234``, ``(12.00)``, ``-12``.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_Q = Decimal("0.01")
PRICE_Q = Decimal("0.0001")
QTY_Q = Decimal("0.001")

_CURRENCY_SYMBOLS = {"₪": "ILS", "$": "USD", "€": "EUR", "£": "GBP"}
_CURRENCY_WORDS = {
    "ILS": "ILS", "NIS": "ILS", 'ש"ח': "ILS", "ש״ח": "ILS", "שח": "ILS", "שקל": "ILS",
    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "דולר": "USD", "יורו": "EUR",
}
_NUM_RE = re.compile(r"[-−(]?\d[\d,.\s']*\d|[-−(]?\d")


def D(value: object) -> Decimal:
    """Strict conversion to Decimal. Rejects floats to avoid binary rounding."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("floats are not allowed for money; pass str or Decimal")
    return Decimal(str(value))


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def parse_amount(raw: str | None) -> Decimal | None:
    """Parse a human-written amount into Decimal. Returns None if unparseable.

    Decides the decimal separator by the *last* separator followed by 1-2 digits.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = _NUM_RE.search(s.replace("‏", "").replace("‎", ""))
    if not m:
        return None
    token = m.group(0)
    negative = token.startswith(("-", "−", "(")) or s.strip().endswith("-")
    token = token.lstrip("-−(").replace(" ", "").replace("'", "")
    last_dot, last_comma = token.rfind("."), token.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        if last_dot > last_comma:
            token = token.replace(",", "")
        else:
            token = token.replace(".", "").replace(",", ".")
    elif last_comma >= 0:
        decimals = len(token) - last_comma - 1
        # "1,234" is thousands; "12,5" / "12,50" is a decimal comma.
        token = token.replace(",", ".") if decimals in (1, 2) and token.count(",") == 1 else token.replace(",", "")
    elif token.count(".") > 1:
        token = token.replace(".", "")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    return -value if negative else value


def detect_currency(text: str | None) -> str | None:
    if not text:
        return None
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in text:
            return code
    upper = text.upper()
    for word, code in _CURRENCY_WORDS.items():
        if word in upper or word in text:
            return code
    return None


def within_tolerance(expected: Decimal, actual: Decimal, abs_tol: Decimal, pct_tol: Decimal) -> bool:
    """True when |actual-expected| <= max(abs_tol, pct_tol% of |expected|)."""
    diff = abs(actual - expected)
    allowed = max(abs_tol, abs(expected) * pct_tol / Decimal(100))
    return diff <= allowed
