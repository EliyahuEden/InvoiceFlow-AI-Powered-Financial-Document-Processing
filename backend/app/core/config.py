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
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_core import PydanticUseDefault
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEV_DB_PASSWORDS = (":invoiceflow_dev@", ":invoiceflow_app_dev@")
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
LOCAL_LLM_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}


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
    # self-service business sign-up (each sign-up creates an isolated organization and its first administrator)
    # None = on, except in production, where public sign-up must be turned on explicitly.
    allow_signup: bool | None = None
    # Tokens per business per UTC day across all model calls; then that business runs offline. 0 = unlimited.
    ai_daily_token_budget: int = 100_000
    # Daily tokens per business on the paid primary (OPENAI_PLATFORM_API_KEY). When used up, the business continues
    # on the free fallback (Groq), which keeps its own ai_daily_token_budget; 0 = unlimited.
    ai_paid_daily_token_budget: int = 300_000
    # Model-backed requests (policy answers, Copilot, investigations) per user per minute.
    rate_limit_ai_per_minute: int = 20
    rate_limit_ai_per_day: int = 40  # AI questions per visitor address per day (0 = no daily cap)
    rate_limit_signup_per_hour: int = 10
    # "Try the demo": each visitor gets a private copy of the template workspace, deleted after demo_sandbox_hours
    demo_sandbox_enabled: bool = True
    demo_sandbox_template: str = "kinneret"
    demo_sandbox_hours: int = 24
    rate_limit_demo_per_day: int = 5  # sandboxes per visitor address per day (each has its own AI budget)
    sandbox_expiry_check_seconds: int = 300
    rate_limit_password_reset_per_hour: int = 5
    rate_limit_mfa_per_5min: int = 6  # wrong-code tries per user; a 6-digit code cannot be guessed at this rate
    # Proxies whose X-Forwarded-For is believed (the web app's proxy, a load balancer). Comma-separated CIDRs.
    trusted_proxies: str = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
    # How many trusted proxies append to X-Forwarded-For: 1 = the web app's proxy; 2 = a load balancer in front of it.
    trusted_proxy_hops: int = 1
    # --- email (password reset, invitations). auto = SMTP when SMTP_HOST is set, otherwise log only.
    email_backend: Literal["auto", "smtp", "console", "memory"] = "auto"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    email_from: str = "InvoiceFlow <no-reply@invoiceflow.local>"
    app_base_url: str = "http://localhost:3000"  # the web app's public address, used in emailed links
    password_reset_ttl_minutes: int = 60
    # --- /health/alerts thresholds (an uptime monitor polls it; 503 means a person should look)
    alert_queue_max_minutes: int = 15        # a runnable job waiting longer means the worker is down or stuck
    alert_failed_jobs_24h: int = 5
    alert_ai_error_rate: float = 0.5         # share of AI calls failing in the last hour...
    alert_ai_min_calls: int = 5              # ...counted only from this many calls on
    backup_status_file: str | None = None    # the backup service's last_success marker (unset: not checked)
    alert_backup_max_hours: int = 26
    invite_ttl_hours: int = 72
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
    # Default: Groq (OpenAI-compatible). Without OPENAI_API_KEY the app runs fully offline.
    llm_provider: Literal["offline", "anthropic", "openai"] = "openai"
    llm_model: str = ""
    # Reasoning models (gpt-5 family, o-series): minimal | low | medium | high. Default low keeps cost down.
    llm_reasoning_effort: str | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    # A key for the official OpenAI API, kept apart from OPENAI_API_KEY (which usually holds the Groq key), so both
    # providers can be configured at once: used by `eval/ --provider openai` and the provider fallback chain.
    openai_platform_api_key: SecretStr | None = None
    # The primary model on the official OpenAI API when OPENAI_PLATFORM_API_KEY is set; the configured provider
    # (usually Groq) becomes its fallback, then the offline path. gpt-4.1-mini scored 32/32 Copilot and 35/35 policy
    # answers (eval/results/*_gpt41mini_*), the cheapest model at full score.
    openai_platform_model: str = "gpt-4.1-mini"
    openai_base_url: str | None = GROQ_BASE_URL  # empty = api.openai.com; http://localhost:11434/v1 for Ollama
    # rules_first: the free rule-based extractor reads every invoice and the LLM is asked only for
    # fields that are missing or do not add up. llm_first: every invoice goes to the LLM, rules as backup.
    extraction_mode: Literal["rules_first", "llm_first"] = "rules_first"
    llm_timeout_seconds: float = 120.0
    # Cap on answer tokens per extraction call. Lower it for providers whose free tier counts the
    # requested maximum against a small tokens-per-minute budget (e.g. Groq: 3000).
    llm_max_output_tokens: int = 8000

    # --- exchange rates (ranking money at risk across currencies) ---
    # boi: Bank of Israel representative rates (public API); static: fx_static_rates (tests, offline); none: no conversion
    fx_provider: Literal["boi", "static", "none"] = "boi"
    fx_static_rates: str = '{"USD": "3.33", "EUR": "3.65", "GBP": "4.36"}'
    fx_cache_hours: int = 6
    fx_timeout_seconds: float = 5.0
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
    job_lock_timeout_seconds: int = Field(300, ge=1)

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
        if self.effective_email_backend == "smtp" and not self.app_base_url.startswith("https://"):
            problems.append("APP_BASE_URL must be the public https:// address (it is used in emailed links)")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true (cookies only over HTTPS)")
        if self.storage_backend == "local":
            problems.append("STORAGE_BACKEND=local is not durable; use s3")
        if any("localhost" in o or "127.0.0.1" in o or o == "*" for o in self.cors_origins):
            problems.append("CORS_ORIGINS must list the real HTTPS origins, not localhost or *")
        # the passwords shipped for local development are public (they are in this repository)
        for name, url in (("DATABASE_URL", self.database_url), ("MIGRATION_DATABASE_URL", self.migration_database_url)):
            if any(dev in url for dev in DEV_DB_PASSWORDS):
                problems.append(f"{name} uses the development database password; set a strong one")
        if self.s3_secret_key.get_secret_value() == "invoiceflow_dev_secret":
            problems.append("S3_SECRET_KEY is the development secret")
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
    def effective_email_backend(self) -> str:
        if self.email_backend != "auto":
            return self.email_backend
        return "smtp" if self.smtp_host else "console"

    @property
    def email_enabled(self) -> bool:
        """True when emails actually reach people (or the test outbox), so links can replace shown passwords."""
        return self.effective_email_backend in ("smtp", "memory")

    @property
    def signup_enabled(self) -> bool:
        return self.allow_signup if self.allow_signup is not None else self.environment != "production"

    @property
    def effective_llm_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "openai" and (self.openai_base_url or "").rstrip("/") == GROQ_BASE_URL:
            return GROQ_DEFAULT_MODEL
        return {"anthropic": "claude-opus-5-5", "openai": "gpt-5.4-nano", "offline": "offline-deterministic"}[
            self.llm_provider
        ]

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key is not None and bool(self.anthropic_api_key.get_secret_value())
        if self.llm_provider == "openai":
            if self.openai_api_key is not None and self.openai_api_key.get_secret_value():
                return True
            # A local server (Ollama, vLLM) needs no key; a hosted one without a key would only return 401s.
            host = urlparse(self.openai_base_url or "").hostname or ""
            return host in LOCAL_LLM_HOSTS
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
