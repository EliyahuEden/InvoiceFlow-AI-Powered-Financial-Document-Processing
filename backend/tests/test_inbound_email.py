"""Inbound email: invoices forwarded to an organization's own address become that organization's invoices.

Covers the tenant mapping (an address belongs to exactly one organization, unknown ones create nothing anywhere), the
message-id dedupe, hostile attachments (the same cases as test_fuzz_uploads), the signed webhook, the IMAP poller,
row-level security of the new table, and the settings endpoints."""
from __future__ import annotations

import time
import uuid
from email.message import EmailMessage

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings, get_settings
from app.core.db import new_session, session_scope
from app.models import AuditLog, Document, InboundEmail, Invoice, Organization
from app.services import inbound_email
from app.services.inbound_email import InboundDeferred, ingest, parse_message, poll_mailbox
from tests.conftest import DATA
from tests.test_fuzz_uploads import CASES, _pdf

pytestmark = pytest.mark.integration
TEMPLATE = "invoices+{token}@inbox.example.test"
SECRET = "inbound-webhook-secret-0123456789abcdef"
CSRF = {"X-Requested-With": "invoiceflow"}
GOOD_PDF = (DATA / "invoices" / "03_price_mismatch_bluewave_en.pdf").read_bytes()


@pytest.fixture(autouse=True)
def inbound_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "inbound_address_template", TEMPLATE)
    monkeypatch.setattr(s, "inbound_webhook_secret", SecretStr(SECRET))
    monkeypatch.setattr(s, "inbound_imap_host", "imap.example.test")
    monkeypatch.setattr(s, "inbound_imap_username", "inbox@example.test")
    monkeypatch.setattr(s, "inbound_imap_password", SecretStr("mailbox-password"))


def token_of(org_id) -> str:  # noqa: ANN001
    with session_scope() as s:
        return s.get(Organization, org_id).inbox_token


def address_of(org_id) -> str:  # noqa: ANN001
    return TEMPLATE.replace("{token}", token_of(org_id))


def make_mail(to: str | list[str], attachments: list[tuple[str, bytes, str]] | None = None, *, message_id: str | None = "<m1@mail.test>",
              subject: str = "Invoice for October", sender: str = "Dana <billing@supplier.example>", headers: dict | None = None) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join([to] if isinstance(to, str) else to)
    msg["Subject"] = subject
    if message_id:
        msg["Message-ID"] = message_id
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content("Please find the invoice attached.")
    for name, data, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


def counts(org_id) -> dict:  # noqa: ANN001
    with session_scope(org_id) as s:
        return {"invoices": s.scalar(select(func.count()).select_from(Invoice)),
                "documents": s.scalar(select(func.count()).select_from(Document)),
                "emails": s.scalar(select(func.count()).select_from(InboundEmail))}


# ------------------------------------------------------------------------------------------ tenant mapping
def test_a_message_becomes_an_invoice_in_the_addressed_organization_only(world):
    left, right = world["org_id"], world["other_org_id"]
    before_right = counts(right)
    before_left = counts(left)
    r = ingest(make_mail(address_of(left), [("inv-001.pdf", GOOD_PDF, "application/pdf")]), "webhook")
    assert (r.status, r.accepted, r.rejected) == ("accepted", 1, 0)
    assert counts(right) == before_right  # nothing in the other organization
    after = counts(left)
    assert after["invoices"] == before_left["invoices"] + 1 and after["emails"] == before_left["emails"] + 1

    with session_scope(left) as s:
        inv = s.scalars(select(Invoice).where(Invoice.source == "email")).one()
        mail = s.get(InboundEmail, inv.inbound_email_id)
        assert (mail.sender, mail.subject, mail.message_id) == ("billing@supplier.example", "Invoice for October", "<m1@mail.test>")
        assert (mail.status, mail.attachments_accepted, mail.source) == ("accepted", 1, "webhook")
        entry = s.scalars(select(AuditLog).where(AuditLog.entity_id == inv.id, AuditLog.action == "invoice.uploaded")).one()
        assert entry.actor_type == "system" and entry.actor_label == "billing@supplier.example"
        assert entry.meta["source"] == "email" and entry.meta["message_id"] == "<m1@mail.test>"
        assert entry.meta["subject"] == "Invoice for October"
        received = s.scalars(select(AuditLog).where(AuditLog.action == "inbox.email_received")).one()
        assert received.meta["sender"] == "billing@supplier.example"
    with session_scope(right) as s:
        assert s.scalars(select(Invoice).where(Invoice.source == "email")).all() == []
        assert s.get(Invoice, inv.id) is None


