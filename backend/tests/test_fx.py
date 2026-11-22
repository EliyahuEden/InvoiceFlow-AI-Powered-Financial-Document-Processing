"""Exchange rates for risk ranking: Bank of Israel representative rates, cached, never blocking.
No network: the HTTP layer is a fake transport."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from app.services import fx

BOI = {"exchangeRates": [
    {"key": "USD", "currentExchangeRate": 3.326, "unit": 1, "lastUpdate": "2026-11-20T10:21:05.8283621Z"},
    {"key": "EUR", "currentExchangeRate": 3.6503, "unit": 1, "lastUpdate": "2026-11-20T10:21:05.8283621Z"},
    {"key": "JPY", "currentExchangeRate": 2.0908, "unit": 100, "lastUpdate": "2026-11-20T10:21:05.8283621Z"},
]}


def transport(payload=None, status=200, exc=None):  # noqa: ANN001, ANN201
    def handler(request: httpx.Request) -> httpx.Response:
        if exc:
            raise exc
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    fx.clear_cache()
    monkeypatch.setattr(fx, "_redis", lambda: None)  # in-memory cache only in these unit tests
    yield
    fx.clear_cache()


def test_parses_bank_of_israel_rates_per_one_unit():
    rates = fx.fetch_boi(transport(BOI))
    assert rates.rates["USD"] == Decimal("3.326") and rates.rates["EUR"] == Decimal("3.6503")
    assert rates.rates["JPY"] == Decimal("0.020908")  # quoted per 100 yen
    assert rates.as_of == date(2026, 11, 20) and rates.source == "Bank of Israel"


def test_converts_to_shekels_and_leaves_shekels_alone():
    rates = fx.fetch_boi(transport(BOI))
    assert fx.to_base(Decimal("2000"), "USD", rates) == Decimal("6652.00")
    assert fx.to_base(Decimal("100"), "ILS", rates) == Decimal("100")
    assert fx.to_base(Decimal("100"), "NIS", rates) == Decimal("100")
    assert fx.to_base(Decimal("100"), "XYZ", rates) is None
    assert fx.to_base(Decimal("100"), None, rates) is None


def test_rates_are_cached_and_the_network_is_not_hit_again(monkeypatch):
    calls = []
    monkeypatch.setattr(fx, "fetch_boi", lambda transport=None: calls.append(1) or fx.parse_boi(BOI))
    monkeypatch.setattr(fx, "_provider", lambda: "boi")
    a, b = fx.current_rates(), fx.current_rates()
    assert a is b and len(calls) == 1


def test_a_failed_fetch_keeps_the_last_good_rates(monkeypatch):
    monkeypatch.setattr(fx, "_provider", lambda: "boi")
    monkeypatch.setattr(fx, "fetch_boi", lambda transport=None: fx.parse_boi(BOI))
    good = fx.current_rates()
    fx._MEMORY["fetched_at"] = datetime(2000, 1, 1, tzinfo=UTC)  # expired

    def boom(transport=None):  # noqa: ANN001, ANN202
        raise httpx.ConnectTimeout("down")
    monkeypatch.setattr(fx, "fetch_boi", boom)
    assert fx.current_rates().rates == good.rates


def test_no_rates_at_all_means_no_conversion(monkeypatch):
    monkeypatch.setattr(fx, "_provider", lambda: "boi")

    def boom(transport=None):  # noqa: ANN001, ANN202
        raise httpx.ConnectTimeout("down")
    monkeypatch.setattr(fx, "fetch_boi", boom)
    assert fx.current_rates() is None


@pytest.mark.parametrize("payload", [{}, {"exchangeRates": "x"}, {"exchangeRates": [{"key": "USD"}]}, None])
def test_malformed_responses_are_rejected_not_trusted(payload):
    with pytest.raises(fx.FxUnavailable):
        fx.fetch_boi(transport(payload))


def test_http_errors_are_reported_as_unavailable():
    with pytest.raises(fx.FxUnavailable):
        fx.fetch_boi(transport({"x": 1}, status=503))


def test_static_provider_for_tests_and_offline_use(monkeypatch):
    monkeypatch.setattr(fx, "_provider", lambda: "static")
    rates = fx.current_rates()
    assert rates.source == "static" and rates.rates["USD"] > 0


# ---------------------------------------------------------------- ranking in shekels
def _inp(amount, risk_base=None, types=("PRICE_MISMATCH",)):  # noqa: ANN001, ANN202
    from app.services import priority as P

    return P.PriorityInput(exception_id=uuid.uuid4(), finding_types=list(types), amount_at_risk=Decimal(amount),
                           due_date=None, created_at=datetime(2026, 11, 1, tzinfo=UTC), risk_base=risk_base)


def test_dollar_risk_is_compared_in_shekels_for_the_critical_threshold():
    from app.services import priority as P

    usd = P.compute(_inp("2000", risk_base=Decimal("6652")), date(2026, 11, 22), Decimal("5000"))
    assert usd.level == "critical"
    assert {"code": "amount_at_risk", "params": {"amount": "2000.00"}} in usd.reasons  # shown in its own currency


def test_ranking_orders_by_shekel_value_across_currencies():
    from app.services import priority as P

    ils = _inp("3000", risk_base=Decimal("3000"))
    usd = _inp("1000", risk_base=Decimal("3326"))
    ranked = P.rank([(i, P.compute(i, date(2026, 11, 22), Decimal("99999"))) for i in (ils, usd)])
    assert ranked[0][0] is usd


def test_without_a_rate_the_nominal_amount_is_used():
    from app.services import priority as P

    assert P.compute(_inp("6000"), date(2026, 11, 22), Decimal("5000")).level == "critical"


@pytest.mark.integration
def test_queue_ranks_a_dollar_case_by_its_shekel_value(client, as_user):
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.models import Discrepancy, ExceptionCase, Invoice, ReconciliationRun, Supplier

    fin = as_user("finance@kinneret.example")
    org_id = client.get("/api/auth/me", headers=fin).json()["organization"]["id"]
    with session_scope(org_id) as s:
        sup = s.scalars(select(Supplier)).first()
        ids = {}
        for cur, risk in (("USD", "2000"), ("ILS", "3000")):
            inv = Invoice(organization_id=uuid.UUID(org_id), supplier_id=sup.id, status="exception",
                          invoice_number=f"FX-{cur}", currency=cur, total=Decimal("10000"))
            s.add(inv)
            s.flush()
            run = ReconciliationRun(organization_id=inv.organization_id, invoice_id=inv.id, outcome="discrepancies",
                                    mode="three_way", engine_version="t", result={}, tolerances={})
            s.add(run)
            s.flush()
            s.add(Discrepancy(organization_id=inv.organization_id, invoice_id=inv.id, run_id=run.id, type="PRICE_MISMATCH",
                              severity="critical", message="x", evidence={"amount_at_risk": risk}))
            s.add(ExceptionCase(organization_id=inv.organization_id, invoice_id=inv.id, title="x", status="open",
                                discrepancy_types=["PRICE_MISMATCH"]))
            ids[cur] = str(inv.id)
    items = client.get("/api/review/queue", headers=fin).json()["items"]
    usd = next(i for i in items if i["invoice_id"] == ids["USD"])
    ils = next(i for i in items if i["invoice_id"] == ids["ILS"])
    assert usd["priority"]["level"] == "critical" and ils["priority"]["level"] == "high"  # critical from 5,000 ILS
    assert usd["amount_at_risk"] == "2000.00" and usd["amount_at_risk_base"] == "6660.00"
    assert ils["amount_at_risk_base"] is None  # already in shekels
    assert usd["priority"]["rank"] < ils["priority"]["rank"]
