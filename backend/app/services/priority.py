"""Risk-first review priority: deterministic, documented rules, never an AI score.

1. critical: a blocking finding (the invoice cannot be paid as is), or money at risk of at
   least the organization's critical amount;
2. high: any money at risk, unconfirmed delivery, or suspicious embedded instructions;
3. normal: everything else that still needs a person;
4. overdue, or due within URGENT_DAYS days, raises the level by one.

Ordering: level, then due date (soonest first, undated last), then money at risk (largest
first), then age (oldest first). Each result carries its reasons as {code, params} so the UI
can explain the priority in the reader's language. Priority orders work; it never decides.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.services.reconciliation.engine import BLOCKING

URGENT_DAYS = 3
DEFAULT_CRITICAL_AMOUNT = Decimal("5000")
LEVELS = ("critical", "high", "normal")
_MONEY = {"PRICE_MISMATCH", "QUANTITY_EXCEEDS_ORDERED", "QUANTITY_EXCEEDS_RECEIVED", "TOTAL_MISMATCH",
          "CURRENCY_MISMATCH", "ITEM_NOT_ON_PO"}


@dataclass
class PriorityInput:
    exception_id: uuid.UUID
    finding_types: list[str]
    amount_at_risk: Decimal
    due_date: date | None
    created_at: datetime
    invoice_total: Decimal | None = None


@dataclass
class Priority:
    level: str
    reasons: list[dict] = field(default_factory=list)
    due_in_days: int | None = None
    sort_key: tuple = ()


def _reason(code: str, **params: object) -> dict:
    return {"code": code, "params": params}


def compute(inp: PriorityInput, today: date, critical_amount: Decimal = DEFAULT_CRITICAL_AMOUNT,
            escalated: bool = False) -> Priority:
    types = set(inp.finding_types)
    risk = inp.amount_at_risk or Decimal(0)
    reasons: list[dict] = []
    blocking = sorted(types & BLOCKING)
    if blocking:
        level = 0
        reasons += [_reason("blocking", finding=t) for t in blocking]
    elif risk >= critical_amount:
        level = 0
    elif risk > 0 or types & {"MISSING_GOODS_RECEIPT", "SUSPICIOUS_CONTENT"} or types & _MONEY:
        level = 1
    else:
        level = 2
    if risk > 0:
        reasons.append(_reason("amount_at_risk", amount=f"{risk:.2f}"))
    if "MISSING_GOODS_RECEIPT" in types:
        reasons.append(_reason("unconfirmed_delivery"))
    if "SUSPICIOUS_CONTENT" in types:
        reasons.append(_reason("suspicious_content"))
    due_in = (inp.due_date - today).days if inp.due_date else None
    if due_in is not None and due_in < 0:
        level = max(0, level - 1)
        reasons.append(_reason("overdue", days=-due_in))
    elif due_in is not None and due_in <= URGENT_DAYS:
        level = max(0, level - 1)
        reasons.append(_reason("due_soon", days=due_in))
    if escalated:
        reasons.append(_reason("escalated"))
    if not reasons:
        reasons.append(_reason("review_needed"))
    sort_key = (level, (0, inp.due_date) if inp.due_date else (1, date.max), -risk, inp.created_at)
    return Priority(level=LEVELS[level], reasons=reasons, due_in_days=due_in, sort_key=sort_key)


def rank(items: list[tuple[PriorityInput, Priority]]) -> list[tuple[PriorityInput, Priority]]:
    return sorted(items, key=lambda x: x[1].sort_key)
