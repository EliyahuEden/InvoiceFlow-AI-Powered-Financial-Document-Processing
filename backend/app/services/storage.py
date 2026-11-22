"""Object storage for original documents (S3-compatible, or local FS for tests/dev).

Keys are opaque and tenant-prefixed: ``{org_id}/{purpose}/{uuid}{ext}``. Original
filenames are never used as paths (prevents path traversal).
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def put_for_upload(session: Session, key: str, data: bytes, content_type: str) -> None:
    storage = get_storage()
    session.info.setdefault("pending_upload_objects", []).append((storage, key))
    storage.put(key, data, content_type)


@event.listens_for(Session, "after_commit")
def _keep_committed_uploads(session: Session) -> None:
    if not session.in_nested_transaction():
        session.info.pop("pending_upload_objects", None)


@event.listens_for(Session, "after_transaction_end")
def _cleanup_uncommitted_uploads(session: Session, transaction) -> None:
    if transaction.parent is None:
        for storage, key in session.info.pop("pending_upload_objects", ()):
            try:
                storage.delete(key)
            except Exception as exc:  # noqa: BLE001
                log.warning("upload_cleanup_failed", storage_key=key, error=str(exc))


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key.get_secret_value(),
            aws_secret_access_key=s.s3_secret_key.get_secret_value(),
            region_name=s.s3_region,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:  # noqa: BLE001
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               **sse_args(get_settings()))

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def sse_args(s: Settings) -> dict[str, str]:
    """put_object arguments for server-side encryption (see S3_SSE / S3_KMS_KEY_ID)."""
    if s.s3_sse == "none":
        return {}
    args = {"ServerSideEncryption": s.s3_sse}
    if s.s3_sse == "aws:kms" and s.s3_kms_key_id:
        args["SSEKMSKeyId"] = s.s3_kms_key_id
    return args


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(s.local_storage_dir)


def new_key(org_id: uuid.UUID, purpose: str, ext: str) -> str:
    return f"{org_id}/{purpose}/{uuid.uuid4().hex}{ext}"
