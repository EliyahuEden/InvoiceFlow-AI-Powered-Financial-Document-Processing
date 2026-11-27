"""Organization API keys: shown once, stored hashed, scoped, revocable, tenant-isolated."""
import hashlib

import pytest
from sqlalchemy import create_engine, select, text

from app.core.config import get_settings
from app.core.db import new_session, session_scope
from app.models import ApiKey, AuditLog, Document
from app.services import api_keys
from app.worker import drain
from tests.conftest import DATA, upload_invoice

ADMIN = "admin@kinneret.example"


def make_key(client, as_user, scope="read", name="Integration", email=ADMIN) -> tuple[dict, dict]:
    r = client.post("/api/org/api-keys", headers=as_user(email), json={"name": name, "scope": scope})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["key"], {"Authorization": f"Bearer {body['secret']}"}


def test_only_administrators_manage_keys(client, as_user):
    for email in ("procurement@kinneret.example", "finance@kinneret.example", "viewer@kinneret.example"):
        h = as_user(email)
        assert client.post("/api/org/api-keys", headers=h, json={"name": "x", "scope": "read"}).status_code == 403
        assert client.get("/api/org/api-keys", headers=h).status_code == 403
    client.cookies.clear()  # logging in sets a session cookie on the test client
    assert client.get("/api/org/api-keys").status_code == 401


def test_creation_is_validated(client, as_user):
    h = as_user(ADMIN)
    for body in ({"name": "", "scope": "read"}, {"name": "   ", "scope": "read"}, {"name": "x", "scope": "admin"},
                 {"name": "x", "scope": "write"}, {"name": "x"}, {"scope": "read"}):
        assert client.post("/api/org/api-keys", headers=h, json=body).status_code == 422, body


def test_the_secret_is_shown_once_and_stored_only_as_a_hash(client, as_user, world):
    h = as_user(ADMIN)
    r = client.post("/api/org/api-keys", headers=h, json={"name": "ERP sync", "scope": "read_write"})
    assert r.headers["cache-control"] == "no-store"
    secret = r.json()["secret"]
    assert secret.startswith("ifk_") and len(secret) >= 40
    listing = client.get("/api/org/api-keys", headers=h)
    assert secret not in listing.text and "key_hash" not in listing.text
    [row] = listing.json()["items"]
    assert row["name"] == "ERP sync" and row["scope"] == "read_write" and row["prefix"] == secret[:12]
    assert row["last_used_at"] is None and row["revoked_at"] is None

    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.connect() as conn:
            stored = conn.execute(text("SELECT key_hash, prefix FROM api_keys")).one()
            dump = " ".join(str(v) for t in ("api_keys", "audit_logs") for r_ in conn.execute(text(f"SELECT * FROM {t}")) for v in r_)
    finally:
        eng.dispose()
    assert stored.key_hash == hashlib.sha256(secret.encode()).hexdigest()
    assert secret not in dump and secret[12:] not in dump  # nowhere in the database, audit trail included


def test_a_read_key_reads_its_own_data_and_nothing_else(client, as_user, world):
    inv = upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    _key, key = make_key(client, as_user, "read")
    r = client.get("/api/invoices", headers=key)
    assert r.status_code == 200 and r.json()["total"] == 1
    assert client.get(f"/api/invoices/{inv['invoice_id']}", headers=key).status_code == 200
    for path in ("/api/exceptions", "/api/suppliers", "/api/purchase-orders"):
        assert client.get(path, headers=key).status_code == 200, path

    f = DATA / "invoices" / "01_correct_tavor_he.pdf"
    assert client.post("/api/invoices/upload", headers=key, files={"file": (f.name, f.read_bytes(), "application/pdf")}).status_code == 403
    assert client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=key, json={"decision": "approve"}).status_code == 403
    assert client.patch(f"/api/invoices/{inv['invoice_id']}", headers=key, json={"header": {}}).status_code == 403
    assert client.post("/api/suppliers", headers=key, json={"name": "x", "tax_id": "1"}).status_code == 403


