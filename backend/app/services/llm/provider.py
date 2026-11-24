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
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


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


OFFICIAL_OPENAI_URL = "https://api.openai.com/v1"


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, model: str, *, api_key: str | None = None, base_url: str | None = None,
                 use_settings: bool = True, max_retries: int | None = None) -> None:
        """An OpenAI-compatible endpoint. Without arguments it uses OPENAI_API_KEY and OPENAI_BASE_URL; the fallback
        chain passes the official API's key and no base URL explicitly (``use_settings=False``)."""
        from openai import OpenAI
        from app.core.config import GROQ_BASE_URL

        s = get_settings()
        if use_settings:
            api_key = s.openai_api_key.get_secret_value() if s.openai_api_key else None
            base_url = s.openai_base_url or None
        # Always pass an explicit address: with base_url=None the OpenAI SDK reads the OPENAI_BASE_URL environment
        # variable (Groq's address in Docker), which would send an OpenAI key to another provider.
        base_url = base_url or OFFICIAL_OPENAI_URL
        self.model = model
        self.base_url = base_url
        # recorded in ai_calls and used for the paid/shared token budget
        self.name = "groq" if (self.base_url or "").rstrip("/") == GROQ_BASE_URL else "openai"
        self.reasoning_effort_setting = s.llm_reasoning_effort
        self.client = OpenAI(
            api_key=api_key or "not-needed",
            base_url=self.base_url,
            timeout=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries if max_retries is None else max_retries,
        )

    REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
    REASONING_HEADROOM = 4000  # tokens a reasoning model may spend thinking before it answers

    def _limits(self, max_tokens: int) -> dict:
        """Token-limit arguments for this endpoint. The official API takes max_completion_tokens
        (and reasoning models count their thinking against it); local OpenAI-compatible servers
        such as Ollama or vLLM still take max_tokens."""
        if (self.base_url or OFFICIAL_OPENAI_URL).rstrip("/") != OFFICIAL_OPENAI_URL:  # None also means the official API
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
        request = {
            "model": self.model, **self._limits(max_tokens),
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": inline_refs(t["schema"])}} for t in tools],
        }
        try:
            resp = self.client.chat.completions.create(**request)
        except Exception as exc:
            # gpt-oss on some servers (Groq) occasionally leaks a channel token into a tool name and the
            # server rejects the call ("Tool call validation failed"); sampling again usually succeeds.
            if "tool call validation failed" not in str(exc).lower():
                raise
            resp = self.client.chat.completions.create(**request)
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


COOLDOWN_SECONDS = 120
_cooldown_until: dict[str, float] = {}


class FallbackChain:
    """Providers in order (the paid primary, then the free fallback). Each call goes to the first provider that is not
    cooling down; when it fails (rate limit, quota, timeout, outage) the call moves to the next one and the failed
    provider is skipped for a short while. If every provider fails, the last error is raised and the caller takes its
    offline path, as it always has. All members speak the OpenAI message format, so a tool loop can continue on the
    next provider."""

    def __init__(self, providers: list[OpenAICompatibleProvider]) -> None:
        self.providers = providers
        self.last = providers[0]

    @property
    def name(self) -> str:
        return self.last.name

    @property
    def model(self) -> str:
        return self.last.model

    def _call(self, method: str, **kw: Any) -> LLMResult:
        now = time.monotonic()
        ready = [p for p in self.providers if _cooldown_until.get(p.name, 0) <= now] or self.providers[-1:]
        error: Exception | None = None
        for p in ready:
            try:
                result = getattr(p, method)(**kw)
                self.last = p
                return result
            except Exception as exc:  # noqa: BLE001 - any provider failure moves the call to the next provider
                error = exc
                if p is not self.providers[-1]:
                    _cooldown_until[p.name] = time.monotonic() + COOLDOWN_SECONDS
                log.warning("llm_provider_failed", provider=p.name, model=p.model, error=str(exc)[:200])
        assert error is not None
        raise error

    def structured(self, **kw: Any) -> LLMResult:
        return self._call("structured", **kw)

    def chat_tools(self, **kw: Any) -> LLMResult:
        return self._call("chat_tools", **kw)

    def tool_result_message(self, results: list[tuple[str, str]]) -> list[dict]:
        return OpenAICompatibleProvider.tool_result_message(results)


Provider = AnthropicProvider | OpenAICompatibleProvider | FallbackChain


def get_llm(org_id: uuid.UUID | str | None = None) -> Provider | None:
    """The model for this business, or None (offline). With OPENAI_PLATFORM_API_KEY the paid primary
    (OPENAI_PLATFORM_MODEL) comes first and the configured provider is its fallback. A business that used its paid
    budget for the day continues on the free fallback; one that also used its shared budget gets the offline path.
    Budgets are checked on every call, never cached."""
    primary, fallback = _platform_llm(), _configured_llm()
    if org_id is not None:
        from app.services import ai_budget

        if primary is not None and not ai_budget.allowed(org_id, "paid"):
            log.info("ai_paid_budget_exhausted", org_id=str(org_id))
            primary = None
        if fallback is not None and not ai_budget.allowed(org_id, ai_budget.bucket_for(fallback.name)):
            log.info("ai_budget_exhausted", org_id=str(org_id))
            fallback = None
    if primary is not None and isinstance(fallback, OpenAICompatibleProvider):
        return FallbackChain([primary, fallback])
    return primary or fallback


@lru_cache
def _platform_llm() -> OpenAICompatibleProvider | None:
    """The official OpenAI API, when OPENAI_PLATFORM_API_KEY is set (fails fast: the chain has a fallback)."""
    s = get_settings()
    key = s.openai_platform_api_key.get_secret_value() if s.openai_platform_api_key else ""
    if not key or s.llm_provider == "offline":
        return None
    return OpenAICompatibleProvider(s.openai_platform_model, api_key=key, base_url=OFFICIAL_OPENAI_URL, use_settings=False,
                                    max_retries=1)


@lru_cache
def _configured_llm() -> AnthropicProvider | OpenAICompatibleProvider | None:
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
