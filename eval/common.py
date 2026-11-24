"""Shared helpers for the evaluation scripts (run from the repository root)."""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("EMBEDDING_BACKEND", "fastembed")

RESULTS = ROOT / "eval" / "results"
DATA = ROOT / "data" / "demo"


def git_rev() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return None


def add_model_options(parser: ArgumentParser) -> None:
    parser.add_argument("--provider", choices=("groq", "openai", "anthropic", "ollama"),
                        help="override the configured provider for this run")
    parser.add_argument("--model", help="override the configured model for this run")


def configure_model(parser: ArgumentParser, args: Namespace) -> None:
    from app.core.config import GROQ_BASE_URL, LOCAL_LLM_HOSTS, get_settings
    from urllib.parse import urlparse

    settings = get_settings()
    from app.services.llm import provider as llm_provider

    if args.provider:
        settings.llm_provider = "anthropic" if args.provider == "anthropic" else "openai"
        settings.llm_model = None
    if args.provider == "groq":
        settings.openai_base_url = GROQ_BASE_URL
    if args.provider == "openai":  # the official API, with its own key (OPENAI_PLATFORM_API_KEY)
        if settings.openai_platform_api_key is None or not settings.openai_platform_api_key.get_secret_value():
            parser.error("--provider openai requires OPENAI_PLATFORM_API_KEY in .env")
        if not args.model:
            parser.error("--provider openai requires --model")
        settings.openai_api_key = settings.openai_platform_api_key
        settings.openai_base_url = "https://api.openai.com/v1"  # explicit: never the OPENAI_BASE_URL variable
    if args.provider == "ollama":
        if not args.model:
            parser.error("--provider ollama requires --model")
        if (urlparse(settings.openai_base_url or "").hostname or "") not in LOCAL_LLM_HOSTS:
            settings.openai_base_url = "http://127.0.0.1:11434/v1"
        settings.openai_api_key = None
    if args.model:
        settings.llm_model = args.model
    if args.provider:
        # an explicit provider is benchmarked alone: never through the paid primary of the fallback chain
        settings.openai_platform_api_key = None
    llm_provider._platform_llm.cache_clear()
    llm_provider._configured_llm.cache_clear()


def daily_quota_exhausted(message: str) -> bool:
    message = message.lower()
    return "per day" in message or "(tpd)" in message or "(rpd)" in message


def write_result(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "git_rev": git_rev(),
               "python": sys.version.split()[0], **payload}
    path = RESULTS / f"{name}_latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def p50(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": None if p is None else round(p, 3),
            "recall": None if r is None else round(r, 3), "f1": None if f is None else round(f, 3)}
