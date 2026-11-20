"""Authentication, RBAC, tenant isolation (application layer + PostgreSQL RLS), audit immutability."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import get_settings
from app.core.db import new_session, session_scope
from app.models import AuditLog, Invoice, Supplier
from tests.conftest import upload_invoice

pytestmark = pytest.mark.integration


def test_login_rejects_bad_credentials(client):
    r = client.post("/api/auth/login", json={"email": "finance@kinneret.example", "password": "wrong"})
    assert r.status_code == 401
    assert client.get("/api/invoices").status_code == 401


def test_me_returns_role_permissions(client, as_user):
    me = client.get("/api/auth/me", headers=as_user("viewer@kinneret.example")).json()
    assert me["role"] == "read_only" and "invoice:upload" not in me["permissions"] and me["ai_mode"] == "offline-deterministic"


@pytest.mark.parametrize("email,status", [("viewer@kinneret.example", 403), ("procurement@kinneret.example", 202)])
def test_upload_requires_permission(client, as_user, email, status):
    pdf = (__import__("tests.conftest", fromlist=["DATA"]).DATA / "invoices" / "01_correct_tavor_he.pdf").read_bytes()
    r = client.post("/api/invoices/upload", headers=as_user(email), files={"file": ("a.pdf", pdf, "application/pdf")})
    assert r.status_code == status


def test_cookie_session_requires_csrf_header(client):
    from app.demo.spec import DEMO_PASSWORD

    client.post("/api/auth/login", json={"email": "finance@kinneret.example", "password": DEMO_PASSWORD})
    assert client.get("/api/invoices").status_code == 200  # cookie works for reads
    r = client.post("/api/invoices/00000000-0000-0000-0000-000000000000/reconcile")
    assert r.status_code == 403 and "CSRF" in r.text
    r = client.post("/api/invoices/00000000-0000-0000-0000-000000000000/reconcile", headers={"X-Requested-With": "invoiceflow"})
    assert r.status_code == 404


def test_role_change_takes_effect_immediately(client, as_user, world):
    h = as_user("procurement@kinneret.example")
    assert client.get("/api/audit", headers=h).status_code == 200
    with session_scope() as s:
        from app.models import Membership, Role

        m = s.scalars(select(Membership).where(Membership.user_id == world["users"]["procurement@kinneret.example"])).first()
        m.role = Role.READ_ONLY
    assert client.get("/api/audit", headers=h).status_code == 403  # same token, role re-read from DB


def test_cross_tenant_access_returns_404(client, as_user, world):
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    other = as_user("admin@yarden.example")
    assert client.get(f"/api/invoices/{inv['invoice_id']}", headers=other).status_code == 404
    assert client.get("/api/invoices", headers=other).json()["total"] == 0
    names = [s["name"] for s in client.get("/api/suppliers", headers=other).json()["items"]]
    assert len(names) == 1  # only Yarden's own copy of the supplier
    assert client.post(f"/api/invoices/{inv['invoice_id']}/reconcile", headers=other).status_code == 404


def test_row_level_security_blocks_even_without_app_filters(client, as_user, world):
    upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    # A query with NO organization filter, in a session bound to the other tenant, sees nothing.
    s = new_session(world["other_org_id"])
    try:
        assert s.scalars(select(Invoice)).all() == []
        assert {x.organization_id for x in s.scalars(select(Supplier))} == {world["other_org_id"]}
        # Writing a row for another tenant violates the RLS WITH CHECK policy.
        s.add(Supplier(organization_id=world["org_id"], name="Injected", tax_id="999999999"))
        with pytest.raises((ProgrammingError, DBAPIError)):
            s.flush()
    finally:
        s.rollback()
        s.close()
    s = new_session()  # no tenant bound at all -> no tenant rows
    try:
        assert s.scalars(select(Invoice)).all() == []
    finally:
        s.close()


def test_audit_log_is_append_only_and_hash_chained(client, as_user, world):
    upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    h = as_user("finance@kinneret.example")
    assert client.get("/api/audit/verify", headers=h).json()["valid"] is True
    s = new_session(world["org_id"])
    try:  # the application role cannot modify history
        with pytest.raises((ProgrammingError, DBAPIError)):
            s.execute(text("UPDATE audit_logs SET action = 'tampered'"))
            s.flush()
    finally:
        s.rollback()
        s.close()
    # A superuser tampering with a row is detected by the hash chain.
    eng = create_engine(get_settings().migration_database_url)
    with eng.begin() as conn:
        conn.execute(text("UPDATE audit_logs SET after = '{\"status\": \"approved\"}' "
                          "WHERE id = (SELECT id FROM audit_logs WHERE organization_id = :o ORDER BY created_at LIMIT 1 OFFSET 2)"),
                     {"o": str(world["org_id"])})
    eng.dispose()
    v = client.get("/api/audit/verify", headers=h).json()
    assert v["valid"] is False and v["broken_at"]


def test_documents_are_tenant_scoped(client, as_user):
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    detail = client.get(f"/api/invoices/{inv['invoice_id']}", headers=as_user("finance@kinneret.example")).json()
    doc_id = detail["document"]["id"]
    assert client.get(f"/api/documents/{doc_id}/file", headers=as_user("viewer@kinneret.example")).status_code == 200
    assert client.get(f"/api/documents/{doc_id}/file", headers=as_user("admin@yarden.example")).status_code == 404
    r = client.get(f"/api/documents/{doc_id}/pages/1/image", headers=as_user("viewer@kinneret.example"))
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_settings_require_admin_and_validate(client, as_user):
    assert client.patch("/api/org/settings", headers=as_user("finance@kinneret.example"),
                        json={"tolerances": {"price_pct": "2"}}).status_code == 403
    admin = as_user("admin@kinneret.example")
    assert client.patch("/api/org/settings", headers=admin, json={"tolerances": {"price_pct": "abc"}}).status_code == 422
    assert client.patch("/api/org/settings", headers=admin, json={"tolerances": {"nope": "1"}}).status_code == 422
    r = client.patch("/api/org/settings", headers=admin, json={"tolerances": {"price_pct": "2.5"}})
    assert r.status_code == 200 and r.json()["settings"]["tolerances"]["price_pct"] == "2.5"


def test_health_endpoints(client):
    assert client.get("/health/live").json()["status"] == "ok"
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"


def test_random_uuid_is_not_found(client, as_user):
    assert client.get(f"/api/invoices/{uuid.uuid4()}", headers=as_user("finance@kinneret.example")).status_code == 404
    with session_scope() as s:
        assert s.scalars(select(AuditLog)).all() == []  # unbound session: RLS hides every tenant's audit rows
