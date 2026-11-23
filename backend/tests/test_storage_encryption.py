"""Server-side encryption settings for the S3 document bucket (no network needed)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.storage import sse_args

SECRET = "x" * 40


def test_no_encryption_headers_by_default_for_local_dev():
    assert sse_args(Settings(jwt_secret=SECRET)) == {}


def test_sse_s3_and_sse_kms_headers():
    assert sse_args(Settings(jwt_secret=SECRET, s3_sse="AES256")) == {"ServerSideEncryption": "AES256"}
    assert sse_args(Settings(jwt_secret=SECRET, s3_sse="aws:kms", s3_kms_key_id="alias/invoiceflow")) == {
        "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": "alias/invoiceflow"}


def test_production_with_s3_requires_server_side_encryption():
    safe = {"cookie_secure": True, "cors_origins": ["https://invoiceflow.example.com"], "s3_secret_key": "k" * 40,  # the other gates
            "database_url": "postgresql+psycopg://invoiceflow_app:Q7vT2mW9xL4pR8sZ@db.internal:5432/invoiceflow",
            "migration_database_url": "postgresql+psycopg://invoiceflow:N3kD8fH2jP6tY1cV@db.internal:5432/invoiceflow"}
    with pytest.raises(ValidationError, match="S3_SSE"):
        Settings(jwt_secret=SECRET, environment="production", storage_backend="s3", **safe)
    Settings(jwt_secret=SECRET, environment="production", storage_backend="s3", s3_sse="aws:kms", **safe)
