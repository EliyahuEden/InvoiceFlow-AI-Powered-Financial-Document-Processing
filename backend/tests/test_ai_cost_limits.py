"""AI spending guards: per-user rate limits on model-backed endpoints, a daily token budget per business that
falls back to offline mode, and sign-up off by default in production."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.config import Settings, get_settings
from app.services import ai_budget, ratelimit
from app.services.events import get_redis
from app.services.llm import provider as llm_provider
from app.services.llm.provider import LLMResult


@pytest.fixture()
def fresh_redis():
    get_redis().flushdb()
    yield
    get_redis().flushdb()


@pytest.fixture()
def budget(monkeypatch):
    def set_budget(tokens: int) -> None:
        monkeypatch.setattr(get_settings(), "ai_daily_token_budget", tokens)
    return set_budget


# ---------------------------------------------------------------- daily token budget
def test_usage_accumulates_per_business_and_day(fresh_redis, budget):
    budget(1000)
    a, b = uuid.uuid4(), uuid.uuid4()
    ai_budget.charge(a, 600)
    ai_budget.charge(a, 300)
    ai_budget.charge(b, 50)
    assert (ai_budget.used_today(a), ai_budget.used_today(b)) == (900, 50)
    assert ai_budget.allowed(a) and ai_budget.allowed(b)
    ai_budget.charge(a, 100)
    assert not ai_budget.allowed(a)      # 1000 of 1000 used: the next call would go over
    assert ai_budget.allowed(b)          # one business never uses up another's budget


def test_zero_budget_means_unlimited(fresh_redis, budget):
    budget(0)
    org = uuid.uuid4()
    ai_budget.charge(org, 10_000_000)
    assert ai_budget.allowed(org)


def test_an_exhausted_business_gets_the_offline_path(fresh_redis, budget, monkeypatch):
    budget(1000)
    configured = Settings(_env_file=None, llm_provider="openai", openai_api_key="gsk_test", ai_daily_token_budget=1000)
    monkeypatch.setattr(llm_provider, "get_settings", lambda: configured)
    llm_provider._configured_llm.cache_clear()
    monkeypatch.setattr(llm_provider, "_configured_llm", llm_provider._configured_llm.__wrapped__)  # no cache in this test
    org = uuid.uuid4()
    assert llm_provider.get_llm(org) is not None
    ai_budget.charge(org, 1000)
    assert llm_provider.get_llm(org) is None
    assert llm_provider.get_llm(uuid.uuid4()) is not None


def test_model_calls_are_charged_when_recorded(world, budget):
    from app.core.db import session_scope
    from app.services.llm.telemetry import record_call

    budget(1000)
    org = world["org_id"]
    with session_scope(org) as session:
        record_call(session, org_id=org, kind="rag", workflow="rag.ask", prompt_version="v",
                    result=LLMResult(provider="openai", model="m", latency_ms=5, input_tokens=300, output_tokens=120))
        record_call(session, org_id=org, kind="ocr", workflow="invoice.ocr", prompt_version=None, provider="tesseract")
    assert ai_budget.used_today(org) == 420


# ---------------------------------------------------------------- per-user rate limits on model-backed endpoints
@pytest.fixture()
def fixed_rate_window(monkeypatch):
    # Keep requests in one fixed Redis window even if the test starts just before a minute changes.
    monkeypatch.setattr(ratelimit, "time", SimpleNamespace(time=lambda: 30.0))


def test_policy_questions_are_rate_limited_per_user(client, as_user, monkeypatch, fixed_rate_window):
    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_minute", 2)
    fin = as_user("finance@kinneret.example")
    codes = [client.post("/api/knowledge/ask", headers=fin, json={"query": "מה תנאי התשלום?"}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    other = as_user("procurement@kinneret.example")
    assert client.post("/api/knowledge/ask", headers=other, json={"query": "payment terms"}).status_code == 200


def test_investigations_are_rate_limited_per_user(client, as_user, monkeypatch, fixed_rate_window):
    from tests.conftest import upload_invoice

    fin = as_user("finance@kinneret.example")
    iid = upload_invoice(client, fin, "03_price_mismatch_bluewave_en.pdf")["invoice_id"]
    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_minute", 1)
    first = client.post(f"/api/invoices/{iid}/investigate", headers=fin)
    assert first.status_code == 202, first.text
    assert client.post(f"/api/invoices/{iid}/investigate", headers=fin).status_code == 429


# ---------------------------------------------------------------- sign-up
def test_signup_is_off_by_default_in_production():
    assert Settings.model_construct(environment="production", allow_signup=None).signup_enabled is False
    assert Settings.model_construct(environment="production", allow_signup=True).signup_enabled is True
    assert Settings.model_construct(environment="development", allow_signup=None).signup_enabled is True
    assert Settings.model_construct(environment="development", allow_signup=False).signup_enabled is False
