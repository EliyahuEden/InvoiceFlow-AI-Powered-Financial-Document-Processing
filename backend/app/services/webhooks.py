"""Outbound webhooks: signed event notifications delivered through the PostgreSQL job queue.

Flow: a state change calls :func:`emit` inside its own transaction. That writes one ``webhook_deliveries`` row per
subscribed endpoint and one ``webhook.deliver`` job, so a committed change always has its notification queued and a
rolled-back one never does. The worker (:func:`handle_webhook_deliver`) POSTs the JSON body, signed with the
endpoint's secret, and records every attempt on the delivery row; a failed attempt is retried by the job queue with
a long backoff (30 s up to 12 h) until ``webhook_max_attempts``. Delivery is at-least-once: receivers deduplicate on
the ``X-InvoiceFlow-Delivery`` header.

Signature: ``X-InvoiceFlow-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<raw body>">``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ssrf
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models import Invoice, Job, Supplier, WebhookDelivery, WebhookEndpoint
from app.services import audit, jobs

log = get_logger("webhooks")

EVENT_TYPES = ("invoice.approved", "payment.approved", "exception.opened")
TEST_EVENT = "webhook.test"
MAX_ENDPOINTS = 20
SECRET_PREFIX = "whsec_"
SIGNATURE_HEADER = "X-InvoiceFlow-Signature"
TOLERANCE_SECONDS = 300
MAX_LOGGED_ATTEMPTS = 10
RESPONSE_SNIPPET_BYTES = 1024

#: seams for tests: how host names are resolved and how requests are sent (None = the real network)
resolver: ssrf.Resolver | None = None
transport: httpx.BaseTransport | None = None


# ------------------------------------------------------------------ secrets

@lru_cache(maxsize=4)
def _fernet(jwt_fingerprint: str) -> Fernet:  # noqa: ARG001 - the cache key changes when the secret does
    secret = get_settings().jwt_secret.get_secret_value().encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"invoiceflow-webhooks", info=b"webhook-signing-secret").derive(secret)
    return Fernet(base64.urlsafe_b64encode(key))


def _cipher() -> Fernet:
    return _fernet(hashlib.sha256(get_settings().jwt_secret.get_secret_value().encode()).hexdigest())


def new_secret() -> str:
    return SECRET_PREFIX + secrets.token_urlsafe(32)


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# ------------------------------------------------------------------ signing

def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify_signature(secret: str, header: str, body: bytes, *, now: float | None = None,
                     tolerance: int = TOLERANCE_SECONDS) -> bool:
    """What a receiver does: recompute the MAC over the raw body, compare in constant time, reject stale timestamps."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs((now if now is not None else time.time()) - timestamp) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, body, timestamp), header.replace(" ", ""))


# ------------------------------------------------------------------ registration

def validate_url(url: str) -> str:
    """Raise ``ssrf.UnsafeTarget`` unless ``url`` is an HTTPS URL on public addresses; returns it normalised."""
    ssrf.resolve_public(url.strip(), resolver)
    return url.strip()


def normalise_events(events: list[str]) -> list[str]:
    unknown = sorted(set(events) - set(EVENT_TYPES))
    if unknown:
        raise ValueError(f"Unknown event type: {', '.join(unknown)}")
    chosen = [e for e in EVENT_TYPES if e in set(events)]
    if not chosen:
        raise ValueError("Choose at least one event type")
    return chosen


def serialize_endpoint(e: WebhookEndpoint) -> dict:
    return {"id": str(e.id), "url": e.url, "description": e.description, "events": list(e.events or []), "active": e.active,
            "secret_hint": e.secret_hint, "created_at": e.created_at.isoformat()}


def serialize_delivery(d: WebhookDelivery) -> dict:
    return {"id": str(d.id), "event_type": d.event_type, "is_test": d.is_test, "status": d.status, "attempts": d.attempts,
            "last_status_code": d.last_status_code, "last_error": d.last_error,
            "created_at": d.created_at.isoformat(),
            "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
            "next_attempt_at": d.next_attempt_at.isoformat() if d.next_attempt_at else None,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "attempt_log": d.attempt_log or []}


# ------------------------------------------------------------------ emitting events

def _envelope(event_type: str, org_id: uuid.UUID, data: dict) -> dict:
    return {"id": str(uuid.uuid4()), "type": event_type, "created_at": datetime.now(UTC).isoformat(),
            "organization_id": str(org_id), "data": audit.to_jsonable(data)}