def test_the_emailed_invoice_is_processed_like_an_uploaded_one(world):
    from app.worker import drain

    ingest(make_mail(address_of(world["org_id"]), [("inv-002.pdf", GOOD_PDF, "application/pdf")]), "imap")
    drain()
    with session_scope(world["org_id"]) as s:
        inv = s.scalars(select(Invoice).where(Invoice.source == "email")).one()
        assert inv.status != "processing" and inv.extraction_method


def test_one_message_to_two_organizations_is_stored_separately_in_each(world):
    left, right = world["org_id"], world["other_org_id"]
    r = ingest(make_mail([address_of(left), address_of(right)], [("shared.pdf", GOOD_PDF, "application/pdf")]), "imap")
    assert (r.status, r.organizations, r.accepted) == ("accepted", 2, 2)
    for org in (left, right):
        with session_scope(org) as s:
            assert len(s.scalars(select(Invoice).where(Invoice.source == "email")).all()) == 1
            assert len(s.scalars(select(InboundEmail)).all()) == 1


def test_the_address_may_be_in_a_delivery_header_instead_of_to(world):
    raw = make_mail("someone-else@example.test", [("a.pdf", GOOD_PDF, "application/pdf")],
                    headers={"Delivered-To": address_of(world["org_id"])})
    assert ingest(raw, "imap").status == "accepted"


@pytest.mark.parametrize("recipient", [
    "invoices+{rand}@inbox.example.test",          # the right shape, but no organization has this token
    "invoices+{real}@other-domain.example",         # a real token on the wrong domain
    "invoices@inbox.example.test",                  # no token
    "invoices+{real_upper}x@inbox.example.test",    # a real token with something appended
    "x{real}@inbox.example.test",                   # wrong local part
    "info@inbox.example.test",
])
def test_unknown_recipients_create_nothing_anywhere(world, recipient, caplog):
    left, right = world["org_id"], world["other_org_id"]
    before = (counts(left), counts(right))
    real = token_of(left)
    to = recipient.format(rand=uuid.uuid4().hex[:20], real=real, real_upper=real.upper())
    r = ingest(make_mail(to, [("a.pdf", GOOD_PDF, "application/pdf")]), "webhook")
    assert (r.status, r.reason, r.accepted) == ("rejected", "unknown_recipient", 0)
    assert (counts(left), counts(right)) == before


def test_a_token_is_matched_case_insensitively_but_only_exactly(world):
    r = ingest(make_mail(address_of(world["org_id"]).upper(), [("a.pdf", GOOD_PDF, "application/pdf")]), "webhook")
    assert r.status == "accepted"


def test_an_unknown_recipient_is_logged_and_the_log_is_one_line(world, capsys):
    # the standard library refuses to build such headers, so write the message by hand
    raw = (b"From: a@evil.example\r\nTo: invoices+" + b"0" * 20 + b"@inbox.example.test\r\nMessage-ID: <log@x>\r\n"
           b"Subject: one" + "\u2028".encode() + b"FORGED LOG LINE" + "\u2029".encode() + b"two\r\n\r\nbody\r\n")
    assert ingest(raw, "webhook").reason == "unknown_recipient"
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if "inbound_email_rejected" in line]
    assert len(lines) == 1 and "unknown_recipient" in lines[0]
    assert not any(line.lstrip().startswith("FORGED LOG LINE") for line in out.splitlines())


def test_a_demo_workspace_does_not_accept_email(world):
    org = world["org_id"]
    with session_scope() as s:
        o = s.get(Organization, org)
        o.settings = {**o.settings, "sandbox": {"expires_at": "2099-01-01T00:00:00+00:00"}}
    before = counts(org)
    assert ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")]), "webhook").status == "rejected"
    assert counts(org) == before


