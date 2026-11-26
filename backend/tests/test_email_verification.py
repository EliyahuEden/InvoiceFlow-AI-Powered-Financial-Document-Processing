"""Email verification for self-service sign-up.

Where InvoiceFlow sends email, a new business's administrator confirms their address before the account works, so
nobody can sign up with someone else's address. Without a mail server (console backend) nothing could arrive, so the
address is taken as given. Invited and seeded accounts are verified from the start."""
from __future__ import annotations

import re

import pytest

from app.core.config import get_settings
from app.core.legal import LEGAL_VERSION
from app.services import email as mail

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}
STRONG = "a-long-passphrase-42"
EMAIL = "tamar@emek-olives.example"


@pytest.fixture
def outbox(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_backend", "memory")
    mail.OUTBOX.clear()
    yield mail.OUTBOX
    mail.OUTBOX.clear()


def signup(client, email: str = EMAIL):  # noqa: ANN001, ANN201
    body = {"company_name": "Emek Olives Ltd", "full_name": "Tamar Golan", "email": email, "password": STRONG,
            "tax_id": "516222228", "accepted_legal_version": LEGAL_VERSION}
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", **CSRF}


def token_from(message: mail.Message) -> str:
    m = re.search(r"/verify-email\?token=([A-Za-z0-9_\-]+)", message.text)
    assert m, message.text
    return m.group(1)


def verify(client, token: str):  # noqa: ANN001, ANN201
    return client.post("/api/auth/verify-email", json={"token": token}, headers=CSRF)


def test_a_new_account_works_only_after_the_emailed_link_is_opened(client, outbox):
    h = signup(client)
    assert [m.to for m in outbox] == [EMAIL]
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email_verification_required"] is True and me["permissions"] == []
    assert client.get("/api/invoices", headers=h).status_code == 403
    assert client.get("/api/org", headers=h).status_code == 403

    r = verify(client, token_from(outbox[0]))
    assert r.status_code == 200 and r.json()["email"] == EMAIL
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email_verification_required"] is False and "invoice:read" in me["permissions"]
    assert client.get("/api/invoices", headers=h).status_code == 200
    actions = [e["action"] for e in client.get("/api/audit", headers=h).json()["items"]]
    assert "auth.email_verified" in actions


def test_a_link_works_once_and_a_resend_replaces_the_old_one(client, outbox):
    h = signup(client)
    first = token_from(outbox[0])
    r = client.post("/api/auth/verify-email/resend", headers=h)
    assert r.status_code == 202 and len(outbox) == 2
    second = token_from(outbox[1])
    assert verify(client, first).status_code == 400  # replaced by the resend
    assert verify(client, second).status_code == 200
    assert verify(client, second).status_code == 400  # single use
    assert client.post("/api/auth/verify-email/resend", headers=h).json().get("already_verified") is True


def test_verification_links_cannot_reset_a_password(client, outbox):
    signup(client)
    r = client.post("/api/auth/reset-password", json={"token": token_from(outbox[0]), "password": "another-pass-99"},
                    headers=CSRF)
    assert r.status_code == 400


def test_verifying_needs_the_csrf_header_and_a_real_token(client, outbox):
    signup(client)
    token = token_from(outbox[0])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code in (400, 403)
    assert verify(client, "not-a-real-token-at-all").status_code == 400


def test_a_password_reset_link_also_proves_the_address(client, outbox):
    h = signup(client)
    outbox.clear()
    client.post("/api/auth/forgot-password", json={"email": EMAIL}, headers=CSRF)
    reset = re.search(r"/reset-password\?token=([A-Za-z0-9_\-]+)", outbox[0].text).group(1)
    assert client.post("/api/auth/reset-password", json={"token": reset, "password": "a-new-passphrase-77"},
                       headers=CSRF).status_code == 200
    login = client.post("/api/auth/login", json={"email": EMAIL, "password": "a-new-passphrase-77"})
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
    assert me["email_verification_required"] is False
    assert h  # the old session was signed out by the reset; the new one is unlocked


def test_without_a_mail_server_new_accounts_are_not_held_back(client):
    assert get_settings().email_backend == "console"
    h = signup(client, email="no-mail@emek-olives.example")
    assert client.get("/api/auth/me", headers=h).json()["email_verification_required"] is False
    assert client.get("/api/invoices", headers=h).status_code == 200


def test_seeded_accounts_are_verified(client, as_user):
    h = as_user("finance@kinneret.example")
    assert client.get("/api/auth/me", headers=h).json()["email_verification_required"] is False
