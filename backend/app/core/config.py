"""Application settings, loaded from environment variables (12-factor).

Secrets (JWT secret, API keys, storage credentials) are only ever read from the
environment and are never logged or returned by the API.
"""
from __future__ import annotations

import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_core import PydanticUseDefault
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "InvoiceFlow"

    # --- database ---
    database_url: str = "postgresql+psycopg://invoiceflow_app:invoiceflow_app_dev@localhost:5433/invoiceflow"
    migration_database_url: str = "postgresql+psycopg://invoiceflow:invoiceflow_dev@localhost:5433/invoiceflow"

    # --- redis (pub/sub progress + rate limiting) ---
    redis_url: str = "redis://localhost:6380/0"

    # --- auth ---
    jwt_secret: SecretStr = SecretStr("dev-only-change-me-0123456789abcdef0123456789")
    jwt_algorithm: str = "HS256"
    # Short-lived access JWTs bound to a server-side session (revocable); the session is
    # kept alive by a rotating refresh token (idle timeout) up to an absolute maximum.
    access_token_minutes: int = 15
    # Fallbacks; each organization can tune these (Settings → security). Small and medium
    # businesses: sign in again after a workday of inactivity, and at least weekly.
    session_idle_hours: int = 8
    session_max_days: int = 7
    sse_ticket_seconds: int = 30
    rate_limit_refresh_per_minute: int = 60
    cookie_secure: bool = False

    # --- storage ---
    storage_backend: Literal["s3", "local"] = "local"
    local_storage_dir: Path = REPO_ROOT / ".data" / "documents"
    s3_endpoint_url: str | None = "http://localhost:8333"
    s3_access_key: SecretStr = SecretStr("invoiceflow")
    s3_secret_key: SecretStr = SecretStr("invoiceflow_dev_secret")
    s3_bucket: str = "invoiceflow-documents"
    s3_region: str = "us-east-1"
    # Server-side encryption for uploaded originals: AES256 (SSE-S3) or aws:kms (SSE-KMS).
    # Required in production; the local SeaweedFS dev server does not implement it.
    s3_sse: Literal["none", "AES256", "aws:kms"] = "none"
    s3_kms_key_id: str | None = None
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 50

    # --- LLM ---
    llm_provider: Literal["offline", "anthropic", "openai"] = "offline"
    llm_model: str = ""
    # Reasoning models (gpt-5 family, o-series): minimal | low | medium | high. Default low keeps cost down.
    llm_reasoning_effort: str | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None  # e.g. http://localhost:11434/v1 for Ollama
    # rules_first: the free rule-based extractor reads every invoice and the LLM is asked only for
    # fields that are missing or do not add up. llm_first: every invoice goes to the LLM, rules as backup.
    extraction_mode: Literal["rules_first", "llm_first"] = "rules_first"
    llm_timeout_seconds: float = 120.0
    # Cap on answer tokens per extraction call. Lower it for providers whose free tier counts the
    # requested maximum against a small tokens-per-minute budget (e.g. Groq: 3000).
    llm_max_output_tokens: int = 8000
    llm_max_retries: int = 2
    # Optional price table for cost estimation, USD per 1M tokens:
    # {"model-id": {"input": 3.0, "output": 15.0}}. No prices are hard-coded: if a
    # model is absent the estimated cost is reported as unknown, never invented.
    llm_pricing_json: str = "{}"

    # --- retrieval ---
    embedding_backend: Literal["fastembed", "hash"] = "fastembed"
    # multilingual-e5-large: dense MRR 0.642 -> 0.879 over MiniLM on the RAG benchmark
    # (eval/results/rag_e5_latest.json). Changing the model changes the dimension: run
    # `python -m app.cli migrate` (resizes the column) and `python -m app.cli reindex-embeddings`.
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    reranker_backend: Literal["none", "fastembed"] = "fastembed"
    reranker_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    model_cache_dir: Path = REPO_ROOT / ".data" / "models"
    retrieval_mode: Literal["bm25", "dense", "hybrid", "hybrid_rerank"] = "hybrid_rerank"
    chunking_strategy: Literal["fixed", "clause"] = "clause"

    # --- OCR ---
    tesseract_cmd: str | None = None
    ocr_languages: str = "heb+eng"
    native_text_min_chars_per_page: int = 40

    # --- worker ---
    worker_poll_seconds: float = 1.0
    job_lock_timeout_seconds: int = 300

    # --- misc ---
    eval_results_dir: Path = REPO_ROOT / "eval" / "results"
    rate_limit_login_per_minute: int = 10
    rate_limit_upload_per_minute: int = 30
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("*", mode="before")
    @classmethod
    def _strip_env_comments(cls, v: object) -> object:
        """Docker's env_file keeps "KEY=value  # note" as the whole value: drop such comments.
        A '#' only starts a comment at the start or after whitespace, so 'a#b' is kept."""
        if isinstance(v, str):
            if v.lstrip().startswith("#"):
                raise PydanticUseDefault  # e.g. OPENAI_BASE_URL=# e.g. http://... -> the field's default
            return re.split(r"\s+#", v, maxsplit=1)[0].strip()
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _secret_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @model_validator(mode="after")
    def _production_is_safe(self) -> Settings:
        """Refuse to start a production deployment on development defaults (audit SEC-02)."""
        if self.environment != "production":
            return self
        problems = []
        if self.jwt_secret.get_secret_value().startswith("dev-only"):
            problems.append("JWT_SECRET is the development placeholder")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true (cookies only over HTTPS)")
        if self.storage_backend == "local":
            problems.append("STORAGE_BACKEND=local is not durable; use s3")
        if any("localhost" in o or "127.0.0.1" in o or o == "*" for o in self.cors_origins):
            problems.append("CORS_ORIGINS must list the real HTTPS origins, not localhost or *")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @model_validator(mode="after")
    def _production_encrypts_documents(self) -> Settings:
        if self.environment == "production" and self.storage_backend == "s3" and self.s3_sse == "none":
            raise ValueError("S3_SSE must be AES256 or aws:kms in production (documents must be encrypted at rest)")
        return self

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        try:
            return json.loads(self.llm_pricing_json or "{}")
        except json.JSONDecodeError:
            return {}

    @property
    def effective_llm_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        return {"anthropic": "claude-opus-5-5", "openai": "gpt-5.4-nano", "offline": "offline-deterministic"}[
            self.llm_provider
        ]

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key is not None and bool(self.anthropic_api_key.get_secret_value())
        if self.llm_provider == "openai":
            return bool(self.openai_base_url) or (
                self.openai_api_key is not None and bool(self.openai_api_key.get_secret_value())
            )
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
