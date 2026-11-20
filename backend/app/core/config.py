"""Application settings, loaded from environment variables (12-factor).

Secrets (JWT secret, API keys, storage credentials) are only ever read from the
environment and are never logged or returned by the API.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    session_idle_days: int = 7
    session_max_days: int = 30
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
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None  # e.g. http://localhost:11434/v1 for Ollama
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2
    # Optional price table for cost estimation, USD per 1M tokens:
    # {"model-id": {"input": 3.0, "output": 15.0}}. No prices are hard-coded: if a
    # model is absent the estimated cost is reported as unknown, never invented.
    llm_pricing_json: str = "{}"

    # --- retrieval ---
    embedding_backend: Literal["fastembed", "hash"] = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
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

    @field_validator("jwt_secret")
    @classmethod
    def _secret_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

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
        return {"anthropic": "claude-opus-5-5", "openai": "gpt-4o-mini", "offline": "offline-deterministic"}[
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
