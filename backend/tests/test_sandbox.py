""""Try the demo": each visitor gets a private copy of the demo workspace, isolated from every other visitor and from
the template, deleted after its day."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import upload_invoice

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}


def try_demo(client) -> dict:  # noqa: ANN001
    r = client.post("/api/auth/demo", headers=CSRF, json={"locale": "en"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", **CSRF, "_body": r.json()}


def headers(h: dict) -> dict:
    return {k: v for k, v in h.items() if not k.startswith("_")}


def test_a_visitor_gets_a_private_copy_of_the_demo_with_working_files(client, as_user):
    finance = as_user("finance@kinneret.example")
    template_invoice = upload_invoice(client, finance, "01_correct_tavor_he.pdf")["invoice_id"]
    template = client.get("/api/invoices", headers=finance).json()["items"]

    visitor = try_demo(client)
    me = visitor["_body"]
    assert me["sandbox"]["expires_at"] and me["role"] == "finance_reviewer"
    assert me["organization"]["slug"].startswith("demo-")
    copy = client.get("/api/invoices", headers=headers(visitor)).json()["items"]
    assert len(copy) == len(template)                                   # the same demo data...
    assert {i["id"] for i in copy}.isdisjoint({i["id"] for i in template})  # ...under new ids
    assert template_invoice not in {i["id"] for i in copy}
    detail = client.get(f"/api/invoices/{copy[0]['id']}", headers=headers(visitor)).json()
    image = client.get(f"/api/documents/{detail['document']['id']}/pages/1/image?width=400", headers=headers(visitor))
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"  # the original file was copied
    assert client.get("/api/suppliers", headers=headers(visitor)).json()["items"]      # master data came along
    assert client.get(f"/api/invoices/{template_invoice}", headers=headers(visitor)).status_code == 404


def test_visitors_never_see_each_others_uploads(client, as_user):
    finance = as_user("finance@kinneret.example")
    upload_invoice(client, finance, "01_correct_tavor_he.pdf")
    first, second = try_demo(client), try_demo(client)
    before = len(client.get("/api/invoices", headers=headers(second)).json()["items"])
    upload_invoice(client, headers(first), "03_price_mismatch_bluewave_en.pdf")
    assert len(client.get("/api/invoices", headers=headers(first)).json()["items"]) == before + 1
    assert len(client.get("/api/invoices", headers=headers(second)).json()["items"]) == before
    assert len(client.get("/api/invoices", headers=finance).json()["items"]) == before  # the template is untouched


def test_sandboxes_are_deleted_after_their_day_with_the_visitor(client, as_user):
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.models import Organization, User
    from app.services.sandbox import expire_due

    finance = as_user("finance@kinneret.example")
    upload_invoice(client, finance, "01_correct_tavor_he.pdf")
    visitor = try_demo(client)
    org_id, email = visitor["_body"]["organization"]["id"], visitor["_body"]["user"]["email"]
    assert expire_due() == 0                                              # not yet due
    assert expire_due(now=datetime.now(UTC) + timedelta(hours=25)) == 1
    with session_scope() as s:
        assert s.get(Organization, org_id) is None
        assert s.scalars(select(User).where(User.email == email)).first() is None
        assert s.scalars(select(Organization).where(Organization.slug == "kinneret")).first() is not None
    assert client.get("/api/invoices", headers=finance).json()["items"]   # the template keeps its data
    from app.worker import drain
    drain()                                                               # file and checkpoint cleanup runs cleanly


def test_the_demo_can_be_switched_off(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_SANDBOX_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert client.post("/api/auth/demo", headers=CSRF, json={}).status_code == 403
    finally:
        monkeypatch.delenv("DEMO_SANDBOX_ENABLED")
        get_settings.cache_clear()


def test_locking_the_template_keeps_the_demo_working(client, as_user):
    from app.demo.spec import DEMO_PASSWORD
    from app.services.sandbox import lock_template

    finance = as_user("finance@kinneret.example")
    upload_invoice(client, finance, "01_correct_tavor_he.pdf")
    assert lock_template() >= 1
    r = client.post("/api/auth/login", json={"email": "finance@kinneret.example", "password": DEMO_PASSWORD})
    assert r.status_code == 401                                           # the published password no longer works
    assert client.get("/api/invoices", headers=headers(try_demo(client))).json()["items"]  # visitors still get data


def test_a_copy_carries_the_demo_history_with_a_valid_chain(client, as_user):
    """The visitor sees how the demo invoices were processed: the business events and the AI call records come along,
    re-keyed to the copy, while the template's sign-ins stay behind. The copied chain verifies on its own."""
    finance = as_user("finance@kinneret.example")
    upload_invoice(client, finance, "02_qty_mismatch_hermon_he.pdf")
    template_events = client.get("/api/audit?page_size=200", headers=finance).json()["items"]
    template_calls = sum(r["calls"] for r in client.get("/api/observability/summary", headers=finance).json()["by_model"])

    visitor = try_demo(client)
    h, email = headers(visitor), visitor["_body"]["user"]["email"]
    events = client.get("/api/audit?page_size=200", headers=h).json()["items"]
    copied = [e for e in events if e["action"] != "sandbox.created" and e["actor_label"] != email]
    assert copied and all(e["action"].startswith(("invoice.", "exception.", "approval.", "agent.", "purchase_order.",
                                                    "goods_receipt.", "supplier.", "knowledge.")) for e in copied)
    assert not any(e["action"].startswith("auth.") for e in copied)              # the template's sign-ins stay behind
    assert {e["id"] for e in events}.isdisjoint({e["id"] for e in template_events})
    invoices = {i["id"] for i in client.get("/api/invoices?page_size=100", headers=h).json()["items"]}
    uploaded = [e for e in copied if e["action"] == "invoice.uploaded"]
    assert uploaded and all(e["entity_id"] in invoices for e in uploaded)       # events point at the copy's own records
    chain = client.get("/api/audit/verify", headers=h).json()
    assert chain["valid"] is True and chain["checked"] == len(events)
    calls = sum(r["calls"] for r in client.get("/api/observability/summary", headers=h).json()["by_model"])
    assert template_calls > 0 and calls == template_calls                       # the AI call records came along