def _queue(db: Session, endpoint: WebhookEndpoint, event: dict, *, is_test: bool = False) -> WebhookDelivery:
    delivery = WebhookDelivery(organization_id=endpoint.organization_id, endpoint_id=endpoint.id, event_type=event["type"],
                               payload=event, is_test=is_test, status="pending", attempts=0, attempt_log=[])
    db.add(delivery)
    db.flush()
    jobs.enqueue(db, org_id=endpoint.organization_id, job_type="webhook.deliver", payload={"delivery_id": str(delivery.id)},
                 idempotency_key=f"webhook.deliver:{delivery.id}", entity_id=delivery.id,
                 max_attempts=get_settings().webhook_max_attempts)
    return delivery


def emit(db: Session, org_id: uuid.UUID, event_type: str, data: dict) -> list[WebhookDelivery]:
    """Queue ``event_type`` for every active endpoint subscribed to it. Call inside the transaction of the change."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown webhook event {event_type}")
    endpoints = db.scalars(select(WebhookEndpoint).where(
        WebhookEndpoint.organization_id == org_id, WebhookEndpoint.active.is_(True),
        WebhookEndpoint.events.contains([event_type])).order_by(WebhookEndpoint.created_at)).all()
    if not endpoints:
        return []
    event = _envelope(event_type, org_id, data)
    # every endpoint receives the same event id, each in its own delivery
    return [_queue(db, e, event) for e in endpoints]


def queue_test(db: Session, endpoint: WebhookEndpoint) -> WebhookDelivery:
    event = _envelope(TEST_EVENT, endpoint.organization_id,
                      {"message": "This is a test delivery from InvoiceFlow.", "endpoint_id": str(endpoint.id)})
    return _queue(db, endpoint, event, is_test=True)


def invoice_data(db: Session, inv: Invoice) -> dict:
    supplier = db.get(Supplier, inv.supplier_id) if inv.supplier_id else None
    return {"invoice_id": str(inv.id), "invoice_number": inv.invoice_number, "status": inv.status,
            "supplier_id": str(inv.supplier_id) if inv.supplier_id else None,
            "supplier_name": supplier.name if supplier else inv.supplier_name_raw,
            "total": f"{inv.total:.2f}" if inv.total is not None else None, "currency": inv.currency}


# ------------------------------------------------------------------ sending

@dataclass
class SendResult:
    ok: bool
    status_code: int | None
    error: str | None
    duration_ms: int
    snippet: str | None = None


def _error_label(exc: Exception) -> str:
    if isinstance(exc, ssrf.UnsafeTarget):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return "The receiver did not answer in time"
    if isinstance(exc, httpx.ConnectError):
        return "Could not connect to the receiver (or its TLS certificate was refused)"
    if isinstance(exc, httpx.TransportError):
        return "The connection to the receiver failed"
    return "Unexpected error while sending"


def _host_literal(address: str) -> str:
    return f"[{address}]" if ":" in address else address


def send(url: str, body: bytes, headers: dict[str, str]) -> SendResult:
    """POST ``body`` to ``url``. The name is resolved now, every address must be public, and the connection goes to
    a checked address with the real host name kept for the TLS handshake and the Host header. No redirects."""
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    try:
        host, path, port, addresses = ssrf.resolve_public(url, resolver)
    except ssrf.UnsafeTarget as exc:
        return SendResult(False, None, str(exc), elapsed())
    host_header = host if port == 443 else f"{host}:{port}"
    last: Exception | None = None
    for address in addresses:
        target = f"https://{_host_literal(address)}:{port}{path}"
        try:
            with httpx.Client(transport=transport, timeout=get_settings().webhook_timeout_seconds,
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", target, content=body, headers={**headers, "Host": host_header},
                                   extensions={"sni_hostname": host}) as response:
                    snippet = b""
                    for chunk in response.iter_bytes():
                        snippet += chunk
                        if len(snippet) >= RESPONSE_SNIPPET_BYTES:
                            break
                    code = response.status_code
        except httpx.ConnectError as exc:  # try the next address of the name
            last = exc
            continue
        except Exception as exc:  # noqa: BLE001
            return SendResult(False, None, _error_label(exc), elapsed())
        text = snippet[:RESPONSE_SNIPPET_BYTES].decode("utf-8", "replace")
        if 200 <= code < 300:
            return SendResult(True, code, None, elapsed(), text)
        error = "The receiver answered with a redirect, which is not followed" if 300 <= code < 400 \
            else f"The receiver answered with HTTP {code}"
        return SendResult(False, code, error, elapsed(), text)
    return SendResult(False, None, _error_label(last) if last else "No address to connect to", elapsed())


# ------------------------------------------------------------------ the worker job

def _record_attempt(delivery: WebhookDelivery, result: SendResult, attempt: int, *, retry_at: datetime | None,
                    final: bool) -> None:
    now = datetime.now(UTC)
    delivery.attempts = attempt
    delivery.last_attempt_at = now
    delivery.last_status_code = result.status_code
    delivery.last_error = result.error[:500] if result.error else None
    delivery.attempt_log = [*(delivery.attempt_log or []),
                            {"attempt": attempt, "at": now.isoformat(), "status_code": result.status_code,
                             "error": result.error, "duration_ms": result.duration_ms}][-MAX_LOGGED_ATTEMPTS:]
    if result.ok:
        delivery.status, delivery.delivered_at, delivery.next_attempt_at = "succeeded", now, None
    elif final:
        delivery.status, delivery.next_attempt_at = "failed", None
    else:
        delivery.status, delivery.next_attempt_at = "retrying", retry_at


def _persist_failure(org_id: uuid.UUID, delivery_id: uuid.UUID, result: SendResult, attempt: int, *,
                     retry_at: datetime | None, final: bool) -> None:
    """Written in its own transaction, because the job's own one is rolled back when the job fails."""
    with session_scope(org_id) as s:
        delivery = s.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return
        _record_attempt(delivery, result, attempt, retry_at=retry_at, final=final)
        if final:
            audit.record(s, org_id=org_id, action="webhook.delivery_failed", entity_type="webhook_endpoint",
                         entity_id=delivery.endpoint_id, actor_type="system", actor_label="webhook-worker",
                         meta={"delivery_id": str(delivery.id), "event_type": delivery.event_type, "attempts": attempt,
                               "error": result.error, "status_code": result.status_code})


