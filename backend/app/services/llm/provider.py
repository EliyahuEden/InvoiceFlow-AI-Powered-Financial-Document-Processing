"""Configurable LLM provider abstraction.

Providers:
- ``anthropic``: Claude via the official Anthropic SDK. Structured output is obtained
  by forcing a single tool whose ``input_schema`` is the Pydantic JSON schema.
- ``openai``: any OpenAI-compatible endpoint (OpenAI, or a local Ollama/vLLM server via
  ``OPENAI_BASE_URL``) using ``response_format=json_schema``.
- ``offline``: no model. Callers must use their deterministic fallback and label the
  output as ``offline-deterministic``. Nothing pre-recorded is ever presented as live
  inference.

Every call returns token usage and latency so it can be recorded in ``ai_calls``.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.core.config import get_settings


class LLMUnavailable(RuntimeError):
    pass


class LLMOutputInvalid(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMResult:
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    data: dict | None = None          # structured output
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    raw_assistant: Any = None         # provider-native assistant message for tool loops

    @property
    def cost_usd(self) -> float | None:
        price = get_settings().pricing.get(self.model)
        if not price or self.input_tokens is None or self.output_tokens is None:
            return None
        return round((self.input_tokens * price["input"] + self.output_tokens * price["output"]) / 1_000_000, 6)


def inline_refs(schema: dict) -> dict:
    """Inline ``$defs``/``$ref`` so the schema is self-contained for every provider."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                merged = {**resolve(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str) -> None:
        import anthropic

        s = get_settings()
        self.model = model
        self.client = anthropic.Anthropic(
            api_key=s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None,
            timeout=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries,
        )

    def structured(self, *, system: str, content: list[dict] | str, schema_name: str, schema: dict,
                   max_tokens: int = 8000) -> LLMResult:
        t0 = time.perf_counter()
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            tools=[{"name": schema_name, "description": "Return the result in this exact structure.",
                    "input_schema": inline_refs(schema)}],
            tool_choice={"type": "tool", "name": schema_name},
            messages=[{"role": "user", "content": content}],
        )
        data = next((b.input for b in msg.content if b.type == "tool_use"), None)
        if data is None:
            raise LLMOutputInvalid(f"model returned no structured output (stop_reason={msg.stop_reason})")
        return LLMResult(self.name, self.model, int((time.perf_counter() - t0) * 1000),
                         msg.usage.input_tokens, msg.usage.output_tokens, data=data, stop_reason=msg.stop_reason)

    def chat_tools(self, *, system: str, messages: list[dict], tools: list[dict], max_tokens: int = 4000) -> LLMResult:
        t0 = time.perf_counter()
        msg = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages,
            tools=[{"name": t["name"], "description": t["description"], "input_schema": inline_refs(t["schema"])}
                   for t in tools],
        )
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in msg.content if b.type == "tool_use"]
        text = "".join(b.text for b in msg.content if b.type == "text")
        return LLMResult(self.name, self.model, int((time.perf_counter() - t0) * 1000), msg.usage.input_tokens,
                         msg.usage.output_tokens, text=text, tool_calls=calls, stop_reason=msg.stop_reason,
                         raw_assistant={"role": "assistant", "content": [b.model_dump() for b in msg.content]})

    @staticmethod
    def tool_result_message(results: list[tuple[str, str]]) -> dict:
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": out}
                                            for tid, out in results]}


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, model: str) -> None:
        from openai import OpenAI

        s = get_settings()
        self.model = model
        self.base_url = s.openai_base_url or None
        self.reasoning_effort_setting = s.llm_reasoning_effort
        self.client = OpenAI(
            api_key=s.openai_api_key.get_secret_value() if s.openai_api_key else "not-needed",
            base_url=s.openai_base_url or None,
            timeout=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries,
        )

    REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
    REASONING_HEADROOM = 4000  # tokens a reasoning model may spend thinking before it answers

    def _limits(self, max_tokens: int) -> dict:
        """Token-limit arguments for this endpoint. The official API takes max_completion_tokens
        (and reasoning models count their thinking against it); local OpenAI-compatible servers
        such as Ollama or vLLM still take max_tokens."""
        if self.base_url:
            return {"max_tokens": max_tokens}
        if self.model.startswith(self.REASONING_PREFIXES):
            return {"max_completion_tokens": max_tokens + self.REASONING_HEADROOM,
                    "reasoning_effort": self.reasoning_effort_setting or "low"}
        return {"max_completion_tokens": max_tokens}

    @staticmethod
    def _to_openai_content(content: list[dict] | str) -> Any:
        if isinstance(content, str):
            return content
        parts = []
        for c in content:
            if c["type"] == "text":
                parts.append({"type": "text", "text": c["text"]})
            elif c["type"] == "image":
                src = c["source"]
                parts.append({"type": "image_url",
                              "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}})
        return parts

    def structured(self, *, system: str, content: list[dict] | str, schema_name: str, schema: dict,
                   max_tokens: int = 8000) -> LLMResult:
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model,
            **self._limits(max_tokens),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": self._to_openai_content(content)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": schema_name, "schema": inline_refs(schema), "strict": False}},
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMOutputInvalid("model returned non-JSON output") from exc
        u = resp.usage
        return LLMResult(self.name, self.model, int((time.perf_counter() - t0) * 1000),
                         u.prompt_tokens if u else None, u.completion_tokens if u else None, data=data,
                         stop_reason=resp.choices[0].finish_reason)

    def chat_tools(self, *, system: str, messages: list[dict], tools: list[dict], max_tokens: int = 4000) -> LLMResult:
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model, **self._limits(max_tokens),
            messages=[{"role": "system", "content": system}, *messages],
            tools=[{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                      "parameters": inline_refs(t["schema"])}} for t in tools],
        )
        m = resp.choices[0].message
        calls = [ToolCall(tc.id, tc.function.name, json.loads(tc.function.arguments or "{}")) for tc in m.tool_calls or []]
        u = resp.usage
        return LLMResult(self.name, self.model, int((time.perf_counter() - t0) * 1000),
                         u.prompt_tokens if u else None, u.completion_tokens if u else None,
                         text=m.content or "", tool_calls=calls, stop_reason=resp.choices[0].finish_reason,
                         raw_assistant=m.model_dump(exclude_none=True))

    @staticmethod
    def tool_result_message(results: list[tuple[str, str]]) -> list[dict]:
        return [{"role": "tool", "tool_call_id": tid, "content": out} for tid, out in results]


@lru_cache
def get_llm() -> AnthropicProvider | OpenAICompatibleProvider | None:
    """Return the configured provider, or None in offline mode / without credentials."""
    s = get_settings()
    if not s.llm_enabled:
        return None
    if s.llm_provider == "anthropic":
        return AnthropicProvider(s.effective_llm_model)
    if s.llm_provider == "openai":
        return OpenAICompatibleProvider(s.effective_llm_model)
    return None


def mode_label() -> str:
    llm = get_llm()
    return f"llm:{llm.model}" if llm else "offline-deterministic"
