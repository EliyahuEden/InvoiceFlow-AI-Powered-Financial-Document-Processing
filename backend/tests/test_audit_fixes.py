"""Regression tests for the P0 findings of docs/audits/FULL_SYSTEM_AUDIT.md (FIN-01..04, SEC-02)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.services.reconciliation import engine as E
from tests.test_reconciliation_engine import ctx, invoice


# ---------------------------------------------------------------- FIN-03: missing line evidence
@pytest.mark.parametrize("missing", [("quantity",), ("unit_price",), ("line_total",), ("quantity", "unit_price", "line_total")])
@pytest.mark.parametrize("mode", ["two_way", "three_way"])
def test_a_line_without_comparable_values_blocks_instead_of_matching(missing, mode):
    c, po = ctx()
    inv = invoice(po)
    inv.lines[0] = replace(inv.lines[0], **{m: None for m in missing})
    r = E.reconcile(inv, c, mode=mode)
    assert r.outcome == "blocked"
    f = next(f for f in r.findings if f.type == "INCOMPLETE_EXTRACTION")
    assert "line 1" in f.params["missing"]


def test_zero_is_a_value_not_a_missing_value():
    c, po = ctx()
    inv = invoice(po)
    inv.lines[0] = replace(inv.lines[0], discount=Decimal(0))
    assert "INCOMPLETE_EXTRACTION" not in {f.type for f in E.reconcile(inv, c).findings}


# ---------------------------------------------------------------- FIN-04: unit-price precision
def test_unit_prices_keep_their_stored_precision():
    from app.api.deps import price

    assert price(Decimal("0.0125")) == "0.0125"
    assert price(Decimal("5.5000")) == "5.50"
    assert price(Decimal("118")) == "118.00"
    assert price(None) is None


@pytest.mark.integration
def test_invoice_api_returns_exact_unit_prices(client, as_user):
    from sqlalchemy import update

    from app.core.db import session_scope
    from app.models import InvoiceLine
    from tests.conftest import upload_invoice

    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    d = client.get(f"/api/invoices/{inv['invoice_id']}", headers=fin).json()
    line_id = d["lines"][0]["id"]
    org_id = client.get("/api/auth/me", headers=fin).json()["organization"]["id"]
    with session_scope(org_id) as s:  # row-level security: act inside the tenant
        s.execute(update(InvoiceLine).where(InvoiceLine.id == line_id).values(unit_price=Decimal("12.3456")))
    d = client.get(f"/api/invoices/{inv['invoice_id']}", headers=fin).json()
    assert next(ln for ln in d["lines"] if ln["id"] == line_id)["unit_price"] == "12.3456"


# ---------------------------------------------------------------- FIN-01: approvals bound to evidence
def _approvals(client, h, inv_id):
    return client.get(f"/api/invoices/{inv_id}", headers=h).json()["approvals"]


def _threshold(client, admin, value):
    org = client.get("/api/org", headers=admin).json()
    r = client.patch("/api/org/settings", headers=admin,
                     json={"approval": {**org["settings"]["approval"], "dual_approval_threshold": value}})
    assert r.status_code == 200, r.text


@pytest.mark.integration
def test_lowering_the_threshold_after_an_approval_requires_the_new_approval_route(client, as_user):
    from tests.conftest import upload_invoice

    proc, fin, admin = (as_user(e) for e in ("procurement@kinneret.example", "finance@kinneret.example", "admin@kinneret.example"))
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")  # 7,633.42: one step under the default 20,000
    iid = inv["invoice_id"]
    assert [a["step"] for a in _approvals(client, fin, iid)] == [1]
    org = client.get("/api/org", headers=admin).json()
    r = client.patch("/api/org/settings", headers=admin,
                     json={"approval": {**org["settings"]["approval"], "dual_approval_threshold": "5000.00"}})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/invoices/{iid}/reconcile", headers=admin).status_code == 200
    steps = _approvals(client, fin, iid)
    assert [(a["step"], a["status"]) for a in steps] == [(1, "pending"), (2, "pending")]


@pytest.mark.integration
def test_an_approval_does_not_survive_changed_evidence(client, as_user):
    from tests.conftest import upload_invoice

    proc, fin, admin = (as_user(e) for e in ("procurement@kinneret.example", "finance@kinneret.example", "admin@kinneret.example"))
    _threshold(client, admin, "1000.00")
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    iid = inv["invoice_id"]
    assert len(_approvals(client, fin, iid)) == 2
    assert client.post(f"/api/invoices/{iid}/approvals", headers=fin, json={"decision": "approve"}).status_code == 200
    # evidence changes: a reviewer corrects the payment terms (any correction re-reconciles)
    r = client.patch(f"/api/invoices/{iid}", headers=fin,
                     json={"header": {"payment_terms": "Net 15"}, "reason": "terms corrected"})
    assert r.status_code == 200, r.text
    steps = _approvals(client, fin, iid)
    assert all(a["status"] == "pending" for a in steps), steps  # the earlier approval no longer counts


@pytest.mark.integration
def test_an_unchanged_rerun_keeps_a_valid_approval(client, as_user):
    from tests.conftest import upload_invoice

    proc, fin, admin = (as_user(e) for e in ("procurement@kinneret.example", "finance@kinneret.example", "admin@kinneret.example"))
    _threshold(client, admin, "1000.00")
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    iid = inv["invoice_id"]
    assert len(_approvals(client, fin, iid)) == 2
    client.post(f"/api/invoices/{iid}/approvals", headers=fin, json={"decision": "approve"})
    assert client.post(f"/api/invoices/{iid}/reconcile", headers=admin).status_code == 200
    assert [a["status"] for a in _approvals(client, fin, iid)] == ["approved", "pending"]


# ---------------------------------------------------------------- FIN-02: approval rows are locked
@pytest.mark.integration
def test_approval_decision_locks_the_invoice_and_its_steps(client, as_user):
    from sqlalchemy import event, select

    from app.core.db import session_scope
    from app.models import Invoice, User
    from app.services import workflow
    from tests.conftest import upload_invoice

    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "01_correct_tavor_he.pdf")
    statements: list[str] = []
    import uuid

    org_id = client.get("/api/auth/me", headers=fin).json()["organization"]["id"]
    with session_scope(org_id) as s:
        user = s.scalars(select(User).where(User.email == "finance@kinneret.example")).one()
        invoice_row = s.get(Invoice, uuid.UUID(inv["invoice_id"]))
        def record(conn, cursor, statement, *args):  # noqa: ANN001, ANN002
            statements.append(statement)

        engine = s.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            workflow.decide_approval(s, invoice_row, user, "finance_reviewer", "approve", None)
        finally:
            event.remove(engine, "before_cursor_execute", record)
    locked = [q for q in statements if "FOR UPDATE" in q.upper()]
    assert any("invoices" in q for q in locked) and any("approvals" in q for q in locked), statements


# ---------------------------------------------------------------- SEC-02: safe production startup
def _prod(**kw):
    from app.core.config import Settings

    base = dict(environment="production", jwt_secret="a" * 48, cookie_secure=True, storage_backend="s3", s3_sse="AES256",
                cors_origins=["https://invoiceflow.example.com"], s3_secret_key="k" * 40,
                database_url="postgresql+psycopg://invoiceflow_app:Q7vT2mW9xL4pR8sZ@db.internal:5432/invoiceflow",
                migration_database_url="postgresql+psycopg://invoiceflow:N3kD8fH2jP6tY1cV@db.internal:5432/invoiceflow")
    base.update(kw)
    return Settings(**base)


def test_a_safe_production_configuration_starts():
    assert _prod().environment == "production"


@pytest.mark.parametrize(("override", "message"), [
    ({"jwt_secret": "dev-only-change-me-0123456789abcdef0123456789"}, "JWT_SECRET"),
    ({"cookie_secure": False}, "COOKIE_SECURE"),
    ({"storage_backend": "local"}, "STORAGE_BACKEND"),
    ({"cors_origins": ["http://localhost:3000"]}, "CORS_ORIGINS"),
    ({"database_url": "postgresql+psycopg://invoiceflow_app:invoiceflow_app_dev@postgres:5432/invoiceflow"}, "DATABASE_URL"),
    ({"migration_database_url": "postgresql+psycopg://invoiceflow:invoiceflow_dev@postgres:5432/invoiceflow"}, "MIGRATION_DATABASE_URL"),
    ({"s3_secret_key": "invoiceflow_dev_secret"}, "S3_SECRET_KEY"),
])
def test_unsafe_production_configurations_refuse_to_start(override, message):
    with pytest.raises(ValueError, match=message):
        _prod(**override)


# ---------------------------------------------------------------- FIN-08: stable line provenance
@pytest.mark.integration
def test_deleting_a_line_keeps_each_surviving_lines_own_source(client, as_user):
    from tests.conftest import upload_invoice

    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    inv = upload_invoice(client, proc, "02_qty_mismatch_hermon_he.pdf")
    iid = inv["invoice_id"]
    before = client.get(f"/api/invoices/{iid}", headers=fin).json()["lines"]
    assert len(before) >= 2 and before[1]["source"].get("bbox")
    survivors = [{**ln, "line_no": n} for n, ln in enumerate(before[1:], start=1)]  # the UI renumbers after a delete
    new_line = {"line_no": len(survivors) + 1, "description": "Delivery fee", "quantity": "1", "unit_price": "10.00",
                "line_total": "10.00"}
    r = client.patch(f"/api/invoices/{iid}", headers=fin, json={"lines": survivors + [new_line], "reason": "drop line 1"})
    assert r.status_code == 200, r.text
    after = client.get(f"/api/invoices/{iid}", headers=fin).json()["lines"]
    assert after[0]["description"] == before[1]["description"]
    assert after[0]["source"]["bbox"] == before[1]["source"]["bbox"]  # not line 1's box
    added = after[-1]
    assert added["source"].get("manual") is True and not added["source"].get("bbox")


# ---------------------------------------------------------------- FIN-06: overrides need a justification
def _blocking_case(client, as_user):
    from tests.conftest import upload_invoice

    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "09_ambiguous_supplier_carmel_he.pdf")
    fin = as_user("finance@kinneret.example")
    d = client.get(f"/api/invoices/{inv['invoice_id']}", headers=fin).json()
    return d["exception"]["id"], d["exception"]["proposed_action"], fin


@pytest.mark.integration
def test_overriding_the_proposed_action_requires_a_justification(client, as_user):
    exc_id, proposed, fin = _blocking_case(client, as_user)
    assert proposed != "accept_variance"
    r = client.post(f"/api/exceptions/{exc_id}/decision", headers=fin,
                    json={"decision": "approve", "action_override": "accept_variance"})
    assert r.status_code == 422 and "justification" in r.json()["detail"].lower()


@pytest.mark.integration
def test_a_justified_override_is_allowed_and_audited(client, as_user):
    exc_id, proposed, fin = _blocking_case(client, as_user)
    r = client.post(f"/api/exceptions/{exc_id}/decision", headers=fin,
                    json={"decision": "approve", "action_override": "accept_variance",
                          "note": "Supplier confirmed by phone; registration number on file"})
    assert r.status_code == 200, r.text
    events = client.get(f"/api/audit?entity_id={exc_id}&action=exception.approve",
                        headers=as_user("admin@kinneret.example")).json()["items"]
    meta = events[0]["meta"]
    assert meta["override"] is True and meta["overridden_action"] == proposed
    assert meta["overridden_findings"] and "AMBIGUOUS_SUPPLIER" in meta["overridden_findings"]


@pytest.mark.integration
def test_requesting_information_cannot_change_the_proposed_action(client, as_user):
    exc_id, proposed, finance = _blocking_case(client, as_user)
    procurement = as_user("procurement@kinneret.example")
    path = f"/api/exceptions/{exc_id}"
    response = client.post(f"{path}/decision", headers=procurement,
                           json={"decision": "request_info", "target": "supplier", "note": "Confirm legal name",
                                 "action_override": "accept_variance"})
    assert response.status_code == 200, response.text
    assert client.get(path, headers=finance).json()["proposed_action"] == proposed


@pytest.mark.integration
def test_approving_the_proposed_action_needs_no_extra_note(client, as_user):
    exc_id, proposed, fin = _blocking_case(client, as_user)
    r = client.post(f"/api/exceptions/{exc_id}/decision", headers=fin, json={"decision": "approve"})
    assert r.status_code == 200, r.text


@pytest.mark.integration
def test_a_dollar_invoice_is_routed_by_its_shekel_value(client, as_user, world):
    """The dual-approval threshold is in shekels: 7,633.42 USD (about 25,400 ILS) needs the second approver."""
    import uuid

    from app.core.db import session_scope
    from app.models import Invoice, Organization
    from app.services.reconciliation.service import ensure_approval_steps
    from tests.conftest import upload_invoice

    proc, fin = as_user("procurement@kinneret.example"), as_user("finance@kinneret.example")
    iid = upload_invoice(client, proc, "01_correct_tavor_he.pdf")["invoice_id"]  # 7,633.42 ILS, reconciled
    assert [a["step"] for a in _approvals(client, fin, iid)] == [1]
    with session_scope(world["org_id"]) as session:
        inv = session.get(Invoice, uuid.UUID(iid))
        assert inv.status == "reconciled"
        inv.currency = "USD"
        ensure_approval_steps(session, session.get(Organization, world["org_id"]), inv)
    assert [a["step"] for a in _approvals(client, fin, iid) if a["status"] == "pending"] == [1, 2]
    route = client.get(f"/api/audit?entity_id={iid}&action=approval.route", headers=fin).json()["items"]
    assert route and route[0]["meta"]["currency"] == "USD" and route[0]["meta"]["steps"] == 2
    assert route[0]["meta"]["total_base"] == "25419.29" and route[0]["meta"]["rate"] == "3.33"


@pytest.mark.integration
def test_procurement_decides_cases_but_never_approves_payment(client, as_user):
    """Owner's decision 2026-11-23: procurement managers decide and override cases, with the same justification rule
    as finance. Payment approval stays with finance."""
    from tests.conftest import upload_invoice

    exc_id, proposed, fin = _blocking_case(client, as_user)
    proc = as_user("procurement@kinneret.example")
    url = f"/api/exceptions/{exc_id}/decision"
    assert client.post(url, headers=proc, json={"decision": "approve", "action_override": "accept_variance"}).status_code == 422
    r = client.post(url, headers=proc, json={"decision": "approve", "action_override": "accept_variance",
                                             "note": "Same supplier, confirmed by phone"})
    assert r.status_code == 200, r.text
    rows = client.get(f"/api/audit?entity_id={exc_id}&page_size=50", headers=fin).json()["items"]
    assert any((r.get("meta") or {}).get("override") is True for r in rows)
    me = client.get("/api/auth/me", headers=proc).json()
    assert "exception:decide" in me["permissions"] and "approval:decide" not in me["permissions"]
    other = upload_invoice(client, fin, "01_correct_tavor_he.pdf")                # uploaded by finance, reconciled
    assert client.post(f"/api/invoices/{other['invoice_id']}/approvals", headers=proc, json={"decision": "approve"}).status_code == 403


def test_audit_filters_by_several_action_prefixes(client, as_user):
    """The audit page's event-type filter asks for a group of prefixes at once; sign-ins stay out of it."""
    from tests.conftest import upload_invoice

    fin = as_user("finance@kinneret.example")
    upload_invoice(client, fin, "02_qty_mismatch_hermon_he.pdf")
    rows = client.get("/api/audit?action=invoice.,exception.&page_size=100", headers=fin).json()["items"]
    assert rows and all(r["action"].startswith(("invoice.", "exception.")) for r in rows)
    assert {r["action"].split(".")[0] for r in rows} >= {"invoice"}
    single = client.get("/api/audit?action=invoice.uploaded", headers=fin).json()["items"]
    assert single and {r["action"] for r in single} == {"invoice.uploaded"}
