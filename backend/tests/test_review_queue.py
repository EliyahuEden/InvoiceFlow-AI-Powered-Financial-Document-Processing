"""Risk-first review queue, summary, next item, and the four reviewer decisions (integration)."""
from __future__ import annotations

import pytest

from tests.conftest import upload_invoice

pytestmark = pytest.mark.integration
PROC, FIN, ADMIN = "procurement@kinneret.example", "finance@kinneret.example", "admin@kinneret.example"
DOCS = ["02_qty_mismatch_hermon_he.pdf", "03_price_mismatch_bluewave_en.pdf", "05_missing_po_arava_mixed.pdf",
        "06_ambiguous_desc_carmel_he.pdf"]


@pytest.fixture()
def queue_world(client, as_user):
    proc = as_user(PROC)
    for d in DOCS:
        upload_invoice(client, proc, d)
    return {"fin": as_user(FIN), "admin": as_user(ADMIN), "proc": proc}


def _queue(client, h, **params):
    r = client.get("/api/review/queue", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_queue_is_ranked_risk_first_with_reasons(client, queue_world):
    items = _queue(client, queue_world["fin"])
    assert len(items) == 4
    assert [i["priority"]["rank"] for i in items] == [1, 2, 3, 4]
    levels = [i["priority"]["level"] for i in items]
    order = {"critical": 0, "high": 1, "normal": 2}
    assert levels == sorted(levels, key=order.get)
    assert items[0]["invoice_number"] and items[0]["finding_types"]
    assert "MISSING_PURCHASE_ORDER" in items[0]["finding_types"] and levels[0] == "critical"
    assert all(i["priority"]["reasons"] and all("code" in r for r in i["priority"]["reasons"]) for i in items)


def test_queue_filters(client, queue_world):
    h = queue_world["fin"]
    assert {i["priority"]["level"] for i in _queue(client, h, level="critical")} == {"critical"}
    price = _queue(client, h, type="PRICE_MISMATCH")
    assert price and all("PRICE_MISMATCH" in i["finding_types"] for i in price)
    assert _queue(client, h, q="BW-")  # by invoice number


def test_summary_matches_the_queue(client, queue_world):
    h = queue_world["fin"]
    s = client.get("/api/review/summary", headers=h).json()
    items = _queue(client, h)
    assert s["needs_review"] == len(items)
    assert sum(s["by_level"].values()) == len(items)
    assert [t["exception_id"] for t in s["top"]] == [i["exception_id"] for i in items[:5]]
    assert float(s["amount_at_risk"]) == pytest.approx(sum(float(i["amount_at_risk"]) for i in items))


def test_next_follows_queue_order_and_skips_items_waiting_for_information(client, queue_world):
    h = queue_world["fin"]
    items = _queue(client, h)
    first = client.get("/api/review/next", headers=h).json()
    assert first["item"]["exception_id"] == items[0]["exception_id"] and first["total"] == 4
    after = client.get("/api/review/next", headers=h, params={"after": items[0]["exception_id"]}).json()
    assert after["item"]["exception_id"] == items[1]["exception_id"]
    r = client.post(f"/api/exceptions/{items[0]['exception_id']}/decision", headers=h,
                    json={"decision": "request_info", "target": "supplier", "note": "Send the PO number"})
    assert r.status_code == 200, r.text
    assert client.get("/api/review/next", headers=h).json()["item"]["exception_id"] == items[1]["exception_id"]


def test_next_is_null_when_the_queue_is_clear(client, queue_world):
    h = queue_world["fin"]
    for i in _queue(client, h):
        r = client.post(f"/api/exceptions/{i['exception_id']}/decision", headers=h,
                        json={"decision": "reject", "note": "test clear"})
        assert r.status_code == 200, r.text
    assert client.get("/api/review/next", headers=h).json() == {"item": None, "position": 0, "total": 0}


def test_other_tenant_sees_nothing(client, queue_world, as_user):
    other = as_user("admin@yarden.example")
    assert _queue(client, other) == []
    assert client.get("/api/review/next", headers=other).json()["item"] is None


def _audit(client, h, exc_id):
    return client.get("/api/audit", headers=h, params={"entity_id": exc_id}).json()["items"]


def test_request_clarification_needs_a_note_and_a_target(client, queue_world):
    h = queue_world["fin"]
    exc = _queue(client, h)[0]["exception_id"]
    url = f"/api/exceptions/{exc}/decision"
    assert client.post(url, headers=h, json={"decision": "request_info", "target": "supplier"}).status_code == 422
    assert client.post(url, headers=h, json={"decision": "request_info", "note": "x", "target": "bank"}).status_code == 422
    r = client.post(url, headers=h, json={"decision": "request_info", "note": "Missing PO", "target": "procurement"})
    assert r.status_code == 200 and r.json()["status"] == "pending_info"
    row = next(a for a in _audit(client, queue_world["admin"], exc) if a["action"] == "exception.request_info")
    assert row["meta"]["target"] == "procurement" and row["before"]["status"] == "open"


def test_escalation_goes_to_an_admin_and_never_back_to_the_escalator(client, queue_world):
    fin, admin = queue_world["fin"], queue_world["admin"]
    exc = _queue(client, fin)[0]["exception_id"]
    url = f"/api/exceptions/{exc}/decision"
    assert client.post(url, headers=fin, json={"decision": "escalate"}).status_code == 422  # note required
    r = client.post(url, headers=fin, json={"decision": "escalate", "note": "Amount above my authority"})
    assert r.status_code == 200 and r.json()["status"] == "escalated"
    assert client.post(url, headers=fin, json={"decision": "approve", "note": "ok"}).status_code == 403
    item = next(i for i in _queue(client, admin) if i["exception_id"] == exc)
    assert {"code": "escalated", "params": {}} in item["priority"]["reasons"]
    assert client.post(url, headers=admin, json={"decision": "approve", "note": "approved by admin"}).status_code == 200
    actions = [a["action"] for a in _audit(client, admin, exc)]
    assert "exception.escalate" in actions and "exception.approve" in actions


def test_escalator_cannot_decide_their_own_escalation_even_as_admin(client, queue_world):
    admin = queue_world["admin"]
    exc = _queue(client, admin)[0]["exception_id"]
    url = f"/api/exceptions/{exc}/decision"
    assert client.post(url, headers=admin, json={"decision": "escalate", "note": "second opinion"}).status_code == 200
    assert client.post(url, headers=admin, json={"decision": "approve", "note": "self"}).status_code == 403


def test_a_decided_item_cannot_be_decided_again(client, queue_world):
    h = queue_world["fin"]
    exc = _queue(client, h)[0]["exception_id"]
    url = f"/api/exceptions/{exc}/decision"
    assert client.post(url, headers=h, json={"decision": "reject", "note": "wrong"}).status_code == 200
    assert client.post(url, headers=h, json={"decision": "approve", "note": "again"}).status_code == 409