@pytest.mark.parametrize("scope", ["read", "read_write"])
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/org"), ("GET", "/api/auth/me"), ("GET", "/api/org/members"), ("GET", "/api/org/api-keys"),
    ("POST", "/api/org/api-keys"), ("GET", "/api/org/webhooks"), ("POST", "/api/org/webhooks"),
    ("PATCH", "/api/org/settings"), ("POST", "/api/org/members"), ("GET", "/api/org/archive.zip"),
    ("POST", "/api/org/erase"), ("GET", "/api/audit"), ("GET", "/api/dashboard"), ("POST", "/api/knowledge/ask"),
    ("POST", "/api/copilot/ask"), ("GET", "/api/export/invoices.csv"), ("POST", "/api/auth/logout-all"),
])
def test_keys_never_reach_administration_or_the_rest_of_the_api(client, as_user, scope, method, path):
    _k, key = make_key(client, as_user, scope)
    r = client.request(method, path, headers=key, json={} if method != "GET" else None)
    assert r.status_code == 403, (scope, method, path, r.status_code, r.text)


def test_a_read_write_key_uploads_invoices_without_a_person_behind_it(client, as_user, world):
    k, key = make_key(client, as_user, "read_write", name="Scanner")
    f = DATA / "invoices" / "01_correct_tavor_he.pdf"
    r = client.post("/api/invoices/upload", headers=key, files={"file": (f.name, f.read_bytes(), "application/pdf")})
    assert r.status_code == 202, r.text
    drain()
    assert client.get(f"/api/invoices/{r.json()['invoice_id']}", headers=key).json()["status"] in ("reconciled", "exception")
    with session_scope(world["org_id"]) as s:
        assert s.scalar(select(Document.uploaded_by).where(Document.purpose == "invoice")) is None
        entry = s.scalars(select(AuditLog).where(AuditLog.action == "invoice.uploaded")).one()
        assert (entry.actor_type, entry.actor_id, entry.actor_label) == ("api_key", __import__("uuid").UUID(k["id"]), "api-key:Scanner")
    # the same file again is a duplicate, exactly as for a person
    assert client.post("/api/invoices/upload", headers=key, files={"file": (f.name, f.read_bytes(), "application/pdf")}).status_code == 409


def test_a_key_cannot_approve_what_it_uploaded_or_anything_else(client, as_user, world):
    _k, key = make_key(client, as_user, "read_write")
    f = DATA / "invoices" / "01_correct_tavor_he.pdf"
    inv = client.post("/api/invoices/upload", headers=key, files={"file": (f.name, f.read_bytes(), "application/pdf")}).json()
    drain()
    for decision in ("approve", "reject"):
        assert client.post(f"/api/invoices/{inv['invoice_id']}/approvals", headers=key, json={"decision": decision}).status_code == 403


def test_every_route_a_key_may_use_exists_and_reads_are_get_only():
    from app.main import app

    real = {(m.upper(), path) for path, methods in app.openapi()["paths"].items() for m in methods}
    for scope, routes in api_keys.SCOPE_ROUTES.items():
        assert routes <= real, (scope, routes - real)
    assert {m for m, _ in api_keys.SCOPE_ROUTES["read"]} == {"GET"}
    assert api_keys.SCOPE_ROUTES["read_write"] - api_keys.SCOPE_ROUTES["read"] == {("POST", "/api/invoices/upload")}
    assert api_keys.route_allowed("read", "get", "/api/invoices") and not api_keys.route_allowed("read", "POST", "/api/invoices/upload")
    assert not api_keys.route_allowed("read", "GET", None) and not api_keys.route_allowed("nope", "GET", "/api/invoices")


def test_a_revoked_key_stops_working_at_once_and_it_is_audited(client, as_user, world):
    k, key = make_key(client, as_user, "read")
    assert client.get("/api/invoices", headers=key).status_code == 200
    h = as_user(ADMIN)
    assert client.delete(f"/api/org/api-keys/{k['id']}", headers=as_user("finance@kinneret.example")).status_code == 403
    r = client.delete(f"/api/org/api-keys/{k['id']}", headers=h)
    assert r.status_code == 200 and r.json()["key"]["revoked_at"]
    assert client.get("/api/invoices", headers=key).status_code == 401
    assert client.delete(f"/api/org/api-keys/{k['id']}", headers=h).status_code == 200  # revoking twice changes nothing
    listing = client.get("/api/org/api-keys", headers=h).json()["items"]
    assert listing[0]["revoked_at"]
    with session_scope(world["org_id"]) as s:
        actions = [a.action for a in s.scalars(select(AuditLog).where(AuditLog.entity_type == "api_key").order_by(AuditLog.created_at))]
    assert actions == ["api_key.created", "api_key.revoked"]  # the second revoke recorded nothing
    assert client.delete(f"/api/org/api-keys/{k['id']}", headers=as_user("admin@yarden.example")).status_code == 404


