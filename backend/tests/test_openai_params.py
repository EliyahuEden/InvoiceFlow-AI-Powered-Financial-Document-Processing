"""OpenAI request parameters for current models, checked against a fake client (no network, no cost)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.llm.provider import OpenAICompatibleProvider


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.kwargs = kwargs
        msg = SimpleNamespace(content=json.dumps({"ok": True}), tool_calls=None,
                              model_dump=lambda **_: {"role": "assistant", "content": ""})
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _provider(model: str, base_url: str | None = None, effort: str | None = None) -> tuple[OpenAICompatibleProvider, FakeCompletions]:
    p = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    fake = FakeCompletions()
    p.model, p.base_url, p.reasoning_effort_setting = model, base_url, effort
    p.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return p, fake


def _call(p: OpenAICompatibleProvider) -> None:
    p.structured(system="s", content="c", schema_name="x", schema={"type": "object"}, max_tokens=1500)


def test_official_api_uses_max_completion_tokens():
    p, fake = _provider("gpt-4.1-mini")
    _call(p)
    assert "max_tokens" not in fake.kwargs and fake.kwargs["max_completion_tokens"] == 1500
    assert "reasoning_effort" not in fake.kwargs


def test_reasoning_models_get_low_effort_and_room_to_think():
    p, fake = _provider("gpt-5.4-nano")
    _call(p)
    assert fake.kwargs["reasoning_effort"] == "low"
    assert fake.kwargs["max_completion_tokens"] > 1500  # visible answer budget plus reasoning headroom


def test_effort_is_configurable():
    p, fake = _provider("gpt-5.4-mini", effort="minimal")
    _call(p)
    assert fake.kwargs["reasoning_effort"] == "minimal"


def test_local_compatible_servers_keep_max_tokens():
    p, fake = _provider("llama3.1", base_url="http://localhost:11434/v1")
    _call(p)
    assert fake.kwargs["max_tokens"] == 1500 and "max_completion_tokens" not in fake.kwargs


def test_tool_calls_use_the_same_limits():
    p, fake = _provider("gpt-5.4-nano")
    p.chat_tools(system="s", messages=[{"role": "user", "content": "hi"}], tools=[], max_tokens=1500)
    assert fake.kwargs["reasoning_effort"] == "low" and "max_tokens" not in fake.kwargs
