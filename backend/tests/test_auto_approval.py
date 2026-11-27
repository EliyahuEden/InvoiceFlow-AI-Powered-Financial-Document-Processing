"""Configurable auto-approval: the policy API, the decision hook, the cases where it must NOT fire, tenant isolation
(row-level security) and the dashboard KPI. Auto-approval never approves or pays: people still approve the payment."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.db import new_session, session_scope
from app.models import RLS_TABLES, AutoApprovalPolicy, Invoice, Supplier
from app.services import auto_approval
from tests.conftest import upload_invoice

pytestmark = pytest.mark.integration

POLICY_URL = "/api/org/auto-approval"
CLEAN_TOTAL = "7633.42"  # 01_correct_tavor_he.pdf


def _policy(client, headers, *, enabled=True, max_amount="10000", scope="all", suppliers=()):
    r = client.put(POLICY_URL, headers=headers, json={"enabled": enabled, "max_amount": max_amount,
                                                      "supplier_scope": scope, "supplier_ids": [str(s) for s in suppliers]})
    assert r.status_code == 200, r.text
    return r.json()


def _detail(client, headers, invoice_id):
    return client.get(f"/api/invoices/{invoice_id}", headers=headers).json()


def _audit(client, headers, invoice_id, action):
    rows = client.get(f"/api/audit?entity_id={invoice_id}&action={action}", headers=headers).json()["items"]
    return rows


@pytest.fixture()
def users(as_user):
    return {name: as_user(f"{name}@kinneret.example") for name in ("admin", "procurement", "finance", "viewer")}


# ---------------------------------------------------------------- the policy API
def test_without_a_policy_nothing_is_auto_approved(client, users):
    view = client.get(POLICY_URL, headers=users["finance"]).json()
    assert view["policy"]["enabled"] is False and view["policy"]["version"] == 0
    assert view["minutes_per_invoice"] == auto_approval.MINUTES_SAVED_PER_INVOICE
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["status"] == "reconciled" and d["auto_approval"] is None and d["auto_approved"] is False
    assert _audit(client, users["admin"], inv["invoice_id"], "invoice.auto_approv") == []


def test_policy_is_admin_only_validated_and_audited(client, users, world):
    body = {"enabled": True, "max_amount": "5000", "supplier_scope": "all", "supplier_ids": []}
    for role in ("finance", "procurement", "viewer"):
        assert client.put(POLICY_URL, headers=users[role], json=body).status_code == 403
    assert client.get(POLICY_URL, headers=users["viewer"]).status_code == 200  # everyone may read it
    admin = users["admin"]
    assert client.put(POLICY_URL, headers=admin, json={**body, "max_amount": "-1"}).status_code == 422
    assert client.put(POLICY_URL, headers=admin, json={**body, "max_amount": "abc"}).status_code == 422
    assert client.put(POLICY_URL, headers=admin, json={**body, "max_amount": "1.005"}).status_code == 422
    assert client.put(POLICY_URL, headers=admin, json={**body, "supplier_scope": "some"}).status_code == 422
    # "selected" with nobody chosen would silently match nothing: refuse to turn it on
    assert client.put(POLICY_URL, headers=admin, json={**body, "supplier_scope": "selected"}).status_code == 422
    # a supplier of another business cannot be listed
    foreign = next(iter(world["other_suppliers"].values()))
    assert client.put(POLICY_URL, headers=admin, json={**body, "supplier_scope": "selected",
                                                      "supplier_ids": [str(foreign)]}).status_code == 422
    assert client.put(POLICY_URL, headers=admin, json={**body, "supplier_scope": "selected",
                                                      "supplier_ids": [str(uuid.uuid4())]}).status_code == 422
    first = _policy(client, admin, max_amount="5000")["policy"]
    assert first["version"] == 1 and first["max_amount"] == "5000.00" and first["enabled"] is True
    second = _policy(client, admin, max_amount="6000.50", scope="selected", suppliers=[world["suppliers"]["tavor"]])["policy"]
    assert second["version"] == 2 and second["supplier_ids"] == [str(world["suppliers"]["tavor"])]
    rows = client.get("/api/audit?action=org.auto_approval_policy_updated", headers=admin).json()["items"]
    assert len(rows) == 2
    newest = rows[0]
    assert newest["actor_label"] == "admin@kinneret.example" and newest["meta"]["version"] == 2
    assert newest["before"]["max_amount"] == "5000.00" and newest["after"]["max_amount"] == "6000.50"
    assert client.get("/api/audit/verify", headers=admin).json()["valid"] is True


# ---------------------------------------------------------------- the decision
def test_clean_invoice_is_auto_approved_but_payment_still_needs_people(client, users, world):
    policy = _policy(client, users["admin"], max_amount="10000")["policy"]
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    path = f"/api/invoices/{inv['invoice_id']}"
    d = _detail(client, users["finance"], inv["invoice_id"])
    # it skipped review and is ready for the normal payment approval ...
    assert d["status"] == "reconciled" and d["exception"] is None and d["auto_approved"] is True
    # ... which is still there, pending, for people to decide
    assert [(a["step"], a["status"]) for a in d["approvals"]] == [(1, "pending")]
    assert d["payment"]["status"] == "unscheduled"
    assert client.post(f"{path}/payment", headers=users["finance"],
                       json={"action": "schedule", "date": (datetime.now(UTC) + timedelta(days=2)).date().isoformat()}
                       ).status_code == 409  # nothing can be paid before a person approves
    snap = d["auto_approval"]
    assert snap["policy_version"] == policy["version"] == 1 and snap["policy_id"]
    assert snap["max_amount"] == "10000.00" and snap["total_base"] == CLEAN_TOTAL and snap["findings"] == 0
    assert snap["mode"] == "three_way" and snap["supplier_id"] == str(world["suppliers"]["tavor"])
    # the audit entry records the policy and the values it used
    [entry] = _audit(client, users["admin"], inv["invoice_id"], "invoice.auto_approved")
    assert entry["actor_type"] == "system" and entry["actor_label"] == "auto-approval-policy"
    assert entry["after"]["status"] == "reconciled" and entry["after"]["auto_approved"] is True
    assert entry["after"]["policy"]["policy_version"] == 1 and entry["after"]["policy"]["max_amount"] == "10000.00"
    assert entry["after"]["policy"]["total_base"] == CLEAN_TOTAL
    assert entry["meta"]["policy_version"] == 1 and "nothing is paid" in entry["meta"]["next_step"]
    # a person still has to approve (and not the uploader)
    assert client.post(f"{path}/approvals", headers=users["procurement"], json={"decision": "approve"}).status_code == 403
    r = client.post(f"{path}/approvals", headers=users["finance"], json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["invoice_status"] == "approved"
    assert client.get("/api/audit/verify", headers=users["admin"]).json()["valid"] is True


def test_dual_approval_above_the_threshold_is_untouched(client, users):
    assert client.patch("/api/org/settings", headers=users["admin"],
                        json={"approval": {"dual_approval_threshold": "1000"}}).status_code == 200
    _policy(client, users["admin"], max_amount="10000")
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["auto_approved"] is True and d["status"] == "reconciled"
    assert [(a["step"], a["required_role"], a["status"]) for a in d["approvals"]] == \
        [(1, "finance_reviewer", "pending"), (2, "admin", "pending")]
    path = f"/api/invoices/{inv['invoice_id']}/approvals"
    assert client.post(path, headers=users["finance"], json={"decision": "approve"}).json()["invoice_status"] == "reconciled"
    assert client.post(path, headers=users["finance"], json={"decision": "approve"}).status_code == 403  # a second person
    assert client.post(path, headers=users["admin"], json={"decision": "approve"}).json()["invoice_status"] == "approved"


def test_amount_ceiling_is_inclusive(client, users):
    _policy(client, users["admin"], max_amount="7633.41")
    over = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    assert _detail(client, users["finance"], over["invoice_id"])["auto_approval"] is None
    _policy(client, users["admin"], max_amount=CLEAN_TOTAL)  # exactly the total: allowed
    client.post(f"/api/invoices/{over['invoice_id']}/reconcile", headers=users["procurement"])
    assert _detail(client, users["finance"], over["invoice_id"])["auto_approved"] is True
    _policy(client, users["admin"], max_amount="0")  # a zero ceiling allows nothing: the marker is withdrawn
    client.post(f"/api/invoices/{over['invoice_id']}/reconcile", headers=users["procurement"])
    d = _detail(client, users["finance"], over["invoice_id"])
    assert d["auto_approval"] is None and d["status"] == "reconciled"
    [revoked] = _audit(client, users["admin"], over["invoice_id"], "invoice.auto_approval_revoked")
    assert revoked["after"]["reasons"] == ["over_max_amount"]


def test_only_the_listed_suppliers_qualify(client, users, world):
    other = world["suppliers"]["hermon"]
    _policy(client, users["admin"], scope="selected", suppliers=[other])
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approval"] is None
    _policy(client, users["admin"], scope="selected", suppliers=[other, world["suppliers"]["tavor"]])
    client.post(f"/api/invoices/{inv['invoice_id']}/reconcile", headers=users["procurement"])
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approved"] is True


def test_a_disabled_policy_approves_nothing(client, users):
    _policy(client, users["admin"], enabled=False)
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approval"] is None


# ---------------------------------------------------------------- the cases where it must NOT fire
@pytest.mark.parametrize("name,expected", [
    ("02_qty_mismatch_hermon_he.pdf", "exception"),      # a critical finding
    ("03_price_mismatch_bluewave_en.pdf", "exception"),
    ("05_missing_po_arava_mixed.pdf", "exception"),
    ("08_prompt_injection_bluewave_en.pdf", "exception"),  # embedded instructions never help an invoice
    ("10_missing_receipt_bluewave_en.pdf", "exception"),   # no goods receipt: not a three-way match
])
def test_invoices_with_findings_are_never_auto_approved(client, users, name, expected):
    _policy(client, users["admin"], max_amount="1000000000")  # as permissive as the policy can be
    inv = upload_invoice(client, users["procurement"], name)
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["status"] == expected and d["auto_approval"] is None and d["auto_approved"] is False
    assert _audit(client, users["admin"], inv["invoice_id"], "invoice.auto_approv") == []


def test_a_two_way_run_is_not_a_three_way_match(client, users):
    _policy(client, users["admin"])
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    path = f"/api/invoices/{inv['invoice_id']}/reconcile"
    assert client.post(f"{path}?mode=two_way", headers=users["procurement"]).status_code == 200
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["status"] == "reconciled" and d["auto_approval"] is None  # reconciled, but only a person may release it
    assert _audit(client, users["admin"], inv["invoice_id"], "invoice.auto_approval_revoked")[0]["after"]["reasons"] == \
        ["not_three_way"]
    assert client.post(path, headers=users["procurement"]).status_code == 200  # a three-way run qualifies again
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approved"] is True


def test_a_person_editing_the_invoice_ends_touchless_processing(client, users):
    _policy(client, users["admin"])
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["auto_approved"] is True
    r = client.patch(f"/api/invoices/{inv['invoice_id']}", headers=users["finance"],
                     json={"header": {"payment_terms": "net 30"}, "revision": d["revision"], "reason": "typo"})
    assert r.status_code == 200, r.text
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["status"] == "reconciled" and d["auto_approval"] is None
    assert _audit(client, users["admin"], inv["invoice_id"], "invoice.auto_approval_revoked")[0]["after"]["reasons"] == \
        ["human_edited"]


def test_bank_change_and_payment_hold_block_auto_approval(client, users, world):
    _policy(client, users["admin"])
    tavor = world["suppliers"]["tavor"]
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")
    rerun = f"/api/invoices/{inv['invoice_id']}/reconcile"
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approved"] is True
    # a bank change awaiting review
    path = f"/api/suppliers/{tavor}/bank-account"
    proposed = client.post(path, headers=users["admin"], json={"bank_code": "10", "branch_code": "800", "account_number": "987654321"})
    assert proposed.status_code == 201, proposed.text
    client.post(rerun, headers=users["procurement"])
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approval"] is None
    assert _audit(client, users["admin"], inv["invoice_id"], "invoice.auto_approval_revoked")[0]["after"]["reasons"] == \
        ["bank_change_pending"]
    # confirmed: the payment hold now runs for bank_change_hold_days
    change_id = proposed.json()["pending"]["id"]
    done = client.post(f"{path}/{change_id}/review", headers=users["finance"], json={"decision": "confirm"})
    assert done.status_code == 200 and done.json()["hold_until"]
    client.post(rerun, headers=users["procurement"])
    d = _detail(client, users["finance"], inv["invoice_id"])
    assert d["auto_approval"] is None and d["status"] == "reconciled"
    # while the hold runs, the supplier's invoices do not qualify (also checked directly: the only reason is the hold)
    with session_scope(world["org_id"]) as s:
        assert s.get(Supplier, tavor).bank_hold_until > datetime.now(UTC)
    assert _evaluate(world, inv["invoice_id"]).reasons == ["payment_hold_active"]
    # the hold runs out: it qualifies again (a hold in the past is no hold)
    with session_scope(world["org_id"]) as s:
        s.get(Supplier, tavor).bank_hold_until = datetime.now(UTC) - timedelta(minutes=1)
    client.post(rerun, headers=users["procurement"])
    assert _detail(client, users["finance"], inv["invoice_id"])["auto_approved"] is True


def _evaluate(world, invoice_id, *, patch=None, policy="default", **kw):
    """Run the pure decision on a (possibly edited) copy of the invoice. Nothing is saved: the session is rolled back."""
    from app.models import Organization

    kw.setdefault("mode", "three_way")
    kw.setdefault("finding_types", [])
    if policy == "default":
        policy = AutoApprovalPolicy(id=uuid.uuid4(), organization_id=world["org_id"], enabled=True,
                                    max_amount=Decimal("10000"), supplier_scope="all", supplier_ids=[], version=3)
    s = new_session(world["org_id"])
    try:
        inv = s.get(Invoice, uuid.UUID(invoice_id))
        if patch:
            patch(inv, s)
            s.flush()  # the decision re-reads the supplier row
        return auto_approval.evaluate(s, s.get(Organization, world["org_id"]), inv, policy, **kw)
    finally:
        s.rollback()
        s.close()


def test_decision_reasons(client, users, world):
    inv = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")["invoice_id"]
    ok = _evaluate(world, inv)
    assert ok.approved and ok.reasons == [] and ok.values["policy_version"] == 3 and ok.values["total_base"] == CLEAN_TOTAL
    assert _evaluate(world, inv, policy=None).reasons == ["policy_disabled"]
    # even an informational finding is a finding
    assert _evaluate(world, inv, finding_types=["UNBILLED_PO_LINES"]).reasons == ["has_findings"]
    assert _evaluate(world, inv, mode="two_way").reasons == ["not_three_way"]

    def edit(**fields):
        return lambda i, s: [setattr(i, k, v) for k, v in fields.items()]
    assert _evaluate(world, inv, patch=edit(status="exception")).reasons == ["not_reconciled"]
    assert _evaluate(world, inv, patch=edit(archived_at=datetime.now(UTC))).reasons == ["archived"]
    assert _evaluate(world, inv, patch=edit(missing_fields=["due_date"])).reasons == ["extraction_warnings"]
    assert _evaluate(world, inv, patch=edit(validation_warnings=[{"code": "X", "severity": "warning"}])).reasons == \
        ["extraction_warnings"]
    assert _evaluate(world, inv, patch=edit(validation_warnings=[{"code": "DUPLICATE_PAGES", "severity": "info"}])).approved
    assert _evaluate(world, inv, patch=edit(supplier_id=None)).reasons == ["no_supplier"]
    assert _evaluate(world, inv, patch=edit(total=Decimal("0"))).reasons == ["amount_not_positive"]
    assert _evaluate(world, inv, patch=edit(total=Decimal("-5"))).reasons == ["amount_not_positive"]
    assert _evaluate(world, inv, patch=edit(total=None)).reasons == ["amount_unknown"]
    assert _evaluate(world, inv, patch=edit(total=Decimal("10000.01"))).reasons == ["over_max_amount"]
    # a foreign amount that cannot be converted to shekels is never approved on a guess
    assert _evaluate(world, inv, patch=edit(currency="XXX")).reasons == ["amount_unknown"]
    assert _evaluate(world, inv, patch=edit(currency="USD"), rates=None).reasons == ["amount_unknown"]
    assert _evaluate(world, inv, patch=lambda i, s: setattr(s.get(Supplier, i.supplier_id), "status", "blocked")
                     ).reasons == ["supplier_blocked"]
    assert _evaluate(world, inv, patch=lambda i, s: setattr(s.get(Supplier, i.supplier_id), "pending_bank_account", {"id": "x"})
                     ).reasons == ["bank_change_pending"]
    assert _evaluate(world, inv, patch=lambda i, s: setattr(s.get(Supplier, i.supplier_id), "bank_hold_until",
                                                            datetime.now(UTC) + timedelta(days=1))).reasons == ["payment_hold_active"]
    narrow = AutoApprovalPolicy(id=uuid.uuid4(), organization_id=world["org_id"], enabled=True, max_amount=Decimal("10000"),
                                supplier_scope="selected", supplier_ids=[str(uuid.uuid4())], version=1)
    assert _evaluate(world, inv, policy=narrow).reasons == ["supplier_not_allowed"]
    # every reason is reported, not only the first
    assert _evaluate(world, inv, policy=narrow, mode="two_way", finding_types=["PRICE_MISMATCH"]).reasons == \
        ["not_three_way", "has_findings", "supplier_not_allowed"]


# ---------------------------------------------------------------- tenant isolation (row-level security)
def test_auto_approval_policies_are_protected_by_row_level_security(client, users, world):
    assert "auto_approval_policies" in RLS_TABLES
    _policy(client, users["admin"], max_amount="1234")
    with session_scope() as s:  # the owner role reads the catalogue
        flags = s.execute(text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'auto_approval_policies'")).one()
        assert tuple(flags) == (True, True)
        assert s.scalar(text("SELECT count(*) FROM pg_policies WHERE tablename = 'auto_approval_policies' "
                             "AND policyname = 'tenant_isolation'")) == 1
    own = new_session(world["org_id"])
    try:
        assert [p.max_amount for p in own.scalars(select(AutoApprovalPolicy))] == [Decimal("1234.0000")]
    finally:
        own.close()
    other = new_session(world["other_org_id"])
    try:  # a query with no organization filter in another tenant's session sees nothing
        assert other.scalars(select(AutoApprovalPolicy)).all() == []
        # writing a row for another tenant violates the WITH CHECK policy
        other.add(AutoApprovalPolicy(organization_id=world["org_id"], enabled=True, max_amount=Decimal("1"),
                                     supplier_scope="all", supplier_ids=[]))
        with pytest.raises((ProgrammingError, DBAPIError)):
            other.flush()
    finally:
        other.rollback()
        other.close()
    unbound = new_session()
    try:
        assert unbound.scalars(select(AutoApprovalPolicy)).all() == []
        # and another tenant's policy cannot be changed or removed
        assert unbound.execute(text("UPDATE auto_approval_policies SET enabled = false")).rowcount == 0
        assert unbound.execute(text("DELETE FROM auto_approval_policies")).rowcount == 0
    finally:
        unbound.rollback()
        unbound.close()


def test_one_business_policy_never_applies_to_another(client, users, as_user, world):
    _policy(client, users["admin"])  # Kinneret allows everything
    other_admin = as_user("admin@yarden.example")
    assert client.get(POLICY_URL, headers=other_admin).json()["policy"]["enabled"] is False
    # and a policy of another business is never visible through this one's API
    _policy(client, other_admin, max_amount="1")
    assert client.get(POLICY_URL, headers=users["admin"]).json()["policy"]["max_amount"] == "10000.00"


def test_one_policy_row_per_organization(client, users, world):
    _policy(client, users["admin"])
    _policy(client, users["admin"], max_amount="20")
    eng_session = new_session(world["org_id"])
    try:
        assert len(eng_session.scalars(select(AutoApprovalPolicy)).all()) == 1
        eng_session.add(AutoApprovalPolicy(organization_id=world["org_id"], enabled=False, max_amount=Decimal("1"),
                                           supplier_scope="all", supplier_ids=[]))
        with pytest.raises(DBAPIError):
            eng_session.flush()
    finally:
        eng_session.rollback()
        eng_session.close()


# ---------------------------------------------------------------- the dashboard KPI
def test_touchless_rate_and_estimated_hours_saved(client, users):
    kpi = client.get("/api/dashboard", headers=users["finance"]).json()["kpis"]["automation"]
    assert kpi["touchless_rate"] is None and kpi["auto_approved"] == 0 and kpi["hours_saved"] == 0
    assert kpi["minutes_per_invoice"] == 6 and kpi["window_days"] == 30
    _policy(client, users["admin"])
    upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")           # clean: auto-approved
    upload_invoice(client, users["procurement"], "02_qty_mismatch_hermon_he.pdf")     # exception: a person decides
    kpi = client.get("/api/dashboard", headers=users["finance"]).json()["kpis"]["automation"]
    assert (kpi["processed"], kpi["auto_approved"], kpi["touchless_rate"]) == (2, 1, 0.5)
    assert kpi["hours_saved"] == 0.1  # 1 invoice x 6 minutes
    assert client.get("/api/dashboard", headers=users["viewer"]).json()["kpis"]["automation"]["auto_approved"] == 1


def test_kpi_counts_only_the_current_window_and_the_current_marker(client, users, world):
    from datetime import timedelta as td

    _policy(client, users["admin"])
    old = upload_invoice(client, users["procurement"], "01_correct_tavor_he.pdf")["invoice_id"]
    with session_scope(world["org_id"]) as s:
        s.get(Invoice, uuid.UUID(old)).created_at = datetime.now(UTC) - td(days=auto_approval.KPI_WINDOW_DAYS + 5)
    kpi = client.get("/api/dashboard", headers=users["finance"]).json()["kpis"]["automation"]
    assert kpi["processed"] == 0 and kpi["auto_approved"] == 0 and kpi["touchless_rate"] is None
    with session_scope(world["org_id"]) as s:
        s.get(Invoice, uuid.UUID(old)).created_at = datetime.now(UTC)
    assert client.get("/api/dashboard", headers=users["finance"]).json()["kpis"]["automation"]["auto_approved"] == 1
    _policy(client, users["admin"], max_amount="0")  # withdrawn on the next run: no longer counted
    client.post(f"/api/invoices/{old}/reconcile", headers=users["procurement"])
    assert client.get("/api/dashboard", headers=users["finance"]).json()["kpis"]["automation"]["auto_approved"] == 0