def test_unknown_malformed_and_cookie_borne_keys_are_refused(client, as_user):
    for token in ("ifk_" + "x" * 43, "ifk_", "ifk_" + "A" * 400):
        assert client.get("/api/invoices", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    _k, key = make_key(client, as_user, "read")
    secret = key["Authorization"].split()[1]
    client.cookies.clear()
    client.cookies.set("invoiceflow_session", secret)
    assert client.get("/api/invoices").status_code == 401  # a key is only accepted as a Bearer token
    client.cookies.clear()


def test_last_used_is_recorded_and_throttled(client, as_user, world):
    k, key = make_key(client, as_user, "read")
    assert client.get("/api/org/api-keys", headers=as_user(ADMIN)).json()["items"][0]["last_used_at"] is None
    client.get("/api/invoices", headers=key)
    first = client.get("/api/org/api-keys", headers=as_user(ADMIN)).json()["items"][0]["last_used_at"]
    assert first
    client.get("/api/invoices", headers=key)
    assert client.get("/api/org/api-keys", headers=as_user(ADMIN)).json()["items"][0]["last_used_at"] == first  # within the minute


def test_a_key_sees_only_its_own_organization(client, as_user, world):
    mine = upload_invoice(client, as_user("procurement@kinneret.example"), "01_correct_tavor_he.pdf")
    _k, other_key = make_key(client, as_user, "read", email="admin@yarden.example")
    assert client.get("/api/invoices", headers=other_key).json()["total"] == 0
    assert client.get(f"/api/invoices/{mine['invoice_id']}", headers=other_key).status_code == 404
    suppliers = client.get("/api/suppliers", headers=other_key).json()["items"]
    assert len(suppliers) == 1  # only the other organization's own supplier


def test_api_key_rows_are_protected_by_row_level_security(client, as_user, world):
    k, key = make_key(client, as_user, "read")
    secret = key["Authorization"].split()[1]
    left, right = world["org_id"], world["other_org_id"]

    s = new_session(right)  # another tenant sees none of it and cannot plant a row in this one
    try:
        assert s.scalars(select(ApiKey)).all() == []
        s.add(ApiKey(organization_id=left, name="planted", scope="read", prefix="ifk_planted_", key_hash="f" * 64))
        with pytest.raises(Exception, match="row-level security"):
            s.flush()
    finally:
        s.rollback()
        s.close()
    s = new_session()  # no tenant and no presented key: nothing
    try:
        assert s.scalars(select(ApiKey)).all() == []
    finally:
        s.close()
    s = new_session()  # the lookup policy exposes exactly the row whose hash is presented, read-only
    try:
        s.execute(text("SELECT set_config('app.api_key_hash', :h, true)"), {"h": api_keys.hash_secret(secret)})
        [found] = s.scalars(select(ApiKey)).all()
        assert str(found.id) == k["id"]
        assert s.execute(text("UPDATE api_keys SET name = 'renamed'")).rowcount == 0
        s.execute(text("SELECT set_config('app.api_key_hash', :h, true)"), {"h": "0" * 64})
        assert s.scalars(select(ApiKey)).all() == []
    finally:
        s.rollback()
        s.close()
    with session_scope(left) as s2:
        assert [x.name for x in s2.scalars(select(ApiKey))] == ["Integration"]


def test_the_number_of_active_keys_is_capped(client, as_user, monkeypatch):
    monkeypatch.setattr(api_keys, "MAX_ACTIVE_KEYS", 2)
    h = as_user(ADMIN)
    ids = []
    for i in range(2):
        ids.append(client.post("/api/org/api-keys", headers=h, json={"name": f"k{i}", "scope": "read"}).json()["key"]["id"])
    assert client.post("/api/org/api-keys", headers=h, json={"name": "k3", "scope": "read"}).status_code == 409
    client.delete(f"/api/org/api-keys/{ids[0]}", headers=h)
    assert client.post("/api/org/api-keys", headers=h, json={"name": "k3", "scope": "read"}).status_code == 201


def test_keys_are_rate_limited(client, as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_api_key_per_minute", 3)
    _k, key = make_key(client, as_user, "read")
    codes = [client.get("/api/invoices", headers=key).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429
