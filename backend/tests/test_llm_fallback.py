"""The model fallback chain: the paid primary (OpenAI gpt-4.1-mini), then the free fallback (Groq), then offline.

A failing provider moves the call to the next one and is skipped for a short cooldown. The paid primary has its own
daily token budget per business; when it is used up the business continues on the free fallback, and when that
budget is used up too it gets the offline path. A visitor address has a daily cap on AI questions."""
from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.services import ai_budget
from app.services.llm import provider as llm_provider
from app.services.llm.provider import FallbackChain, LLMResult


class Fake:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name, self.model, self.fail, self.calls = name, f"{name}-model", fail, 0

    def structured(self, **kw):  # noqa: ANN003, ANN201
        self.calls += 1
        if self.fail:
            raise RuntimeError("Error code: 429 - rate limit")
        return LLMResult(self.name, self.model, 5, 10, 5, data={"ok": True})

    chat_tools = structured


@pytest.fixture()
def fresh_redis():
    from app.services.events import get_redis

    get_redis().flushdb()
    yield
    get_redis().flushdb()


@pytest.fixture(autouse=True)
def no_cooldowns(monkeypatch):
    monkeypatch.setattr(llm_provider, "_cooldown_until", {})


def test_the_primary_answers_when_it_works():
    primary, fallback = Fake("openai"), Fake("groq")
    chain = FallbackChain([primary, fallback])
    assert chain.structured(system="s", content="c", schema_name="x", schema={}).provider == "openai"
    assert (primary.calls, fallback.calls) == (1, 0) and chain.model == "openai-model"


def test_a_failing_primary_hands_the_call_to_the_fallback_and_cools_down():
    primary, fallback = Fake("openai", fail=True), Fake("groq")
    chain = FallbackChain([primary, fallback])
    assert chain.chat_tools(system="s", messages=[], tools=[]).provider == "groq"
    assert chain.name == "groq" and chain.model == "groq-model"          # labels follow the provider that answered
    chain.structured(system="s", content="c", schema_name="x", schema={})
    assert primary.calls == 1 and fallback.calls == 2                  # the primary is skipped while cooling down


def test_when_every_provider_fails_the_caller_gets_the_error():
    chain = FallbackChain([Fake("openai", fail=True), Fake("groq", fail=True)])
    with pytest.raises(RuntimeError, match="429"):
        chain.structured(system="s", content="c", schema_name="x", schema={})


def _settings(monkeypatch, **kw) -> None:  # noqa: ANN003
    configured = Settings(_env_file=None, llm_provider="openai", openai_api_key="gsk_test",
                          openai_platform_api_key="sk-test", ai_daily_token_budget=1000, ai_paid_daily_token_budget=500, **kw)
    monkeypatch.setattr(llm_provider, "get_settings", lambda: configured)
    monkeypatch.setattr(ai_budget, "get_settings", lambda: configured)
    monkeypatch.setattr(llm_provider, "_platform_llm", llm_provider._platform_llm.__wrapped__)
    monkeypatch.setattr(llm_provider, "_configured_llm", llm_provider._configured_llm.__wrapped__)


def test_with_both_keys_the_paid_model_leads_and_groq_follows(monkeypatch):
    _settings(monkeypatch)
    llm = llm_provider.get_llm()
    assert isinstance(llm, FallbackChain)
    assert [(p.name, p.model) for p in llm.providers] == [("openai", "gpt-4.1-mini"), ("groq", "openai/gpt-oss-120b")]


@pytest.mark.integration
def test_a_used_up_paid_budget_falls_back_to_groq_then_offline(monkeypatch, fresh_redis):
    _settings(monkeypatch)
    org = uuid.uuid4()
    assert isinstance(llm_provider.get_llm(org), FallbackChain)
    ai_budget.charge(org, 500, "paid")
    llm = llm_provider.get_llm(org)
    assert not isinstance(llm, FallbackChain) and llm.name == "groq"
    ai_budget.charge(org, 1000, "shared")
    assert llm_provider.get_llm(org) is None
    assert isinstance(llm_provider.get_llm(uuid.uuid4()), FallbackChain)  # another business is unaffected


def test_offline_mode_uses_no_model_even_with_keys(monkeypatch):
    configured = Settings(_env_file=None, llm_provider="offline", openai_api_key="gsk_test", openai_platform_api_key="sk-test")
    monkeypatch.setattr(llm_provider, "get_settings", lambda: configured)
    monkeypatch.setattr(llm_provider, "_platform_llm", llm_provider._platform_llm.__wrapped__)
    monkeypatch.setattr(llm_provider, "_configured_llm", llm_provider._configured_llm.__wrapped__)
    assert llm_provider.get_llm() is None


def test_calls_are_charged_to_the_paid_or_shared_budget():
    assert ai_budget.bucket_for("openai") == "paid" and ai_budget.bucket_for("anthropic") == "paid"
    assert ai_budget.bucket_for("groq") == "shared" and ai_budget.bucket_for(None) == "shared"


@pytest.mark.integration
def test_a_visitor_address_has_a_daily_cap_on_ai_questions(client, as_user, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_day", 2)
    h = as_user("finance@kinneret.example")
    codes = [client.post("/api/copilot/ask", headers=h, json={"question": "What is most urgent?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_the_openai_key_only_ever_goes_to_openai(monkeypatch):
    """With base_url=None the OpenAI SDK would read OPENAI_BASE_URL (Groq's address in Docker) and send the OpenAI
    key there. The paid primary always names api.openai.com explicitly."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    _settings(monkeypatch)
    primary = llm_provider.get_llm().providers[0]
    assert str(primary.client.base_url).rstrip("/") == "https://api.openai.com/v1" and primary.name == "openai"
    assert "max_completion_tokens" in primary._limits(100)          # official API token argument
