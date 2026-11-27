"""Outbound webhooks: registration, SSRF refusal, queued signed delivery, retries with backoff, delivery log, RLS."""
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine, select, text

from app.core.config import get_settings
from app.core.db import new_session, session_scope
from app.models import AuditLog, Job, WebhookDelivery, WebhookEndpoint
from app.services import jobs, webhooks
from app.worker import drain
from tests.conftest import upload_invoice

ADMIN = "admin@kinneret.example"
URL = "https://hooks.receiver.example/invoiceflow"
PUBLIC_IP = "93.184.216.34"


class Receiver:
    """Stands in for the network: answers requests from a script and keeps what it was sent."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.statuses: list[int] = []  # answers in order; the last one repeats

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        code = self.statuses[min(len(self.requests), len(self.statuses)) - 1] if self.statuses else 200
        return httpx.Response(code, text="ok" if code < 400 else "nope", headers={"Location": "http://10.0.0.1/"} if 300 <= code < 400 else {})


@pytest.fixture()
def net(monkeypatch):
    receiver = Receiver()
    names = {"hooks.receiver.example": [PUBLIC_IP], "other.receiver.example": ["2606:4700:4700::1111"],
             "internal.receiver.example": ["10.0.0.5"], "rebind.receiver.example": [PUBLIC_IP]}
    monkeypatch.setattr(webhooks, "resolver", lambda host, _port: names[host])
    monkeypatch.setattr(webhooks, "transport", httpx.MockTransport(receiver))
    receiver.names = names
    return receiver


def register(client, as_user, url=URL, events=("invoice.approved",), email=ADMIN, **extra) -> tuple[dict, str]:
    r = client.post("/api/org/webhooks", headers=as_user(email), json={"url": url, "events": list(events), **extra})
    assert r.status_code == 201, r.text
    return r.json()["webhook"], r.json()["secret"]


def deliveries(org_id) -> list[WebhookDelivery]:
    with session_scope(org_id) as s:
        rows = s.scalars(select(WebhookDelivery).order_by(WebhookDelivery.created_at)).all()
        s.expunge_all()
        return rows


def make_due() -> None:
    """Pretend the backoff has elapsed for every queued job."""
    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.begin() as conn:
            conn.execute(text("UPDATE jobs SET run_after = now() - interval '1 second' WHERE status = 'queued' AND run_after IS NOT NULL"))
    finally:
        eng.dispose()


def approve(client, as_user, name="01_correct_tavor_he.pdf") -> dict:
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), name)
    r = client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=as_user("finance@kinneret.example"),
                    json={"decision": "approve"})
    assert r.status_code == 200, r.text
    return inv


# ------------------------------------------------------------------ registration

def test_only_administrators_manage_webhooks(client, as_user, net):
    body = {"url": URL, "events": ["invoice.approved"]}
    for email in ("procurement@kinneret.example", "finance@kinneret.example", "viewer@kinneret.example"):
        h = as_user(email)
        assert client.post("/api/org/webhooks", headers=h, json=body).status_code == 403
        assert client.get("/api/org/webhooks", headers=h).status_code == 403
    wh, _ = register(client, as_user)
    for email in ("procurement@kinneret.example", "finance@kinneret.example", "viewer@kinneret.example"):
        h = as_user(email)
        for method, path in (("PATCH", ""), ("DELETE", ""), ("POST", "/test"), ("POST", "/rotate-secret"), ("GET", "/deliveries")):
            assert client.request(method, f"/api/org/webhooks/{wh['id']}{path}", headers=h, json={}).status_code == 403, (email, method, path)


def test_the_secret_is_shown_once_and_stored_encrypted(client, as_user, net, world):
    r = client.post("/api/org/webhooks", headers=as_user(ADMIN), json={"url": URL, "events": ["exception.opened", "invoice.approved"],
                                                                      "description": " ERP "})
    assert r.headers["cache-control"] == "no-store"
    wh, secret = r.json()["webhook"], r.json()["secret"]
    assert secret.startswith("whsec_") and wh["secret_hint"] == secret[-4:] and wh["description"] == "ERP"
    assert wh["events"] == ["invoice.approved", "exception.opened"]  # normalised to the documented order
    listing = client.get("/api/org/webhooks", headers=as_user(ADMIN))
    assert secret not in listing.text and "secret_enc" not in listing.text
    assert listing.json()["event_types"] == ["invoice.approved", "payment.approved", "exception.opened"]

    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.connect() as conn:
            dump = " ".join(str(v) for t in ("webhook_endpoints", "audit_logs") for row in conn.execute(text(f"SELECT * FROM {t}")) for v in row)
    finally:
        eng.dispose()
    assert secret not in dump and secret[6:] not in dump
    with session_scope(world["org_id"]) as s:
        stored = s.scalars(select(WebhookEndpoint)).one()
        assert webhooks.decrypt_secret(stored.secret_enc) == secret


@pytest.mark.parametrize("url,message", [
    ("http://hooks.receiver.example/x", "https://"),
    ("https://127.0.0.1/hook", "private or internal"),
    ("https://[::1]/hook", "private or internal"),
    ("https://169.254.169.254/latest/meta-data/", "private or internal"),
    ("https://10.1.2.3:8443/hook", "private or internal"),
    ("https://internal.receiver.example/hook", "private or internal"),  # a name that resolves inward
    ("https://user:pw@hooks.receiver.example/x", "user name"),
    ("ftp://hooks.receiver.example/x", "https://"),
])
def test_unsafe_targets_are_refused_when_registering(client, as_user, net, url, message):
    r = client.post("/api/org/webhooks", headers=as_user(ADMIN), json={"url": url, "events": ["invoice.approved"]})
    assert r.status_code == 422 and message in r.json()["detail"], r.text
    assert client.get("/api/org/webhooks", headers=as_user(ADMIN)).json()["items"] == []


def test_events_are_validated_and_updates_recheck_the_url(client, as_user, net):
    h = as_user(ADMIN)
    for events in ([], ["nope"], ["invoice.approved", "nope"], ["webhook.test"]):
        assert client.post("/api/org/webhooks", headers=h, json={"url": URL, "events": events}).status_code == 422, events
    wh, _ = register(client, as_user)
    assert client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"url": "https://127.0.0.1/"}).status_code == 422
    assert client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"events": ["bogus"]}).status_code == 422
    ok = client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"url": "https://other.receiver.example/in", "active": False,
                                                                    "events": ["payment.approved"], "description": None})
    assert ok.status_code == 200
    assert ok.json()["webhook"] == {**wh, "url": "https://other.receiver.example/in", "active": False,
                                    "events": ["payment.approved"], "description": None}
    assert client.patch(f"/api/org/webhooks/{uuid.uuid4()}", headers=h, json={"active": True}).status_code == 404


def test_management_is_audited_without_secrets(client, as_user, net, world):
    h = as_user(ADMIN)
    wh, secret = register(client, as_user)
    client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"active": False})
    client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"active": False})  # no change, no entry
    rotated = client.post(f"/api/org/webhooks/{wh['id']}/rotate-secret", headers=h).json()["secret"]
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=h)
    client.delete(f"/api/org/webhooks/{wh['id']}", headers=h)
    with session_scope(world["org_id"]) as s:
        entries = s.scalars(select(AuditLog).where(AuditLog.entity_type == "webhook_endpoint").order_by(AuditLog.created_at)).all()
        assert [e.action for e in entries] == ["webhook.created", "webhook.updated", "webhook.secret_rotated",
                                               "webhook.test_sent", "webhook.deleted"]
        assert all(e.actor_label == ADMIN for e in entries)
        blob = json.dumps([[e.before, e.after, e.meta] for e in entries])
        assert secret not in blob and rotated not in blob
    assert client.get("/api/audit/verify", headers=h).json()["valid"] is True


def test_the_number_of_webhooks_is_capped(client, as_user, net, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_ENDPOINTS", 2)
    register(client, as_user)
    register(client, as_user)
    r = client.post("/api/org/webhooks", headers=as_user(ADMIN), json={"url": URL, "events": ["invoice.approved"]})
    assert r.status_code == 409


# ------------------------------------------------------------------ signatures

def test_signature_round_trip_and_tampering():
    body = b'{"id":"1","type":"invoice.approved"}'
    header = webhooks.sign("whsec_abc", body, 1_700_000_000)
    assert header.startswith("t=1700000000,v1=") and len(header.split("v1=")[1]) == 64
    assert webhooks.verify_signature("whsec_abc", header, body, now=1_700_000_100)
    assert not webhooks.verify_signature("whsec_other", header, body, now=1_700_000_100)  # wrong secret
    assert not webhooks.verify_signature("whsec_abc", header, body + b" ", now=1_700_000_100)  # altered body
    assert not webhooks.verify_signature("whsec_abc", header, body, now=1_700_000_000 + 301)  # replayed later
    assert not webhooks.verify_signature("whsec_abc", header.replace("t=1700000000", "t=1700000001"), body, now=1_700_000_100)
    for junk in ("", "v1=abc", "t=x,v1=abc", "garbage"):
        assert not webhooks.verify_signature("whsec_abc", junk, body)


def test_secret_encryption_round_trip():
    secret = webhooks.new_secret()
    token = webhooks.encrypt_secret(secret)
    assert secret not in token and webhooks.decrypt_secret(token) == secret
    assert webhooks.decrypt_secret("not-a-token") is None
    assert webhooks.new_secret() != secret


# ------------------------------------------------------------------ delivery

def test_an_approval_queues_signed_deliveries_that_the_worker_sends(client, as_user, net, world):
    wh, secret = register(client, as_user, events=("invoice.approved", "payment.approved"))
    inv = approve(client, as_user)
    queued = deliveries(world["org_id"])
    assert sorted(d.event_type for d in queued) == ["invoice.approved", "payment.approved"]
    assert {d.status for d in queued} == {"pending"} and net.requests == []  # nothing is sent inside the request
    with session_scope(world["org_id"]) as s:
        assert len(s.scalars(select(Job).where(Job.type == "webhook.deliver")).all()) == 2
    assert drain() == 2

    assert len(net.requests) == 2
    by_event = {r.headers["x-invoiceflow-event"]: r for r in net.requests}
    request = by_event["invoice.approved"]
    body = request.content
    assert webhooks.verify_signature(secret, request.headers["x-invoiceflow-signature"], body)
    event = json.loads(body)
    assert event["type"] == "invoice.approved" and event["organization_id"] == str(world["org_id"])
    assert event["data"]["invoice_id"] == inv["invoice_id"] and event["data"]["status"] == "approved"
    assert event["data"]["invoice_number"] == "TV-24518" and event["data"]["currency"] == "ILS"
    assert request.headers["x-invoiceflow-event-id"] == event["id"]
    assert request.headers["content-type"] == "application/json" and request.headers["user-agent"].startswith("InvoiceFlow")
    paid = json.loads(by_event["payment.approved"].content)["data"]
    assert paid["approval"] == {"step": 1, "final": True}
    # the connection goes to the address that was checked, with the real name kept for TLS and Host
    assert request.url.host == PUBLIC_IP and request.url.port in (None, 443) and request.url.path == "/invoiceflow"
    assert request.headers["host"] == "hooks.receiver.example" and request.extensions["sni_hostname"] == "hooks.receiver.example"
    assert request.headers["x-invoiceflow-delivery"] in {str(d.id) for d in queued}

    done = deliveries(world["org_id"])
    assert {d.status for d in done} == {"succeeded"} and {d.attempts for d in done} == {1}
    assert all(d.delivered_at and d.last_status_code == 200 and d.next_attempt_at is None for d in done)
    assert done[0].attempt_log[0]["status_code"] == 200


def test_the_secret_signs_with_the_current_value_after_rotation(client, as_user, net, world):
    wh, old = register(client, as_user)
    new = client.post(f"/api/org/webhooks/{wh['id']}/rotate-secret", headers=as_user(ADMIN)).json()["secret"]
    assert new != old
    approve(client, as_user)
    drain()
    request = net.requests[0]
    assert webhooks.verify_signature(new, request.headers["x-invoiceflow-signature"], request.content)
    assert not webhooks.verify_signature(old, request.headers["x-invoiceflow-signature"], request.content)


def test_a_new_exception_is_announced(client, as_user, net, world):
    register(client, as_user, events=("exception.opened",))
    upload_invoice(client, as_user("procurement@kinneret.example"), "02_qty_mismatch_hermon_he.pdf")
    drain()
    [row] = deliveries(world["org_id"])
    assert row.event_type == "exception.opened" and row.status == "succeeded"
    data = json.loads(net.requests[0].content)["data"]
    assert data["priority"] in ("low", "medium", "high", "critical") and data["discrepancy_types"]
    assert data["invoice"]["status"] == "exception" and data["exception_id"] and data["title"]


def test_only_subscribed_active_endpoints_receive_events(client, as_user, net, world):
    h = as_user(ADMIN)
    only_exceptions, _ = register(client, as_user, events=("exception.opened",))
    off, _ = register(client, as_user, url="https://other.receiver.example/x", events=("invoice.approved",))
    on, _ = register(client, as_user, events=("invoice.approved",))
    client.patch(f"/api/org/webhooks/{off['id']}", headers=h, json={"active": False})
    approve(client, as_user)
    rows = deliveries(world["org_id"])
    assert [(str(d.endpoint_id), d.event_type) for d in rows] == [(on["id"], "invoice.approved")]
    drain()
    assert [r.url.host for r in net.requests] == [PUBLIC_IP]
    assert only_exceptions["id"] != on["id"]


def test_nothing_is_queued_when_the_change_is_rolled_back(client, as_user, net, world):
    register(client, as_user)
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    # the uploader may not approve (segregation of duties): the refused request leaves no delivery behind
    r = client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=as_user("procurement@kinneret.example"),
                    json={"decision": "approve"})
    assert r.status_code == 403
    assert deliveries(world["org_id"]) == []
    r = client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=as_user("finance@kinneret.example"), json={"decision": "reject"})
    assert r.status_code == 200 and deliveries(world["org_id"]) == []  # a rejection is not an approval


def test_the_test_button_queues_a_delivery_that_shows_in_the_log(client, as_user, net, world):
    h = as_user(ADMIN)
    wh, secret = register(client, as_user, events=("exception.opened",))
    r = client.post(f"/api/org/webhooks/{wh['id']}/test", headers=h)
    assert r.status_code == 202 and r.json()["status"] == "pending"
    log = client.get(f"/api/org/webhooks/{wh['id']}/deliveries", headers=h).json()
    assert log["total"] == 1 and log["items"][0]["status"] == "pending" and log["items"][0]["is_test"] is True
    drain()
    log = client.get(f"/api/org/webhooks/{wh['id']}/deliveries", headers=h).json()
    [row] = log["items"]
    assert row["event_type"] == "webhook.test" and row["status"] == "succeeded" and row["attempts"] == 1
    assert row["last_status_code"] == 200 and row["delivered_at"] and row["id"] == r.json()["delivery_id"]
    assert row["attempt_log"][0]["duration_ms"] >= 0
    event = json.loads(net.requests[0].content)
    assert event["type"] == "webhook.test" and webhooks.verify_signature(secret, net.requests[0].headers["x-invoiceflow-signature"], net.requests[0].content)
    # a test works on a switched-off endpoint too, so it can be tried before turning it on
    client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"active": False})
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=h)
    drain()
    assert client.get(f"/api/org/webhooks/{wh['id']}/deliveries?status=succeeded", headers=h).json()["total"] == 2


def test_the_delivery_log_is_paged_filtered_and_tenant_scoped(client, as_user, net, world):
    h = as_user(ADMIN)
    wh, _ = register(client, as_user)
    for _ in range(3):
        client.post(f"/api/org/webhooks/{wh['id']}/test", headers=h)
    net.statuses = [200, 500, 200]
    drain()
    page = client.get(f"/api/org/webhooks/{wh['id']}/deliveries?page_size=2", headers=h).json()
    assert page["total"] == 3 and page["pages"] == 2 and len(page["items"]) == 2
    assert client.get(f"/api/org/webhooks/{wh['id']}/deliveries?status=retrying", headers=h).json()["total"] == 1
    other = as_user("admin@yarden.example")
    for method, path in (("GET", "/deliveries"), ("POST", "/test"), ("PATCH", ""), ("DELETE", ""), ("POST", "/rotate-secret")):
        assert client.request(method, f"/api/org/webhooks/{wh['id']}{path}", headers=other, json={}).status_code == 404, (method, path)
    assert client.get("/api/org/webhooks", headers=other).json()["items"] == []


# ------------------------------------------------------------------ failure, retries, backoff

def test_a_failing_receiver_is_retried_with_growing_delays_until_it_works(client, as_user, net, world):
    h = as_user(ADMIN)
    wh, _ = register(client, as_user)
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=h)
    net.statuses = [503, 500, 200]

    assert drain() == 1
    [d] = deliveries(world["org_id"])
    assert (d.status, d.attempts, d.last_status_code) == ("retrying", 1, 503) and d.last_error == "The receiver answered with HTTP 503"
    assert d.delivered_at is None
    assert 25 <= (d.next_attempt_at - datetime.now(UTC)).total_seconds() <= 31  # first backoff: 30 s
    with session_scope(world["org_id"]) as s:
        job = s.scalars(select(Job).where(Job.type == "webhook.deliver")).one()
        assert job.status == "queued" and job.attempts == 1
        assert 25 <= (job.run_after - datetime.now(UTC)).total_seconds() <= 31
    assert drain() == 0 and len(net.requests) == 1  # not due yet: nothing is sent early

    make_due()
    assert drain() == 1
    [d] = deliveries(world["org_id"])
    assert (d.status, d.attempts, d.last_status_code) == ("retrying", 2, 500)
    assert 115 <= (d.next_attempt_at - datetime.now(UTC)).total_seconds() <= 121  # second backoff: 2 min

    make_due()
    assert drain() == 1
    [d] = deliveries(world["org_id"])
    assert (d.status, d.attempts, d.last_status_code, d.last_error) == ("succeeded", 3, 200, None)
    assert [a["status_code"] for a in d.attempt_log] == [503, 500, 200] and d.next_attempt_at is None
    # the same event, with the same delivery id, every time
    assert len({r.headers["x-invoiceflow-delivery"] for r in net.requests}) == 1 and len(net.requests) == 3


def test_the_backoff_schedule_grows_and_is_capped():
    delays = [jobs.retry_delay("webhook.deliver", n) for n in range(1, 9)]
    assert delays == [30, 120, 600, 3600, 14400, 43200, 43200, 43200]
    assert jobs.retry_delay("invoice.process", 1) == 10 and jobs.retry_delay("invoice.process", 9) == 300  # unchanged for others
    assert get_settings().webhook_max_attempts == 6


def test_a_delivery_that_keeps_failing_ends_as_failed_and_is_audited(client, as_user, net, world):
    h = as_user(ADMIN)
    wh, _ = register(client, as_user)
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=h)
    net.statuses = [500]
    eng = create_engine(get_settings().migration_database_url)
    with eng.begin() as conn:
        conn.execute(text("UPDATE jobs SET max_attempts = 3 WHERE type = 'webhook.deliver'"))
    eng.dispose()
    for expected in ("retrying", "retrying", "failed"):
        make_due()
        assert drain() == 1
        [d] = deliveries(world["org_id"])
        assert d.status == expected
    assert d.attempts == 3 and d.next_attempt_at is None and d.last_status_code == 500 and len(d.attempt_log) == 3
    make_due()
    assert drain() == 0 and len(net.requests) == 3  # no fourth attempt
    with session_scope(world["org_id"]) as s:
        job = s.scalars(select(Job).where(Job.type == "webhook.deliver")).one()
        assert job.status == "failed"
        failed = s.scalars(select(AuditLog).where(AuditLog.action == "webhook.delivery_failed")).one()
        assert failed.actor_type == "system" and failed.meta["attempts"] == 3 and str(failed.entity_id) == wh["id"]
    log = client.get(f"/api/org/webhooks/{wh['id']}/deliveries?status=failed", headers=h).json()
    assert log["total"] == 1 and log["items"][0]["last_error"] == "The receiver answered with HTTP 500"


def test_redirects_are_not_followed(client, as_user, net, world):
    wh, _ = register(client, as_user)
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=as_user(ADMIN))
    net.statuses = [302]
    drain()
    [d] = deliveries(world["org_id"])
    assert d.status == "retrying" and d.last_status_code == 302 and "redirect" in d.last_error
    assert len(net.requests) == 1  # the Location (an internal address here) was never requested


def test_a_name_that_later_resolves_inward_is_refused_at_delivery_time(client, as_user, net, world):
    wh, _ = register(client, as_user, url="https://rebind.receiver.example/hook")
    net.names["rebind.receiver.example"] = ["169.254.169.254"]  # DNS rebinding after registration
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=as_user(ADMIN))
    drain()
    [d] = deliveries(world["org_id"])
    assert d.status == "retrying" and "private or internal" in d.last_error and d.last_status_code is None
    assert net.requests == []  # no connection was attempted


def test_a_receiver_with_several_addresses_is_reached_through_a_working_one(client, as_user, net, world, monkeypatch):
    wh, _ = register(client, as_user)
    net.names["hooks.receiver.example"] = ["93.184.216.35", PUBLIC_IP]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "93.184.216.35":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(204)

    monkeypatch.setattr(webhooks, "transport", httpx.MockTransport(handler))
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=as_user(ADMIN))
    drain()
    assert calls == ["93.184.216.35", PUBLIC_IP] and deliveries(world["org_id"])[0].status == "succeeded"


def test_ipv6_receivers_are_addressed_in_brackets(client, as_user, net, world):
    wh, _ = register(client, as_user, url="https://other.receiver.example:8443/a/b?c=d")
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=as_user(ADMIN))
    drain()
    request = net.requests[0]
    assert request.url.host == "2606:4700:4700::1111" and request.url.port == 8443
    assert request.url.raw_path == b"/a/b?c=d" and request.headers["host"] == "other.receiver.example:8443"


def test_a_removed_or_switched_off_endpoint_fails_its_queued_events_for_good(client, as_user, net, world):
    h = as_user(ADMIN)
    wh, _ = register(client, as_user)
    approve(client, as_user)
    client.patch(f"/api/org/webhooks/{wh['id']}", headers=h, json={"active": False})
    assert drain() == 1 and net.requests == []
    [d] = deliveries(world["org_id"])
    assert d.status == "failed" and "switched off" in d.last_error
    with session_scope(world["org_id"]) as s:
        assert s.scalars(select(Job).where(Job.type == "webhook.deliver")).one().status == "failed"  # permanent: not retried

    wh2, _ = register(client, as_user, events=("exception.opened",))
    client.post(f"/api/org/webhooks/{wh2['id']}/test", headers=h)
    client.delete(f"/api/org/webhooks/{wh2['id']}", headers=h)  # its deliveries go with it
    assert drain() == 1  # the orphaned job ends quietly
    with session_scope(world["org_id"]) as s:
        assert {j.status for j in s.scalars(select(Job).where(Job.type == "webhook.deliver"))} == {"failed"}


def test_the_job_queue_keeps_one_job_per_delivery(client, as_user, net, world):
    wh, _ = register(client, as_user)
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=as_user(ADMIN))
    with session_scope(world["org_id"]) as s:
        job = s.scalars(select(Job).where(Job.type == "webhook.deliver")).one()
        delivery_id = job.payload["delivery_id"]
        assert job.idempotency_key == f"webhook.deliver:{delivery_id}" and str(job.entity_id) == delivery_id
        assert job.max_attempts == get_settings().webhook_max_attempts


# ------------------------------------------------------------------ tenant isolation

def test_webhook_tables_are_protected_by_row_level_security(client, as_user, net, world):
    wh, _ = register(client, as_user)
    client.post(f"/api/org/webhooks/{wh['id']}/test", headers=as_user(ADMIN))
    left, right = world["org_id"], world["other_org_id"]
    s = new_session(right)
    try:
        assert s.scalars(select(WebhookEndpoint)).all() == [] and s.scalars(select(WebhookDelivery)).all() == []
        s.add(WebhookEndpoint(organization_id=left, url=URL, events=[], secret_enc="x", secret_hint="x"))
        with pytest.raises(Exception, match="row-level security"):
            s.flush()
        s.rollback()
        s.add(WebhookDelivery(organization_id=left, endpoint_id=uuid.UUID(wh["id"]), event_type="x", payload={}))
        with pytest.raises(Exception, match="row-level security"):
            s.flush()
    finally:
        s.rollback()
        s.close()
    s = new_session()
    try:  # no tenant bound at all
        assert s.scalars(select(WebhookEndpoint)).all() == [] and s.scalars(select(WebhookDelivery)).all() == []
    finally:
        s.close()
    with session_scope(left) as own:
        assert len(own.scalars(select(WebhookEndpoint)).all()) == 1 and len(own.scalars(select(WebhookDelivery)).all()) == 1


def test_events_of_one_organization_never_reach_another_organizations_endpoint(client, as_user, net, world):
    register(client, as_user, url="https://other.receiver.example/yarden", email="admin@yarden.example")
    approve(client, as_user)  # an approval in Kinneret
    assert deliveries(world["other_org_id"]) == [] and deliveries(world["org_id"]) == []
    drain()
    assert net.requests == []
