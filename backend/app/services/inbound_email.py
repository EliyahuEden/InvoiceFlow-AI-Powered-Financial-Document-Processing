"""Inbound email: invoices forwarded to an organization's own address become invoices in that organization.

An organization's forwarding address is the configured template (``INBOUND_ADDRESS_TEMPLATE``, e.g.
``invoices+{token}@inbox.example.com``) with its secret ``organizations.inbox_token`` filled in. Mail arrives two ways:
the worker polls an IMAP mailbox (``poll_mailbox``), or a mail provider posts the raw message to the signed webhook
(``api/routes/inbound.py``). Both call :func:`ingest`, which

1. parses the message (nothing in it is trusted: headers, names and attachments are all attacker-controlled),
2. maps the recipient addresses to organizations by token; an address that matches no organization is logged and
   dropped, and creates no data anywhere,
3. in a session bound to that organization (so row-level security applies), claims the message id (the dedupe), and
4. sends every PDF or image attachment through ``create_invoice_upload``, the same validation, storage, job and audit
   path a manual upload takes. An attachment that fails validation is recorded as rejected; it never fails the message.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import imaplib
import re
import ssl
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.db import engine, lock_workspace, new_session, session_scope
from app.core.logging import get_logger
from app.models import InboundEmail, Organization
from app.services import audit
from app.services.documents.validation import UploadRejected, validate_upload
from app.services.processing import DuplicateUpload, create_invoice_upload
from app.services.ratelimit import check_rate_limit
from app.services.sandbox import is_sandbox

log = get_logger("inbound_email")

#: headers that can carry the address a message was delivered to (the To header alone misses forwards and Bcc)
RECIPIENT_HEADERS = ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To", "X-Envelope-To", "X-Forwarded-To",
                     "Resent-To")
MAX_RECIPIENTS = 50
MAX_PARTS = 200  # MIME parts looked at in one message (a nesting or "zip bomb" style message stops here)
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/pjpeg": ".jpg"}
FILE_TYPES = {"application/pdf": ".pdf", **IMAGE_TYPES}
EXTENSION_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")


class InboundDeferred(Exception):
    """Not now: the organization is over its hourly limit. The message is neither recorded nor lost: IMAP leaves it
    unread for the next poll and the webhook answers 429 so the sender retries."""


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class ParsedEmail:
    message_id: str
    sender: str
    subject: str
    recipients: list[str]
    sent_at: datetime | None
    attachments: list[Attachment] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # attachments never attempted: {"filename", "reason"}


@dataclass
class IngestResult:
    status: str  # accepted | partial | rejected | duplicate | ignored
    reason: str | None = None
    accepted: int = 0
    rejected: int = 0
    organizations: int = 0


def clean(value: object, limit: int) -> str:
    """Single-line, printable text: headers and file names are attacker-controlled and end up in logs and screens."""
    return _CONTROL.sub(" ", str(value or "")).strip()[:limit]


# ----------------------------------------------------------------------------------------------- addresses
def address_pattern(template: str) -> re.Pattern[str] | None:
    if "{token}" not in template or "@" not in template:
        return None
    local, domain = template.rsplit("@", 1)
    prefix, suffix = local.split("{token}", 1)
    return re.compile(rf"^{re.escape(prefix)}([0-9a-f]{{20}}){re.escape(suffix)}@{re.escape(domain)}$", re.IGNORECASE)


def address_for(token: str) -> str | None:
    """The forwarding address for an organization token, or None while inbound email is not configured."""
    template = get_settings().inbound_address_template
    return template.replace("{token}", token) if template else None


def tokens_in(recipients: list[str]) -> dict[str, str]:
    """{token: the address it was found in} for every recipient that has the shape of a forwarding address."""
    pattern = address_pattern(get_settings().inbound_address_template)
    found: dict[str, str] = {}
    if pattern is None:
        return found
    for address in recipients:
        match = pattern.match(address.strip())
        if match:
            found.setdefault(match.group(1).lower(), address.strip().lower())
    return found


# ----------------------------------------------------------------------------------------------- parsing
def _addresses(msg: EmailMessage, extra: list[str]) -> list[str]:
    values: list[str] = list(extra)
    for header in RECIPIENT_HEADERS:
        try:
            values.extend(str(v) for v in msg.get_all(header, []))
        except Exception:  # noqa: BLE001 - a header the parser cannot decode is simply not an address
            continue
    out: list[str] = []
    for _, address in email.utils.getaddresses(values):
        address = clean(address, 320).lower()
        if address and address not in out:
            out.append(address)
        if len(out) >= MAX_RECIPIENTS:
            break
    return out


def parse_message(raw: bytes, extra_recipients: list[str] | None = None) -> ParsedEmail:
    """Read a raw RFC 5322 message. Raises ValueError when it cannot be read at all."""
    s = get_settings()
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("The message could not be parsed.") from exc

    def header(name: str, limit: int) -> str:
        try:
            return clean(msg.get(name, ""), limit)
        except Exception:  # noqa: BLE001 - e.g. an undecodable encoded word
            return ""

    message_id = header("Message-ID", 1000)
    if not message_id or len(message_id) > 300:  # none, or too long to store: identify it by its content instead
        message_id = "sha256:" + hashlib.sha256(raw).hexdigest()
    sender = clean(email.utils.parseaddr(header("From", 500))[1], 320).lower()
    sent_at = None
    try:
        sent_at = email.utils.parsedate_to_datetime(header("Date", 100))
        sent_at = sent_at.astimezone(UTC) if sent_at.tzinfo else sent_at.replace(tzinfo=UTC)
    except Exception:  # noqa: BLE001
        sent_at = None
    parsed = ParsedEmail(message_id=message_id, sender=sender, subject=header("Subject", 500),
                         recipients=_addresses(msg, extra_recipients or []), sent_at=sent_at)

    try:
        for index, part in enumerate(msg.walk()):
            if index >= MAX_PARTS:
                parsed.skipped.append({"filename": "", "reason": "Too many parts in the message."})
                break
            if part.is_multipart():
                continue
            try:
                ctype = part.get_content_type()
                name = clean(part.get_filename() or "", 200)
                disposition = part.get_content_disposition()
            except Exception:  # noqa: BLE001
                continue
            if not name and disposition != "attachment" and ctype not in FILE_TYPES:
                continue  # the message text itself
            ext = EXTENSION_TYPES.get(("." + name.rsplit(".", 1)[-1].lower()) if "." in name else "")
            if ctype in ("application/octet-stream", "binary/octet-stream") and ext:
                ctype = ext  # some mail programs send every file as octet-stream
            if ctype not in FILE_TYPES:
                if name or disposition == "attachment":
                    parsed.skipped.append({"filename": name, "reason": f"Only PDF and image attachments are read (this was {clean(ctype, 60)})."})
                continue
            try:
                data = part.get_payload(decode=True)
            except Exception:  # noqa: BLE001
                data = None
            if not data:
                parsed.skipped.append({"filename": name, "reason": "The attachment is empty or could not be decoded."})
                continue
            # a signature logo or tracking pixel is an inline image, not an invoice
            if ctype in IMAGE_TYPES and (disposition == "inline" or part.get("Content-ID")) \
                    and len(data) < s.inbound_min_inline_image_bytes:
                continue
            if len(parsed.attachments) >= s.inbound_max_attachments:
                parsed.skipped.append({"filename": name, "reason": f"Only the first {s.inbound_max_attachments} files of a message are read."})
                continue
            parsed.attachments.append(Attachment(filename=name or f"attachment{FILE_TYPES[ctype]}", content_type=ctype, data=data))
    except RecursionError:  # parts nested thousands deep: keep what was read, drop the rest
        parsed.skipped.append({"filename": "", "reason": "The message is nested too deeply."})
    return parsed


# ----------------------------------------------------------------------------------------------- ingestion
def _organizations_for(tokens: dict[str, str]) -> list[tuple[uuid.UUID, str, dict]]:
    """(organization id, the address used, settings) for every token that belongs to an organization."""
    if not tokens:
        return []
    db = new_session()  # no tenant: the token lookup is the one query that has to run before a tenant is known
    try:
        rows = db.execute(select(Organization.id, Organization.inbox_token, Organization.settings)
                          .where(Organization.inbox_token.in_(list(tokens)))).all()
    finally:
        db.close()
    return [(org_id, tokens[token], settings) for org_id, token, settings in rows]


def ingest(raw: bytes, source: str, extra_recipients: list[str] | None = None) -> IngestResult:
    """Process one raw message. Never raises for a message that is merely bad; raises InboundDeferred when the
    organization is over its hourly limit, and lets infrastructure errors (database, storage) propagate so the caller
    retries the whole message."""
    s = get_settings()
    if not s.inbound_address_template:
        return IngestResult("ignored", "inbound_email_off")
    if len(raw) > s.inbound_max_message_bytes:
        log.warning("inbound_email_rejected", reason="message_too_large", size=len(raw), source=source)
        return IngestResult("rejected", "message_too_large")
    try:
        parsed = parse_message(raw, extra_recipients)
    except ValueError:
        log.warning("inbound_email_rejected", reason="unparseable", source=source)
        return IngestResult("rejected", "unparseable")

    targets = _organizations_for(tokens_in(parsed.recipients))
    if not targets:
        log.warning("inbound_email_rejected", reason="unknown_recipient", source=source, sender=parsed.sender[:120],
                    recipients=[clean(r, 120) for r in parsed.recipients[:5]], message_id=clean(parsed.message_id, 120))
        return IngestResult("rejected", "unknown_recipient")

    results = [_ingest_for_organization(org_id, address, settings, parsed, source) for org_id, address, settings in targets]
    if all(r.status == "duplicate" for r in results):
        return IngestResult("duplicate", organizations=len(results))
    accepted, rejected = sum(r.accepted for r in results), sum(r.rejected for r in results)
    status = "rejected" if accepted == 0 else "partial" if rejected else "accepted"
    return IngestResult(status, accepted=accepted, rejected=rejected, organizations=len(results))


def _ingest_for_organization(org_id: uuid.UUID, address: str, settings: dict, parsed: ParsedEmail, source: str) -> IngestResult:
    ctx = {"org_id": str(org_id), "source": source, "message_id": clean(parsed.message_id, 120)}
    if is_sandbox(settings):
        log.warning("inbound_email_rejected", reason="demo_workspace", **ctx)
        return IngestResult("rejected", "demo_workspace")
    limit = get_settings().rate_limit_inbound_per_hour
    if limit:
        try:
            check_rate_limit(f"inbound:{org_id}", limit, window_seconds=3600)
        except HTTPException as exc:
            log.warning("inbound_email_deferred", reason="rate_limited", **ctx)
            raise InboundDeferred(str(org_id)) from exc

    with session_scope(org_id) as db:
        lock_workspace(db, org_id)
        if db.get(Organization, org_id) is None:  # erased since the lookup
            return IngestResult("rejected", "unknown_recipient")
        claim = insert(InboundEmail).values(
            id=uuid.uuid4(), organization_id=org_id, message_id=parsed.message_id, source=source, sender=parsed.sender,
            subject=parsed.subject, recipient=address[:320], received_at=parsed.sent_at, status="rejected",
            attachments_total=len(parsed.attachments) + len(parsed.skipped), attachments_accepted=0, details=[],
        ).on_conflict_do_nothing(constraint="uq_inbound_emails_org_message").returning(InboundEmail.id)
        email_id = db.scalar(claim)
        if email_id is None:  # the same message again: polled twice, redelivered by the provider, posted twice
            log.info("inbound_email_duplicate", **ctx)
            return IngestResult("duplicate")

        details: list[dict] = [{"filename": k["filename"], "status": "skipped", "reason": k["reason"]} for k in parsed.skipped]
        accepted = 0
        for att in parsed.attachments:
            entry = {"filename": clean(att.filename, 200), "status": "rejected", "reason": None, "invoice_id": None}
            try:
                # Validate first, here, so a file that crashes the validator is that file's rejection rather than a
                # retry loop for the whole message. create_invoice_upload validates again: it is the manual path.
                validate_upload(att.data, att.filename)
            except UploadRejected as exc:
                entry["reason"] = str(exc)
            except Exception as exc:  # noqa: BLE001 - hostile files must never take the worker down
                log.warning("inbound_attachment_unreadable", error=type(exc).__name__, **ctx)
                entry["reason"] = "The file could not be read."
            else:
                try:
                    with db.begin_nested():
                        inv, _job = create_invoice_upload(
                            db, org_id=org_id, user=None, data=att.data, filename=att.filename, source="email",
                            inbound_email_id=email_id, actor_label=parsed.sender or "email",
                            audit_meta={"inbound_email_id": str(email_id), "sender": parsed.sender,
                                        "subject": parsed.subject, "message_id": parsed.message_id})
                    entry.update(status="accepted", invoice_id=str(inv.id))
                    accepted += 1
                except DuplicateUpload as dup:
                    entry.update(status="duplicate", reason="This exact file was already uploaded.",
                                 invoice_id=str(dup.invoice_id) if dup.invoice_id else None)
                except UploadRejected as exc:
                    entry["reason"] = str(exc)
            details.append(entry)
            if entry["status"] == "rejected":
                log.warning("inbound_attachment_rejected", reason=clean(entry["reason"], 200), **ctx)

        rejected = sum(1 for d in details if d["status"] == "rejected")
        status = "accepted" if accepted and not rejected else "partial" if accepted else "rejected"
        row = db.get(InboundEmail, email_id)
        row.status, row.attachments_accepted, row.details = status, accepted, details
        audit.record(db, org_id=org_id, action="inbox.email_received" if accepted else "inbox.email_rejected",
                     entity_type="inbound_email", entity_id=email_id, actor_type="system", actor_label=parsed.sender or "email",
                     after={"status": status, "attachments": len(parsed.attachments) + len(parsed.skipped), "accepted": accepted},
                     meta={"sender": parsed.sender, "subject": parsed.subject, "message_id": parsed.message_id,
                           "source": source, "recipient": address})
    log.info("inbound_email_processed", status=status, accepted=accepted, rejected=rejected, **ctx)
    return IngestResult(status, accepted=accepted, rejected=rejected)


def regenerate_token(db, org: Organization) -> str:  # noqa: ANN001 - a tenant-bound Session
    """Replace the organization's secret. The old address stops working at once: mail to it is an unknown recipient."""
    from app.models.tenancy import new_inbox_token

    org.inbox_token = new_inbox_token()
    db.flush()
    return org.inbox_token