def test_inbound_is_off_without_an_address_template(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_address_template", "")
    before = counts(world["org_id"])
    assert ingest(make_mail(address_of(world["org_id"]), [("a.pdf", GOOD_PDF, "application/pdf")]), "webhook").status == "ignored"
    assert counts(world["org_id"]) == before


# ------------------------------------------------------------------------------------------ dedupe
def test_the_same_message_id_is_processed_once(world):
    org = world["org_id"]
    raw = make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")])
    assert ingest(raw, "imap").status == "accepted"
    again = ingest(raw, "webhook")
    assert again.status == "duplicate" and again.accepted == 0
    # a redelivery whose content differs is still the same message
    other = make_mail(address_of(org), [("b.pdf", _pdf(["Tax Invoice 77"]), "application/pdf")])
    assert ingest(other, "webhook").status == "duplicate"
    c = counts(org)
    assert c["emails"] == 1 and c["invoices"] - counts(world["other_org_id"])["invoices"] >= 1
    with session_scope(org) as s:
        assert len(s.scalars(select(Invoice).where(Invoice.source == "email")).all()) == 1


def test_the_same_message_id_in_two_organizations_is_not_a_duplicate(world):
    for org in (world["org_id"], world["other_org_id"]):
        assert ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")]), "webhook").status == "accepted"


def test_a_message_without_an_id_is_deduplicated_by_its_content(world):
    raw = make_mail(address_of(world["org_id"]), [("a.pdf", GOOD_PDF, "application/pdf")], message_id=None)
    assert ingest(raw, "imap").status == "accepted"
    assert ingest(raw, "imap").status == "duplicate"
    with session_scope(world["org_id"]) as s:
        assert s.scalars(select(InboundEmail)).one().message_id.startswith("sha256:")


def test_the_same_file_in_a_new_message_is_reported_as_a_duplicate_file(world):
    org = world["org_id"]
    ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<one@x>"), "imap")
    r = ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<two@x>"), "imap")
    assert (r.status, r.accepted) == ("rejected", 0)
    with session_scope(org) as s:
        second = s.scalars(select(InboundEmail).where(InboundEmail.message_id == "<two@x>")).one()
        assert [d["status"] for d in second.details] == ["duplicate"]
        assert len(s.scalars(select(Invoice).where(Invoice.source == "email")).all()) == 1


# ------------------------------------------------------------------------------------------ hostile attachments
@pytest.mark.parametrize(("name", "data", "mime"), CASES, ids=[c[0][:30] for c in CASES])
def test_hostile_attachments_never_raise_and_never_hang(world, name, data, mime):
    """The cases of test_fuzz_uploads, sent by email: each is rejected with a reason, skipped, or processed to a
    final state; never an exception, never a job left running."""
    from app.worker import drain

    org = world["org_id"]
    r = ingest(make_mail(address_of(org), [(name, data, mime)], message_id=f"<{uuid.uuid4().hex}@fuzz>"), "imap")
    assert r.status in ("accepted", "rejected")
    drain()
    with session_scope(org) as s:
        mail = s.scalars(select(InboundEmail)).one()
        assert mail.status == r.status and len(mail.details) == 1
        entry = mail.details[0]
        if r.status == "rejected":
            assert entry["status"] in ("rejected", "skipped", "duplicate") and entry["reason"]
        else:
            inv = s.get(Invoice, uuid.UUID(entry["invoice_id"]))
            assert inv.status != "processing", "the job never finished"
            assert "/" not in s.get(Document, inv.document_id).filename  # path tricks never reach storage names


def test_a_bad_attachment_does_not_stop_the_good_one(world):
    org = world["org_id"]
    r = ingest(make_mail(address_of(org), [("garbage.pdf", b"\x00\xff" * 4000, "application/pdf"),
                                           ("good.pdf", GOOD_PDF, "application/pdf"),
                                           ("note.txt", b"hello", "text/plain")]), "imap")
    assert (r.status, r.accepted, r.rejected) == ("partial", 1, 1)
    with session_scope(org) as s:
        mail = s.scalars(select(InboundEmail)).one()
        assert sorted(d["status"] for d in mail.details) == ["accepted", "rejected", "skipped"]
        assert (mail.attachments_total, mail.attachments_accepted) == (3, 1)


def test_an_oversized_attachment_is_rejected(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2000)
    r = ingest(make_mail(address_of(world["org_id"]), [("big.pdf", GOOD_PDF, "application/pdf")]), "imap")
    assert (r.status, r.accepted) == ("rejected", 0)
    with session_scope(world["org_id"]) as s:
        assert "limit" in s.scalars(select(InboundEmail)).one().details[0]["reason"]


def test_a_message_over_the_size_limit_is_dropped_unread(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_max_message_bytes", 1000)
    before = counts(world["org_id"])
    r = ingest(make_mail(address_of(world["org_id"]), [("a.pdf", GOOD_PDF, "application/pdf")]), "imap")
    assert (r.status, r.reason) == ("rejected", "message_too_large") and counts(world["org_id"]) == before


def test_only_the_configured_number_of_files_is_read_from_one_message(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_max_attachments", 2)
    files = [(f"f{i}.pdf", _pdf([f"Tax Invoice {i}"]), "application/pdf") for i in range(4)]
    r = ingest(make_mail(address_of(world["org_id"]), files), "imap")
    assert r.accepted == 2
    with session_scope(world["org_id"]) as s:
        assert [d["status"] for d in s.scalars(select(InboundEmail)).one().details].count("skipped") == 2


def test_signature_logos_are_ignored_but_a_photographed_invoice_is_kept(world):
    from tests.test_fuzz_uploads import _png

    org = world["org_id"]
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Message-ID"], msg["Subject"] = "a@b.example", address_of(org), "<logo@x>", "hi"
    msg.set_content("text")
    msg.add_alternative("<p>hi <img src='cid:logo'></p>", subtype="html")
    msg.get_payload()[1].add_related(_png(8, 8), "image", "png", cid="<logo>", filename="logo.png")
    msg.add_attachment(_png(300, 300), maintype="image", subtype="png", filename="scan.png")
    parsed = parse_message(msg.as_bytes())
    assert [a.filename for a in parsed.attachments] == ["scan.png"]


def test_a_pathologically_nested_message_is_handled(world):
    depth = 4000
    raw = (b"From: a@b.example\r\nTo: " + address_of(world["org_id"]).encode() + b"\r\nMessage-ID: <deep@x>\r\n"
           + b"".join(b"Content-Type: multipart/mixed; boundary=b%d\r\n\r\n--b%d\r\n" % (i, i) for i in range(depth)))
    r = ingest(raw, "webhook")  # whatever the parser makes of it, it must not raise
    assert r.status in ("rejected", "accepted")


def test_garbage_that_is_not_an_email_is_rejected(world):
    before = counts(world["org_id"])
    r = ingest(b"\x00\x01\x02 not an email at all", "webhook")
    assert r.status == "rejected" and counts(world["org_id"]) == before


def test_headers_are_cleaned_and_bounded(world):
    org = world["org_id"]
    ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")], subject="S" * 900 + "\u202e evil",
                     sender="Attacker <attacker@evil.example>"), "imap")
    with session_scope(org) as s:
        mail = s.scalars(select(InboundEmail)).one()
        assert len(mail.subject) <= 500 and "\u202e" not in mail.subject


# ------------------------------------------------------------------------------------------ rate limit
def test_an_organization_over_its_hourly_limit_is_deferred_not_dropped(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_inbound_per_hour", 1)
    org = world["org_id"]
    assert ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<r1@x>"), "imap").status == "accepted"
    with pytest.raises(InboundDeferred):
        ingest(make_mail(address_of(org), [("b.pdf", _pdf(["Tax Invoice 5"]), "application/pdf")], message_id="<r2@x>"), "imap")
    with session_scope(org) as s:
        assert [m.message_id for m in s.scalars(select(InboundEmail))] == ["<r1@x>"]  # the deferred one left no trace


# ------------------------------------------------------------------------------------------ webhook
def signed(raw: bytes, *, secret: str = SECRET, ts: int | None = None, extra: dict | None = None) -> dict:
    from app.api.routes.inbound import sign

    stamp = str(int(time.time()) if ts is None else ts)
    return {"X-InvoiceFlow-Timestamp": stamp, "X-InvoiceFlow-Signature": sign(secret, stamp, raw),
            "Content-Type": "message/rfc822", **(extra or {})}


def test_the_webhook_takes_a_signed_message(client, world):
    org = world["org_id"]
    raw = make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")])
    r = client.post("/api/inbound/email", content=raw, headers=signed(raw))
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted", "reason": None, "accepted": 1, "rejected": 0}
    assert "organization" not in r.text
    again = client.post("/api/inbound/email", content=raw, headers=signed(raw))
    assert again.status_code == 202 and again.json()["status"] == "duplicate"
    assert counts(org)["emails"] == 1


@pytest.mark.parametrize("tamper", ["wrong_secret", "stale", "future", "bad_body", "no_headers", "garbage_ts"])
def test_the_webhook_refuses_anything_not_signed_correctly(client, world, tamper):
    org = world["org_id"]
    raw = make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")])
    headers = {"wrong_secret": lambda: signed(raw, secret="x" * 40), "stale": lambda: signed(raw, ts=int(time.time()) - 3600),
               "future": lambda: signed(raw, ts=int(time.time()) + 3600),
               "bad_body": lambda: signed(raw + b"tampered"), "no_headers": lambda: {},
               "garbage_ts": lambda: {**signed(raw), "X-InvoiceFlow-Timestamp": "12abc"}}[tamper]()
    before = counts(org)
    r = client.post("/api/inbound/email", content=raw if tamper != "bad_body" else raw, headers=headers)
    assert r.status_code == 401, r.text
    assert counts(org) == before


def test_the_webhook_does_not_exist_without_a_secret(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_webhook_secret", None)
    raw = make_mail(address_of(world["org_id"]), [("a.pdf", GOOD_PDF, "application/pdf")])
    assert client.post("/api/inbound/email", content=raw, headers=signed(raw)).status_code == 404


def test_the_webhook_accepts_the_envelope_recipient_in_a_header(client, world):
    raw = make_mail("undisclosed-recipients:;", [("a.pdf", GOOD_PDF, "application/pdf")])
    r = client.post("/api/inbound/email", content=raw,
                    headers=signed(raw, extra={"X-InvoiceFlow-Recipient": f"nobody@x.test, {address_of(world['org_id'])}"}))
    assert r.json()["status"] == "accepted"


def test_the_webhook_answers_an_unknown_recipient_without_naming_anyone(client, world):
    raw = make_mail("invoices+" + "a" * 20 + "@inbox.example.test", [("a.pdf", GOOD_PDF, "application/pdf")])
    r = client.post("/api/inbound/email", content=raw, headers=signed(raw))
    assert r.status_code == 202 and r.json()["status"] == "rejected" and r.json()["reason"] == "unknown_recipient"


def test_the_webhook_refuses_an_oversized_body_before_reading_it(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_max_message_bytes", 5000)
    raw = b"x" * 6000
    assert client.post("/api/inbound/email", content=raw, headers=signed(raw)).status_code == 413


def test_the_webhook_defers_with_429_when_the_organization_is_over_its_limit(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_inbound_per_hour", 1)
    org = address_of(world["org_id"])
    first = make_mail(org, [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<w1@x>")
    second = make_mail(org, [("b.pdf", _pdf(["Tax Invoice 8"]), "application/pdf")], message_id="<w2@x>")
    assert client.post("/api/inbound/email", content=first, headers=signed(first)).status_code == 202
    r = client.post("/api/inbound/email", content=second, headers=signed(second))
    assert r.status_code == 429 and r.headers["Retry-After"]


# ------------------------------------------------------------------------------------------ IMAP polling
class FakeImap:
    """Just enough of imaplib.IMAP4 for the poller: UNSEEN search, size and body fetches, STORE, logout."""

    def __init__(self, messages: dict[bytes, bytes]) -> None:
        self.messages, self.seen, self.fetched_bodies, self.logged_out = messages, set(), [], False

    def select(self, folder):  # noqa: ANN001, ANN201
        assert folder == "INBOX"
        return "OK", [b"1"]

    def uid(self, command, *args):  # noqa: ANN001, ANN201
        if command == "SEARCH":
            return "OK", [b" ".join(u for u in self.messages if u not in self.seen)]
        if command == "FETCH":
            uid, what = args
            if what == "(RFC822.SIZE)":
                return "OK", [b"1 (UID %s RFC822.SIZE %d)" % (uid, len(self.messages[uid]))]
            self.fetched_bodies.append(uid)
            return "OK", [(b"1 (UID %s BODY[] {%d}" % (uid, len(self.messages[uid])), self.messages[uid]), b")"]
        if command == "STORE":
            assert args[1:] == ("+FLAGS", "(\\Seen)")
            self.seen.add(args[0])
            return "OK", [b""]
        raise AssertionError(command)

    def logout(self):  # noqa: ANN201
        self.logged_out = True


def test_the_poller_ingests_unread_mail_and_marks_every_outcome_read(world):
    org = world["org_id"]
    good = make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<p1@x>")
    unknown = make_mail("invoices+" + "b" * 20 + "@inbox.example.test", [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<p2@x>")
    junk = b"not an email"
    fake = FakeImap({b"1": good, b"2": unknown, b"3": junk})
    stats = poll_mailbox(connect=lambda: fake)
    assert (stats["read"], stats["accepted"], stats["rejected"], stats["failed"]) == (3, 1, 2, 0)
    assert fake.seen == {b"1", b"2", b"3"} and fake.logged_out
    assert counts(org)["emails"] == 1
    again = poll_mailbox(connect=lambda: fake)  # everything is read now
    assert again["read"] == 0


def test_the_poller_never_downloads_a_message_over_the_size_limit(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_max_message_bytes", 1000)
    fake = FakeImap({b"7": make_mail(address_of(world["org_id"]), [("a.pdf", GOOD_PDF, "application/pdf")])})
    stats = poll_mailbox(connect=lambda: fake)
    assert fake.fetched_bodies == [] and fake.seen == {b"7"} and stats["rejected"] == 1


def test_the_poller_leaves_deferred_and_failed_messages_unread(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_inbound_per_hour", 1)
    org = address_of(world["org_id"])
    one = make_mail(org, [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<q1@x>")
    two = make_mail(org, [("b.pdf", _pdf(["Tax Invoice 12"]), "application/pdf")], message_id="<q2@x>")
    fake = FakeImap({b"1": one, b"2": two})
    stats = poll_mailbox(connect=lambda: fake)
    assert (stats["accepted"], stats["deferred"]) == (1, 1) and fake.seen == {b"1"}

    def boom(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("storage is down")

    monkeypatch.setattr(inbound_email, "ingest", boom)
    monkeypatch.setattr(get_settings(), "rate_limit_inbound_per_hour", 0)
    stats = poll_mailbox(connect=lambda: fake)
    assert stats["failed"] == 1 and fake.seen == {b"1"}  # still unread: the next poll tries again


def test_only_one_worker_polls_at_a_time(world):
    from sqlalchemy import create_engine

    key = inbound_email._poll_lock_key()
    eng = create_engine(get_settings().database_url)
    with eng.connect() as other:
        assert other.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()
        try:
            fake = FakeImap({b"1": b"x"})
            assert poll_mailbox(connect=lambda: fake)["skipped"] is True and fake.seen == set()
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
    eng.dispose()
    assert poll_mailbox(connect=lambda: FakeImap({}))["read"] == 0  # the lock was released


def test_polling_is_off_without_a_mailbox(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_imap_host", None)
    assert poll_mailbox(connect=lambda: pytest.fail("connected")) == {"skipped": True}


# ------------------------------------------------------------------------------------------ row-level security
def test_inbound_emails_are_under_row_level_security(world):
    left, right = world["org_id"], world["other_org_id"]
    for org in (left, right):
        ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")], message_id=f"<rls-{org}@x>"), "imap")
    with session_scope(left) as s:
        assert [m.organization_id for m in s.scalars(select(InboundEmail))] == [left]
        assert s.scalars(select(InboundEmail).where(InboundEmail.organization_id == right)).all() == []
    s = new_session()  # no tenant bound: nothing is visible
    try:
        assert s.scalars(select(InboundEmail)).all() == []
    finally:
        s.close()
    with session_scope() as s:
        assert s.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'inbound_emails'"))


def test_a_tenant_session_cannot_write_another_tenants_inbound_email(world):
    left, right = world["org_id"], world["other_org_id"]
    with pytest.raises(DBAPIError), session_scope(left) as s:
        s.add(InboundEmail(organization_id=right, message_id="<forged@x>", source="imap", recipient="x@y.test"))
        s.flush()


def test_the_table_is_listed_among_the_protected_tables():
    from app.models import RLS_TABLES

    assert "inbound_emails" in RLS_TABLES


def test_an_invoice_cannot_point_at_another_tenants_email(world):
    left, right = world["org_id"], world["other_org_id"]
    ingest(make_mail(address_of(right), [("a.pdf", GOOD_PDF, "application/pdf")]), "imap")
    with session_scope(right) as s:
        foreign = s.scalars(select(InboundEmail)).one().id
    with session_scope(left) as s:
        assert s.get(InboundEmail, foreign) is None  # the left organization cannot even read it


# ------------------------------------------------------------------------------------------ API and settings
def test_the_invoice_list_says_where_each_invoice_came_from(client, as_user, world):
    org = world["org_id"]
    ingest(make_mail(address_of(org), [("a.pdf", GOOD_PDF, "application/pdf")]), "imap")
    h = as_user("finance@kinneret.example")
    items = client.get("/api/invoices?page_size=100", headers=h).json()["items"]
    emailed = [i for i in items if i["source"] == "email"]
    assert len(emailed) == 1
    assert (emailed[0]["email_sender"], emailed[0]["email_subject"]) == ("billing@supplier.example", "Invoice for October")
    assert all(i["source"] == "upload" and i["email_sender"] is None for i in items if i["source"] != "email")
    detail = client.get(f"/api/invoices/{emailed[0]['id']}", headers=h).json()
    assert detail["source"] == "email" and detail["email_sender"] == "billing@supplier.example"


def test_the_other_organization_sees_none_of_it(world):
    ingest(make_mail(address_of(world["org_id"]), [("a.pdf", GOOD_PDF, "application/pdf")]), "imap")
    with session_scope(world["org_id"]) as s:
        inv_id = s.scalars(select(Invoice).where(Invoice.source == "email")).one().id
    with session_scope(world["other_org_id"]) as s:
        assert s.scalars(select(Invoice).where(Invoice.source == "email")).all() == []
        assert s.get(Invoice, inv_id) is None


def test_an_administrator_sees_the_address_and_recent_messages(client, as_user, world):
    org = world["org_id"]
    ingest(make_mail(address_of(org), [("garbage.pdf", b"\x00\xff" * 4000, "application/pdf")]), "imap")
    body = client.get("/api/org/inbox", headers=as_user("admin@kinneret.example")).json()
    assert body["enabled"] is True and body["address"] == address_of(org)
    assert body["methods"] == {"imap": True, "webhook": True}
    assert [(m["status"], m["sender"]) for m in body["recent"]] == [("rejected", "billing@supplier.example")]
    assert body["recent"][0]["problems"][0]["status"] == "rejected" and body["recent"][0]["problems"][0]["reason"]


@pytest.mark.parametrize("email", ["procurement@kinneret.example", "finance@kinneret.example", "viewer@kinneret.example"])
def test_only_administrators_can_see_or_change_the_address(client, as_user, world, email):
    h = {**as_user(email), **CSRF}
    assert client.get("/api/org/inbox", headers=h).status_code == 403
    assert client.post("/api/org/inbox/regenerate", headers=h).status_code == 403


def test_regenerating_replaces_the_address_and_the_old_one_stops_working(client, as_user, world):
    org = world["org_id"]
    h = {**as_user("admin@kinneret.example"), **CSRF}
    old = address_of(org)
    new = client.post("/api/org/inbox/regenerate", headers=h).json()["address"]
    assert new != old and new == address_of(org)
    before = counts(org)
    r = ingest(make_mail(old, [("a.pdf", GOOD_PDF, "application/pdf")]), "imap")
    assert (r.status, r.reason) == ("rejected", "unknown_recipient") and counts(org) == before
    assert ingest(make_mail(new, [("a.pdf", GOOD_PDF, "application/pdf")]), "imap").status == "accepted"
    with session_scope(org) as s:
        entry = s.scalars(select(AuditLog).where(AuditLog.action == "org.inbox_address_regenerated")).one()
        assert token_of(org) not in str(entry.meta) + str(entry.after) + str(entry.before)


def test_every_organization_has_its_own_token(world):
    assert token_of(world["org_id"]) != token_of(world["other_org_id"])
    assert len(token_of(world["org_id"])) == 20


def test_the_settings_page_says_so_when_inbound_email_is_not_configured(client, as_user, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbound_address_template", "")
    h = {**as_user("admin@kinneret.example"), **CSRF}
    body = client.get("/api/org/inbox", headers=h).json()
    assert body["enabled"] is False and body["address"] is None
    assert client.post("/api/org/inbox/regenerate", headers=h).status_code == 409


# ------------------------------------------------------------------------------------------ configuration
@pytest.mark.parametrize("template", ["no-token@example.com", "{token}{token}@example.com", "{token}", "a{token}@nodot",
                                      "x@{token}.example.com", "a {token}@example.com"])
def test_a_bad_address_template_is_refused_at_startup(template):
    with pytest.raises(ValueError):
        Settings(inbound_address_template=template)


def test_a_short_webhook_secret_is_refused():
    with pytest.raises(ValueError):
        Settings(inbound_webhook_secret="too-short")


def test_the_address_pattern_matches_only_the_template():
    pattern = inbound_email.address_pattern("invoices+{token}@inbox.example.test")
    token = "0123456789abcdef0123"
    assert pattern.match(f"invoices+{token}@inbox.example.test")
    assert not pattern.match(f"invoices+{token}@inbox.example.test.evil.example")
    assert not pattern.match(f"xinvoices+{token}@inbox.example.test")
    assert not pattern.match(f"invoices+{token[:-1]}@inbox.example.test")
    assert not pattern.match(f"invoices+{token}0@inbox.example.test")


def test_docker_compose_passes_empty_values_for_everything_that_is_off():
    """docker-compose.yml sets every INBOUND_* variable, empty when unset: that must mean "off", never an error."""
    s = Settings(inbound_address_template="", inbound_webhook_secret="", inbound_imap_host="", inbound_imap_username="",
                 inbound_imap_password="", inbound_imap_port="993", inbound_imap_security="ssl")
    assert not s.inbound_enabled and not s.inbound_imap_enabled and not s.inbound_webhook_enabled


def test_a_template_with_a_way_in_is_enabled_and_production_refuses_an_unencrypted_mailbox():
    assert Settings(inbound_address_template=TEMPLATE, inbound_webhook_secret=SECRET).inbound_enabled
    assert not Settings(inbound_webhook_secret=SECRET).inbound_enabled  # a secret alone has no address to give out
    imap = {"inbound_imap_host": "h", "inbound_imap_username": "u", "inbound_imap_password": "p", "inbound_imap_security": "none"}
    assert Settings(**imap).inbound_imap_enabled  # fine for development
    with pytest.raises(ValueError, match="INBOUND_IMAP_SECURITY"):
        Settings(environment="production", jwt_secret="x" * 40, cookie_secure=True, storage_backend="s3", s3_sse="AES256",
                 s3_secret_key="prod-secret", cors_origins=["https://invoices.example.com"], database_url="postgresql+psycopg://a:b@h/d",
                 migration_database_url="postgresql+psycopg://a:b@h/d", **imap)


def test_a_file_that_was_already_uploaded_is_listed_with_its_reason(client, as_user, world):
    org = address_of(world["org_id"])
    ingest(make_mail(org, [("a.pdf", GOOD_PDF, "application/pdf")], message_id="<d1@x>"), "imap")
    ingest(make_mail(org, [("again.pdf", GOOD_PDF, "application/pdf")], message_id="<d2@x>"), "imap")
    newest = client.get("/api/org/inbox", headers=as_user("admin@kinneret.example")).json()["recent"][0]
    assert newest["accepted"] == 0
    assert [(p["filename"], p["status"]) for p in newest["problems"]] == [("again.pdf", "duplicate")]
    assert "already uploaded" in newest["problems"][0]["reason"]
