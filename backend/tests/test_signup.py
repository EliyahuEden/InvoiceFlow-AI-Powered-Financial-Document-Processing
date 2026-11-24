"""Self-service businesses: sign-up creates an isolated organization with its first administrator, who manages
the team (add, remove, roles). Users change their own password."""
from __future__ import annotations

import pytest

from app.core.legal import LEGAL_VERSION

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}
STRONG = "a-long-passphrase-42"


def signup(client, **over):  # noqa: ANN001, ANN201
    body = {"company_name": "Galil Bakery Ltd", "full_name": "Noa Peretz", "email": "noa@galil-bakery.example",
            "password": STRONG, "tax_id": "516111117", "accepted_legal_version": LEGAL_VERSION, **over}
    return client.post("/api/auth/signup", json=body)


def bearer(r) -> dict:  # noqa: ANN001
    return {"Authorization": f"Bearer {r.json()['access_token']}", **CSRF}


def test_signup_creates_an_isolated_business_with_its_first_admin(client, as_user):
    r = signup(client)
    assert r.status_code == 201, r.text
    me = client.get("/api/auth/me", headers=bearer(r)).json()
    assert me["organization"]["name"] == "Galil Bakery Ltd" and me["role"] == "admin"
    h = bearer(r)
    assert client.get("/api/invoices", headers=h).json()["items"] == []
    assert client.get("/api/suppliers", headers=h).json()["items"] == []
    assert client.get("/api/review/queue", headers=h).json()["items"] == []
    org = client.get("/api/org", headers=h).json()
    assert org["settings"]["tax_id"] == "516111117"  # used to never read the business itself as the supplier
    # and the demo company does not see the new business either
    kin = as_user("admin@kinneret.example")
    assert all(m["email"] != "noa@galil-bakery.example" for m in client.get("/api/org/members", headers=kin).json()["items"])


def test_the_same_email_cannot_sign_up_twice(client):
    assert signup(client).status_code == 201
    r = signup(client, company_name="Another Co")
    assert r.status_code == 409 and "sign in" in r.json()["detail"].lower()


@pytest.mark.parametrize("over", [{"password": "short"}, {"email": "not-an-email"}, {"company_name": "x"},
                                  {"full_name": ""}, {"tax_id": "12"}, {"company_name": "a" * 300}])
def test_invalid_sign_up_is_refused(client, over):
    assert signup(client, **over).status_code == 422


def test_sign_up_can_be_turned_off(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "allow_signup", False)
    assert signup(client).status_code == 403


def test_hebrew_company_names_work(client):
    r = signup(client, company_name="מאפיית הגליל בע\"מ", email="dana@galil.example")
    assert r.status_code == 201
    assert client.get("/api/auth/me", headers=bearer(r)).json()["organization"]["name"] == "מאפיית הגליל בע\"מ"


def test_admin_adds_and_removes_team_members(client):
    admin = bearer(signup(client))
    r = client.post("/api/org/members", headers=admin, json={"email": "avi@galil-bakery.example", "full_name": "Avi Levi",
                                                             "role": "finance_reviewer", "password": STRONG})
    assert r.status_code == 201, r.text
    login = client.post("/api/auth/login", json={"email": "avi@galil-bakery.example", "password": STRONG})
    assert login.status_code == 200 and login.json()["role"] == "finance_reviewer"
    avi = bearer(login)
    assert client.get("/api/org/members", headers=admin).json()["items"][0]["email"]
    r = client.delete(f"/api/org/members/{login.json()['user']['id']}", headers=admin)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=avi).status_code == 401  # removed: signed out at once


def test_the_last_admin_and_yourself_cannot_be_removed(client):
    r = signup(client)
    admin, me = bearer(r), r.json()["user"]["id"]
    assert client.delete(f"/api/org/members/{me}", headers=admin).status_code == 422


def test_only_admins_manage_the_team(client):
    admin = bearer(signup(client))
    client.post("/api/org/members", headers=admin, json={"email": "v@galil-bakery.example", "full_name": "Viewer",
                                                         "role": "read_only", "password": STRONG})
    viewer = bearer(client.post("/api/auth/login", json={"email": "v@galil-bakery.example", "password": STRONG}))
    r = client.post("/api/org/members", headers=viewer, json={"email": "x@x.example", "full_name": "X Y",
                                                              "role": "admin", "password": STRONG})
    assert r.status_code == 403


def test_users_change_their_own_password(client):
    r = signup(client)
    h = bearer(r)
    bad = client.post("/api/auth/password", headers=h, json={"current_password": "wrong-password-123", "new_password": "x" * 14})
    assert bad.status_code == 400
    ok = client.post("/api/auth/password", headers=h, json={"current_password": STRONG, "new_password": "new-passphrase-777"})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"email": "noa@galil-bakery.example", "password": STRONG}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "noa@galil-bakery.example",
                                                "password": "new-passphrase-777"}).status_code == 200


def test_signup_requires_and_records_acceptance_of_the_current_legal_documents(client, as_user):
    assert signup(client, accepted_legal_version="2000-01-01").status_code == 400
    body = {"company_name": "No Consent Ltd", "full_name": "No Consent", "email": "none@consent.example", "password": STRONG}
    assert client.post("/api/auth/signup", json=body).status_code == 422
    r = signup(client)
    assert r.status_code == 201, r.text
    from sqlalchemy import select

    from app.core.db import new_session
    from app.models import AuditLog
    s = new_session(r.json()["organization"]["id"])
    try:
        entry = s.scalars(select(AuditLog).where(AuditLog.action == "legal.accepted")).first()
        assert entry is not None and entry.meta["version"] == LEGAL_VERSION
    finally:
        s.close()


def test_backend_and_frontend_agree_on_the_legal_version():
    from pathlib import Path
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "legal.ts"
    assert f'LEGAL_VERSION = "{LEGAL_VERSION}"' in frontend.read_text(encoding="utf-8")
