"""Risk-first priority: transparent, deterministic rules (no AI score)."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.services import priority as P

TODAY = date(2026, 11, 20)
T5000 = Decimal("5000")


def item(types=(), risk="0", due=None, age_days=0):
    return P.PriorityInput(exception_id=uuid.uuid4(), finding_types=list(types), amount_at_risk=Decimal(risk),
                           due_date=due, created_at=datetime(2026, 11, 20, tzinfo=UTC) - timedelta(days=age_days),
                           invoice_total=Decimal("1000"))


def codes(p):
    return [r["code"] for r in p.reasons]


def test_blocking_finding_is_critical_and_says_which():
    p = P.compute(item(["DUPLICATE_INVOICE"]), TODAY, T5000)
    assert p.level == "critical"
    assert {"code": "blocking", "params": {"finding": "DUPLICATE_INVOICE"}} in p.reasons


def test_large_money_at_risk_is_critical():
    p = P.compute(item(["PRICE_MISMATCH"], risk="5000.00"), TODAY, T5000)
    assert p.level == "critical" and {"code": "amount_at_risk", "params": {"amount": "5000.00"}} in p.reasons


def test_any_money_at_risk_is_high():
    assert P.compute(item(["QUANTITY_EXCEEDS_RECEIVED"], risk="1180.00"), TODAY, T5000).level == "high"


def test_unconfirmed_delivery_is_high():
    assert P.compute(item(["MISSING_GOODS_RECEIPT"]), TODAY, T5000).level == "high"


def test_minor_issue_is_normal():
    p = P.compute(item(["AMBIGUOUS_DESCRIPTION"]), TODAY, T5000)
    assert p.level == "normal" and codes(p) == ["review_needed"]


def test_due_within_three_days_raises_one_level():
    p = P.compute(item(["AMBIGUOUS_DESCRIPTION"], due=TODAY + timedelta(days=2)), TODAY, T5000)
    assert p.level == "high" and {"code": "due_soon", "params": {"days": 2}} in p.reasons and p.due_in_days == 2


def test_overdue_raises_high_to_critical():
    p = P.compute(item(["PRICE_MISMATCH"], risk="100", due=TODAY - timedelta(days=3)), TODAY, T5000)
    assert p.level == "critical" and {"code": "overdue", "params": {"days": 3}} in p.reasons


def test_due_later_does_not_change_level():
    p = P.compute(item(["AMBIGUOUS_DESCRIPTION"], due=TODAY + timedelta(days=10)), TODAY, T5000)
    assert p.level == "normal" and p.due_in_days == 10 and "due_soon" not in codes(p)


def test_no_due_date_is_fine_and_sorts_after_dated_items():
    undated = item(["PRICE_MISMATCH"], risk="900")
    dated = item(["PRICE_MISMATCH"], risk="100", due=TODAY + timedelta(days=20))
    ranked = P.rank([(i, P.compute(i, TODAY, T5000)) for i in (undated, dated)])
    assert ranked[0][0] is dated and ranked[1][1].due_in_days is None


def test_order_is_level_then_due_then_money_then_age():
    crit = item(["DUPLICATE_INVOICE"])
    high_soon = item(["PRICE_MISMATCH"], risk="10", due=TODAY + timedelta(days=5))
    high_big = item(["PRICE_MISMATCH"], risk="4000", due=TODAY + timedelta(days=9))
    high_small = item(["PRICE_MISMATCH"], risk="50", due=TODAY + timedelta(days=9))
    normal_old = item(["PO_CLOSED"], age_days=9)
    normal_new = item(["PO_CLOSED"], age_days=1)
    items = [normal_new, high_small, crit, normal_old, high_big, high_soon]
    ranked = [i for i, _ in P.rank([(i, P.compute(i, TODAY, T5000)) for i in items])]
    assert ranked == [crit, high_soon, high_big, high_small, normal_old, normal_new]


def test_escalated_and_suspicious_reasons():
    p = P.compute(item(["SUSPICIOUS_CONTENT"]), TODAY, T5000, escalated=True)
    assert p.level == "high"
    assert {"code": "suspicious_content", "params": {}} in p.reasons
    assert {"code": "escalated", "params": {}} in p.reasons