# ----------------------------------------------------------------------------------------------- IMAP polling
def _imap_connect() -> imaplib.IMAP4:
    s = get_settings()
    context = ssl.create_default_context()
    port = s.inbound_imap_port or (993 if s.inbound_imap_security == "ssl" else 143)
    if s.inbound_imap_security == "ssl":
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(s.inbound_imap_host, port, ssl_context=context, timeout=30)
    else:
        client = imaplib.IMAP4(s.inbound_imap_host, port, timeout=30)
        if s.inbound_imap_security == "starttls":
            client.starttls(ssl_context=context)
    client.login(s.inbound_imap_username, s.inbound_imap_password.get_secret_value())
    return client


def _poll_lock_key() -> int:
    return int.from_bytes(hashlib.sha256(b"invoiceflow:inbound-email-poll").digest()[:8], "big", signed=True)


def poll_mailbox(connect=None) -> dict:  # noqa: ANN001 - a callable returning an imaplib-like client (tests pass a fake)
    """Read up to ``INBOUND_IMAP_BATCH`` unread messages, process each, and mark it read.

    Only one worker polls at a time (a PostgreSQL advisory lock), so replicas do not read the same message twice.
    A message is marked read once it has an outcome, including rejection; one that could not be processed because
    of a database or storage error, or that is deferred by the hourly limit, stays unread and is retried."""
    s = get_settings()
    if not (s.inbound_imap_enabled and s.inbound_address_template):
        return {"skipped": True}
    stats = {"read": 0, "accepted": 0, "rejected": 0, "duplicate": 0, "deferred": 0, "failed": 0}
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _poll_lock_key()}).scalar():
            lock_conn.rollback()
            return {"skipped": True, "reason": "another worker is polling"}
        try:
            lock_conn.rollback()
            client = (connect or _imap_connect)()
            try:
                typ, _ = client.select(s.inbound_imap_folder)
                if typ != "OK":
                    raise RuntimeError("The mailbox folder could not be opened.")
                typ, found = client.uid("SEARCH", None, "UNSEEN")
                uids = (found[0] or b"").split()[: s.inbound_imap_batch] if typ == "OK" else []
                for uid in uids:
                    stats["read"] += 1
                    try:
                        outcome = _process_uid(client, uid)
                    except InboundDeferred:
                        stats["deferred"] += 1
                        continue
                    except Exception as exc:  # noqa: BLE001 - leave it unread; the next poll tries again
                        log.error("inbound_email_failed", error=f"{type(exc).__name__}: {exc}"[:300], source="imap")
                        stats["failed"] += 1
                        continue
                    client.uid("STORE", uid, "+FLAGS", "(\\Seen)")
                    key = "accepted" if outcome.status in ("accepted", "partial") else \
                        "duplicate" if outcome.status == "duplicate" else "rejected"
                    stats[key] += 1
            finally:
                try:
                    client.logout()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _poll_lock_key()})
            lock_conn.rollback()
    if stats["read"]:
        log.info("inbound_mailbox_polled", **stats)
    return stats


def _process_uid(client, uid: bytes) -> IngestResult:  # noqa: ANN001
    s = get_settings()
    typ, meta = client.uid("FETCH", uid, "(RFC822.SIZE)")
    size = 0
    if typ == "OK" and meta and meta[0]:
        head = meta[0][0] if isinstance(meta[0], tuple) else meta[0]
        found = re.search(rb"RFC822\.SIZE (\d+)", head)
        size = int(found.group(1)) if found else 0
    if size > s.inbound_max_message_bytes:  # never download it
        log.warning("inbound_email_rejected", reason="message_too_large", size=size, source="imap")
        return IngestResult("rejected", "message_too_large")
    typ, data = client.uid("FETCH", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        raise RuntimeError("The message could not be fetched.")
    return ingest(bytes(data[0][1]), "imap")
