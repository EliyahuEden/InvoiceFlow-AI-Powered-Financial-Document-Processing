"""Inbound email: the signed webhook a mail provider posts to, and the organization's forwarding-address settings."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.core.client_ip import client_ip
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import InboundEmail, Organization
from app.services import audit, inbound_email
from app.services.ratelimit import check_rate_limit
from app.services.rbac import Perm

router = APIRouter(tags=["inbound"])
log = get_logger("inbound_email")


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The signature a sender computes: HMAC-SHA256 over "<timestamp>." followed by the raw body."""
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


async def _read_capped(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdecimal() and int(declared) > limit:
        raise HTTPException(413, "The message is too large.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, "The message is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/api/inbound/email", status_code=202)
async def receive_email(request: Request) -> JSONResponse:
    """The raw RFC 822 message as the request body, signed with INBOUND_WEBHOOK_SECRET:

    ``X-InvoiceFlow-Timestamp``: unix seconds; ``X-InvoiceFlow-Signature``: ``sha256=<hex HMAC-SHA256 of
    "<timestamp>." + body>``; optional ``X-InvoiceFlow-Recipient``: the envelope recipient(s), comma-separated,
    for mail where the address is not in the message's own headers (Bcc, forwards)."""
    s = get_settings()
    if not (s.inbound_webhook_enabled and s.inbound_address_template):
        raise HTTPException(404, "Not found")
    check_rate_limit(f"inbound-webhook:{client_ip(request)}", 120)  # before reading the body: unsigned posts cost nothing
    timestamp = request.headers.get("x-invoiceflow-timestamp", "")
    signature = request.headers.get("x-invoiceflow-signature", "")
    if not timestamp.isdecimal() or len(timestamp) > 12 or abs(time.time() - int(timestamp)) > s.inbound_webhook_tolerance_seconds:
        raise HTTPException(401, "Invalid signature")
    body = await _read_capped(request, s.inbound_max_message_bytes)
    expected = sign(s.inbound_webhook_secret.get_secret_value(), timestamp, body)
    if not hmac.compare_digest(expected, signature):
        log.warning("inbound_webhook_bad_signature", ip=client_ip(request))
        raise HTTPException(401, "Invalid signature")
    extra = [a.strip() for a in request.headers.get("x-invoiceflow-recipient", "")[:2000].split(",") if a.strip()]
    try:
        result = await run_in_threadpool(inbound_email.ingest, body, "webhook", extra)
    except inbound_email.InboundDeferred:
        raise HTTPException(429, "Too many messages for this organization, retry later.", headers={"Retry-After": "600"}) from None
    # The sender is trusted by its signature, but the answer still names no organization.
    return JSONResponse({"status": result.status, "reason": result.reason, "accepted": result.accepted,
                         "rejected": result.rejected}, status_code=202)


# ------------------------------------------------------------------------- settings: the forwarding address
def _view(db: Session, org: Organization) -> dict:
    s = get_settings()
    recent = db.scalars(select(InboundEmail).where(InboundEmail.organization_id == org.id)
                        .order_by(InboundEmail.created_at.desc()).limit(20)).all()
    return {
        "enabled": s.inbound_enabled,
        "address": inbound_email.address_for(org.inbox_token) if s.inbound_enabled else None,
        "methods": {"imap": s.inbound_imap_enabled, "webhook": s.inbound_webhook_enabled},
        "max_attachment_mb": s.max_upload_bytes // (1024 * 1024),
        "recent": [{"id": str(m.id), "created_at": m.created_at.isoformat(), "sender": m.sender, "subject": m.subject,
                    "status": m.status, "source": m.source, "attachments": m.attachments_total,
                    "accepted": m.attachments_accepted,
                    "problems": [{"filename": d.get("filename"), "status": d.get("status"), "reason": d.get("reason")}
                                 for d in m.details if d.get("status") in ("rejected", "skipped", "duplicate")]} for m in recent],
    }


@router.get("/api/org/inbox")
def get_inbox(p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    return _view(db, db.get(Organization, p.org_id))


@router.post("/api/org/inbox/regenerate")
def regenerate_inbox(p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    if not get_settings().inbound_enabled:
        raise HTTPException(409, "Inbound email is not configured on this installation.")
    check_rate_limit(f"inbox-regenerate:{p.user.id}", 10, window_seconds=3600)
    org = db.get(Organization, p.org_id)
    inbound_email.regenerate_token(db, org)
    # the audit entry names no address: the address is a secret
    audit.record(db, org_id=org.id, action="org.inbox_address_regenerated", entity_type="organization", entity_id=org.id,
                 actor_id=p.user.id, actor_label=p.user.email)
    return _view(db, org)
