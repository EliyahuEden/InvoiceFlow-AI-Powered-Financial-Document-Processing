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


def test_queue_filters(client, queue_world, world):
    h = queue_world["fin"]
    assert {i["priority"]["level"] for i in _queue(client, h, level="critical")} == {"critical"}
    price = _queue(client, h, type="PRICE_MISMATCH")
    assert price and all("PRICE_MISMATCH" in i["finding_types"] for i in price)
    assert _queue(client, h, q="BW-")  # by invoice number
    items = _queue(client, h)
    supplier_id = next(i["supplier_id"] for i in items if i["supplier_id"])
    assert all(i["supplier_id"] == supplier_id for i in _queue(client, h, supplier_id=supplier_id))
    import uuid
    from datetime import date, timedelta
    from app.core.db import session_scope
    from app.models import Invoice

    with session_scope(world["org_id"]) as db:
        for item, days in zip(items, [-1, 2, 10, None]):
            db.get(Invoice, uuid.UUID(item["invoice_id"])).due_date = date.today() + timedelta(days=days) if days is not None else None
    assert [i["exception_id"] for i in _queue(client, h, due="overdue")] == [items[0]["exception_id"]]
    assert [i["exception_id"] for i in _queue(client, h, due="soon")] == [items[1]["exception_id"]]
    assert {i["exception_id"] for i in _queue(client, h, due="later")} == {i["exception_id"] for i in items[2:]}
    assert _queue(client, h, status="approved") == []
    assert client.post(f"/api/exceptions/{items[0]['exception_id']}/decision", headers=h,
                       json={"decision": "reject", "note": "filter guard"}).status_code == 200
    assert [i["exception_id"] for i in _queue(client, h, status="rejected")] == [items[0]["exception_id"]]


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
    rows = _audit(client, admin, exc)
    actions = [a["action"] for a in rows]
    assert "exception.escalate" in actions and "exception.approve" in actions
    for action in ("exception.escalate", "exception.approve"):
        row = next(a for a in rows if a["action"] == action)
        assert row["before"]["status"] and row["after"]["status"] and row["meta"]["note"]


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
    row = next(a for a in _audit(client, queue_world["admin"], exc) if a["action"] == "exception.reject")
    assert row["before"]["status"] == "open" and row["after"]["status"] == "rejected"
    assert row["meta"]["note"] == "wrong"


def test_read_only_user_has_no_actionable_next_item(client, queue_world, as_user):
    for email in ("viewer@kinneret.example", PROC):
        headers = as_user(email)
        assert _queue(client, headers)
        assert client.get("/api/review/next", headers=headers).json() == {"item": None, "position": 0, "total": 0}


@pytest.mark.parametrize("decision", ["request_info", "escalate"])
def test_escalation_cannot_be_rerouted_by_the_escalating_reviewer(client, queue_world, decision):
    fin = queue_world["fin"]
    exc = _queue(client, fin)[0]["exception_id"]
    url = f"/api/exceptions/{exc}/decision"
    assert client.post(url, headers=fin, json={"decision": "escalate", "note": "Need administrator"}).status_code == 200
    r = client.post(url, headers=fin, json={"decision": decision, "note": "reroute", "target": "supplier"})
    assert r.status_code == 403
    assert client.get(f"/api/exceptions/{exc}", headers=fin).json()["status"] == "escalated"


def test_stale_reviewer_cannot_overwrite_a_committed_decision(client, queue_world, world):
    import uuid
    from fastapi import HTTPException
    from app.core.db import new_session
    from app.models import ExceptionCase, User
    from app.services.workflow import decide_exception

    exc_id = uuid.UUID(_queue(client, queue_world["fin"])[0]["exception_id"])
    first, stale = new_session(world["org_id"]), new_session(world["org_id"])
    try:
        first_exc = first.get(ExceptionCase, exc_id)
        stale_exc = stale.get(ExceptionCase, exc_id)
        first_user = first.get(User, world["users"][FIN])
        stale_user = stale.get(User, world["users"][ADMIN])
        decide_exception(first, first_exc, first_user, "finance_reviewer", "reject", "first reviewer")
        first.commit()
        with pytest.raises(HTTPException) as err:
            decide_exception(stale, stale_exc, stale_user, "admin", "approve", "stale reviewer")
        assert err.value.status_code == 409
        stale.rollback()
        assert client.get(f"/api/exceptions/{exc_id}", headers=queue_world["fin"]).json()["decision_note"] == "first reviewer"
    finally:
        first.close()
        stale.close()


