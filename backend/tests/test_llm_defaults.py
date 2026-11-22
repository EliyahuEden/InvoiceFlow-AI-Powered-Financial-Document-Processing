"""Groq is the default AI provider; without a key the app stays fully usable in offline mode."""
from __future__ import annotations

import pytest

from app.core.config import Settings

GROQ = "https://api.groq.com/openai/v1"


@pytest.fixture()
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def make(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_default_provider_is_groq(clean_env):
    s = make()
    assert (s.llm_provider, s.openai_base_url, s.effective_llm_model) == ("openai", GROQ, "openai/gpt-oss-120b")


def test_groq_without_a_key_falls_back_to_offline(clean_env):
    assert make().llm_enabled is False


def test_groq_with_a_key_is_enabled(clean_env):
    assert make(openai_api_key="gsk_test").llm_enabled is True


def test_local_openai_compatible_server_needs_no_key(clean_env):
    for url in ("http://host.docker.internal:11434/v1", "http://localhost:11434/v1", "http://127.0.0.1:8080/v1"):
        assert make(openai_base_url=url).llm_enabled is True, url


def test_hosted_endpoint_without_a_key_is_not_enabled(clean_env):
    assert make(openai_base_url="https://api.openai.com/v1").llm_enabled is False


def test_explicit_offline_stays_offline(clean_env):
    s = make(llm_provider="offline", openai_api_key="gsk_test")
    assert s.llm_enabled is False and s.effective_llm_model == "offline-deterministic"


def test_openai_without_base_url_keeps_its_own_default_model(clean_env):
    s = make(openai_base_url="", openai_api_key="sk-test")
    assert s.llm_enabled is True and s.effective_llm_model == "gpt-5.4-nano"
