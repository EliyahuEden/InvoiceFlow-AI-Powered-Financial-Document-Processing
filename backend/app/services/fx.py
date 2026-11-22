"""Exchange rates for ranking money at risk across currencies.

Source: the Bank of Israel's official representative rates (public API, no key). Rates are cached for
FX_CACHE_HOURS in memory and in Redis, so a page view never waits on the network more than once; if the API is
down the last good rates are used; with no rates at all, ranking falls back to nominal amounts.

Conversion is used only to *rank* (priority level and order) and to show an approximate shekel value next to
foreign amounts. Invoice amounts, reconciliation and approvals always stay in the invoice's own currency.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.money import round_money

log = get_logger(__name__)
BOI_URL = "https://boi.org.il/PublicApi/GetExchangeRates"
BASE = "ILS"
ALIASES = {"NIS": "ILS", "₪": "ILS"}
REDIS_KEY = "invoiceflow:fx:rates"


class FxUnavailable(RuntimeError):
    pass


@dataclass
class Rates:
    rates: dict[str, Decimal]          # shekels per 1 unit of the currency
    as_of: date | None
    source: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_json(self) -> str:
        return json.dumps({"rates": {k: str(v) for k, v in self.rates.items()}, "source": self.source,
                           "as_of": self.as_of.isoformat() if self.as_of else None,
                           "fetched_at": self.fetched_at.isoformat()})

    @classmethod
    def from_json(cls, raw: str) -> Rates:
        d = json.loads(raw)
        return cls({k: Decimal(v) for k, v in d["rates"].items()},
                   date.fromisoformat(d["as_of"]) if d.get("as_of") else None, d["source"],
                   datetime.fromisoformat(d["fetched_at"]))


_MEMORY: dict = {"rates": None, "fetched_at": None, "failed_at": None}
RETRY_AFTER_FAILURE = timedelta(minutes=10)
_LOCK = threading.Lock()


def clear_cache() -> None:
    _MEMORY.update(rates=None, fetched_at=None, failed_at=None)


def _provider() -> str:
    return get_settings().fx_provider


def _redis():  # noqa: ANN202
    try:
        from app.services.events import get_redis

        return get_redis()
    except Exception:  # noqa: BLE001 - Redis is an optional cache here
        return None


def parse_boi(payload: object) -> Rates:
    """Parse the Bank of Israel payload; anything unexpected is rejected, never guessed."""
    items = payload.get("exchangeRates") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise FxUnavailable("unexpected Bank of Israel response")
    rates: dict[str, Decimal] = {}
    as_of: date | None = None
    for it in items:
        try:
            unit = Decimal(str(it.get("unit") or 1))
            rate = Decimal(str(it["currentExchangeRate"])) / unit
            code = str(it["key"]).upper()
        except (KeyError, TypeError, InvalidOperation, AttributeError):
            continue
        if rate > 0 and len(code) == 3:
            rates[code] = rate.normalize()
        stamp = str(it.get("lastUpdate") or "")[:10]
        try:
            as_of = max(as_of, date.fromisoformat(stamp)) if as_of else date.fromisoformat(stamp)
        except ValueError:
            pass
    if not rates:
        raise FxUnavailable("no usable rates in the Bank of Israel response")
    return Rates(rates, as_of, "Bank of Israel")


def fetch_boi(transport: httpx.BaseTransport | None = None) -> Rates:
    try:
        with httpx.Client(timeout=get_settings().fx_timeout_seconds, transport=transport) as client:
            r = client.get(BOI_URL, headers={"Accept": "application/json"})
            r.raise_for_status()
            return parse_boi(r.json())
    except FxUnavailable:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise FxUnavailable(f"Bank of Israel rates unavailable: {exc}") from exc


def _static() -> Rates:
    raw = json.loads(get_settings().fx_static_rates or "{}")
    return Rates({k.upper(): Decimal(str(v)) for k, v in raw.items()}, None, "static")


def current_rates() -> Rates | None:
    """The latest rates (cached), the last good rates if a refresh fails, or None if there are none."""
    provider = _provider()
    if provider == "none":
        return None
    if provider == "static":
        return _static()
    ttl = timedelta(hours=get_settings().fx_cache_hours)
    now = datetime.now(UTC)
    with _LOCK:
        cached: Rates | None = _MEMORY["rates"]
        if cached and _MEMORY["fetched_at"] and now - _MEMORY["fetched_at"] < ttl:
            return cached
        r = _redis()
        if r is not None:
            try:
                raw = r.get(REDIS_KEY)
                if raw:
                    shared = Rates.from_json(raw)
                    if now - shared.fetched_at < ttl:
                        _MEMORY.update(rates=shared, fetched_at=shared.fetched_at)
                        return shared
                    cached = cached or shared
            except Exception:  # noqa: BLE001
                pass
        failed_at = _MEMORY.get("failed_at")
        if failed_at and now - failed_at < RETRY_AFTER_FAILURE:
            return cached  # the bank was unreachable a moment ago: do not make every page wait for the timeout again
        try:
            fresh = fetch_boi()
        except Exception as exc:  # noqa: BLE001 - a rate refresh must never break a page
            log.warning("fx_rates_unavailable", error=str(exc)[:200], using_last_good=cached is not None)
            _MEMORY["failed_at"] = now
            return cached
        _MEMORY.update(rates=fresh, fetched_at=fresh.fetched_at, failed_at=None)
        if r is not None:
            try:
                r.set(REDIS_KEY, fresh.to_json(), ex=int(ttl.total_seconds()) * 4)
            except Exception:  # noqa: BLE001
                pass
        return fresh


def to_base(amount: Decimal | None, currency: str | None, rates: Rates | None) -> Decimal | None:
    """The amount in shekels, or None when it cannot be converted (unknown currency or no rates)."""
    if amount is None or not currency:
        return None
    code = ALIASES.get(currency.upper(), currency.upper())
    if code == BASE:
        return amount
    if rates is None or code not in rates.rates:
        return None
    return round_money(amount * rates.rates[code])


@dataclass(frozen=True)
class ApprovalRoute:
    steps: int
    total_base: Decimal | None   # the total in shekels that was compared, None when it could not be converted
    rate: Decimal | None         # shekels per unit, for foreign currencies
    rate_as_of: date | None


def approval_steps(total: Decimal | None, currency: str | None, threshold: Decimal, rates: Rates | None) -> ApprovalRoute:
    """The dual-approval threshold is a shekel amount, so a foreign invoice is compared in shekels.
    A foreign invoice that cannot be converted gets both approvals: a missing rate must never remove a control."""
    if total is None:
        return ApprovalRoute(1, None, None, None)
    base = to_base(total, currency or BASE, rates)
    code = ALIASES.get((currency or BASE).upper(), (currency or BASE).upper())
    rate = rates.rates.get(code) if rates is not None and code != BASE else None
    as_of = rates.as_of if rate is not None else None
    if base is None:
        return ApprovalRoute(2, None, None, None)
    return ApprovalRoute(2 if base > threshold else 1, base, rate, as_of)