def test_po_invoiced_uses_latest_confident_matches_and_excludes_rejected_invoices(client, queue_world, world):
    import uuid
    from decimal import Decimal
    from sqlalchemy import select
    from app.core.db import session_scope
    from app.models import Invoice, ReconciliationRun

    h = queue_world["fin"]
    item = next(i for i in _queue(client, h) if "QUANTITY_EXCEEDS_RECEIVED" in i["finding_types"])
    detail = client.get(f"/api/invoices/{item['invoice_id']}", headers=h).json()
    po_id = detail["purchase_order"]["id"]
    po_url = f"/api/purchase-orders/{po_id}"
    expected = {ln["po_line_id"]: Decimal(next(i["quantity"] for i in detail["lines"] if i["line_no"] == ln["invoice_line_no"]))
                for ln in detail["reconciliation"]["line_matches"] if ln["method"] in ("sku", "description")}
    lines = client.get(po_url, headers=h).json()["lines"]
    assert all(Decimal(ln["invoiced"]) == expected.get(ln["id"], Decimal(0)) for ln in lines)
    with session_scope(world["org_id"]) as db:
        run = db.scalars(select(ReconciliationRun).where(ReconciliationRun.invoice_id == uuid.UUID(item["invoice_id"]))
                         .order_by(ReconciliationRun.created_at.desc())).first()
        original = run.result
        changed = {**original, "line_matches": [{**m, "method": "ambiguous"} for m in run.result["line_matches"]]}
        latest = ReconciliationRun(organization_id=world["org_id"], invoice_id=run.invoice_id, mode=run.mode,
                                   engine_version=run.engine_version, outcome=run.outcome, tolerances=run.tolerances,
                                   result=changed, triggered_by="test")
        db.add(latest)
        db.flush()
        latest_id = latest.id
    assert all(Decimal(ln["invoiced"]) == 0 for ln in client.get(po_url, headers=h).json()["lines"])
    with session_scope(world["org_id"]) as db:
        db.get(ReconciliationRun, latest_id).result = original
    assert any(Decimal(ln["invoiced"]) > 0 for ln in client.get(po_url, headers=h).json()["lines"])
    with session_scope(world["org_id"]) as db:
        db.get(ReconciliationRun, latest_id).result = {**original, "findings": [{"type": "DUPLICATE_INVOICE"}]}
    assert all(Decimal(ln["invoiced"]) == 0 for ln in client.get(po_url, headers=h).json()["lines"])
    with session_scope(world["org_id"]) as db:
        db.get(ReconciliationRun, latest_id).result = original
        inv = db.get(Invoice, uuid.UUID(item["invoice_id"]))
        inv.status = "rejected"
    assert all(Decimal(ln["invoiced"]) == 0 for ln in client.get(po_url, headers=h).json()["lines"])


def test_summary_keeps_currency_totals_separate(client, queue_world, world):
    import uuid
    from decimal import Decimal
    from app.core.db import session_scope
    from app.models import Invoice

    h = queue_world["fin"]
    items = _queue(client, h)
    foreign = items[0]
    with session_scope(world["org_id"]) as db:
        db.get(Invoice, uuid.UUID(foreign["invoice_id"])).currency = "USD"
    summary = client.get("/api/review/summary", headers=h).json()
    base_items = [i for i in items if i["invoice_id"] != foreign["invoice_id"] and i["currency"] == "ILS"]
    assert summary["currency"] == "ILS"
    assert Decimal(summary["value_under_review"]) == sum((Decimal(i["total"]) for i in base_items), Decimal(0))
    assert Decimal(summary["amount_at_risk"]) == sum((Decimal(i["amount_at_risk"]) for i in base_items), Decimal(0))
    usd = next(t for t in summary["totals_by_currency"] if t["currency"] == "USD")
    assert usd["value_under_review"] == foreign["total"]
    assert usd["amount_at_risk"] == foreign["amount_at_risk"]
    with session_scope(world["org_id"]) as db:
        db.get(Invoice, uuid.UUID(foreign["invoice_id"])).currency = None
    unknown = client.get("/api/review/summary", headers=h).json()
    group = next(t for t in unknown["totals_by_currency"] if t["currency"] is None)
    assert group["value_under_review"] == foreign["total"]
    assert unknown["value_under_review"] == summary["value_under_review"]