def _fail_permanently(org_id: uuid.UUID, delivery_id: uuid.UUID, message: str, attempt: int) -> None:
    _persist_failure(org_id, delivery_id, SendResult(False, None, message, 0), attempt, retry_at=None, final=True)


def handle_webhook_deliver(session: Session, job: Job) -> dict:
    from app.services.processing import PermanentJobError

    delivery = session.get(WebhookDelivery, uuid.UUID(job.payload["delivery_id"]))
    if delivery is None:
        raise PermanentJobError("delivery no longer exists")
    endpoint = session.get(WebhookEndpoint, delivery.endpoint_id)
    if endpoint is None or (not endpoint.active and not delivery.is_test):
        _fail_permanently(job.organization_id, delivery.id, "The endpoint was removed or switched off", job.attempts)
        raise PermanentJobError("endpoint unavailable")
    secret = decrypt_secret(endpoint.secret_enc)
    if secret is None:
        _fail_permanently(job.organization_id, delivery.id, "The signing secret cannot be read", job.attempts)
        raise PermanentJobError("signing secret unreadable")

    body = json.dumps(delivery.payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "InvoiceFlow-Webhooks/1",
               "X-InvoiceFlow-Event": delivery.event_type, "X-InvoiceFlow-Delivery": str(delivery.id),
               "X-InvoiceFlow-Event-Id": delivery.payload.get("id", ""),
               SIGNATURE_HEADER: sign(secret, body, int(time.time()))}
    result = send(endpoint.url, body, headers)
    attempt = job.attempts
    if result.ok:
        _record_attempt(delivery, result, attempt, retry_at=None, final=False)
        return {"status_code": result.status_code}
    final = attempt >= job.max_attempts
    retry_at = datetime.now(UTC) + timedelta(seconds=jobs.retry_delay(job.type, attempt))
    _persist_failure(job.organization_id, delivery.id, result, attempt, retry_at=retry_at, final=final)
    log.warning("webhook_delivery_failed", delivery_id=str(delivery.id), attempt=attempt, error=result.error)
    raise RuntimeError(result.error or "delivery failed")
