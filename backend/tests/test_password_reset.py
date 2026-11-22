"""Email: forgotten-password links and teammate invitations.

A reset link is single-use, expires, is stored only as a hash, signs the user out everywhere, and the request
never reveals whether an address has an account. Invitations let a new teammate choose their own password."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.services import email as mail

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}
NEW = "a-brand-new-passphrase-7"
DEMO = "finance@kinneret.example"


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_backend", "memory")
    mail.OUTBOX.clear()
    yield mail.OUTBOX
    mail.OUTBOX.clear()


def token_from(message: mail.Message) -> str:
    m = re.search(r"/(?:reset-password|accept-invite)\?token=([A-Za-z0-9_\-]+)", message.text)
    assert m, message.text
    return m.group(1)


def login(client, email: str, password: str):  # noqa: ANN001, ANN201
    return client.post("/api/auth/login", json={"email": email, "password": password})


def forgot(client, email: str):  # noqa: ANN001, ANN201
    return client.post("/api/auth/forgot-password", json={"email": email}, headers=CSRF)


def reset(client, token: str, password: str = NEW):  # noqa: ANN001, ANN201
    return client.post("/api/auth/reset-password", json={"token": token, "password": password}, headers=CSRF)


# ---------------------------------------------------------------- forgotten password
def test_a_reset_link_is_emailed_and_the_answer_never_reveals_an_account(client, outbox):
    known, unknown = forgot(client, DEMO), forgot(client, "nobody@nowhere.example")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [m.to for m in outbox] == [DEMO]
    assert get_settings().app_base_url in outbox[0].text and token_from(outbox[0])


def test_the_link_sets_a_new_password_once_and_signs_out_everywhere(client, outbox):
    from app.demo.spec import DEMO_PASSWORD

    session = login(client, DEMO, DEMO_PASSWORD)
    old_access = {"Authorization": f"Bearer {session.json()['access_token']}"}
    forgot(client, DEMO)
    token = token_from(outbox[0])
    assert reset(client, token).status_code == 200
    assert login(client, DEMO, DEMO_PASSWORD).status_code == 401
    assert login(client, DEMO, NEW).status_code == 200
    assert client.get("/api/auth/me", headers=old_access).status_code == 401
    assert reset(client, token, "yet-another-passphrase-9").status_code == 400   # single use


def test_an_expired_or_unknown_link_is_refused(client, outbox):
    from app.core.db import session_scope
    from app.models import AuthToken

    forgot(client, DEMO)
    token = token_from(outbox[0])
    with session_scope() as s:
        for t in s.query(AuthToken).all():
            t.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert reset(client, token).status_code == 400
    assert reset(client, "not-a-real-token-at-all-0123456789").status_code == 400


def test_tokens_are_stored_only_as_hashes(client, outbox):
    from app.core.db import session_scope
    from app.models import AuthToken

    forgot(client, DEMO)
    token = token_from(outbox[0])
    with session_scope() as s:
        stored = [t.token_hash for t in s.query(AuthToken).all()]
    assert stored and token not in stored and all(len(h) == 64 for h in stored)


def test_a_newer_link_replaces_older_ones(client, outbox):
    forgot(client, DEMO)
    forgot(client, DEMO)
    first, second = token_from(outbox[0]), token_from(outbox[1])
    assert reset(client, first).status_code == 400
    assert reset(client, second).status_code == 200


def test_weak_passwords_and_missing_csrf_are_refused(client, outbox):
    forgot(client, DEMO)
    token = token_from(outbox[0])
    assert reset(client, token, "short").status_code == 422
    assert client.post("/api/auth/reset-password", json={"token": token, "password": NEW}).status_code == 403
    assert reset(client, token).status_code == 200


def test_reset_requests_are_rate_limited(client, outbox, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_password_reset_per_hour", 2)
    codes = [forgot(client, DEMO).status_code for _ in range(3)]
    assert codes == [202, 202, 429] and len(outbox) == 2


# ---------------------------------------------------------------- invitations
def test_an_invited_teammate_chooses_their_own_password(client, as_user, outbox):
    admin = {**as_user("admin@kinneret.example"), **CSRF}
    r = client.post("/api/org/members", headers=admin,
                    json={"email": "maya@kinneret.example", "full_name": "Maya Levi", "role": "finance_reviewer"})
    assert r.status_code == 201, r.text
    assert r.json()["invited"] is True
    assert [m.to for m in outbox] == ["maya@kinneret.example"]
    assert "Kinneret" in outbox[0].text or "כנרת" in outbox[0].text
    token = token_from(outbox[0])
    assert login(client, "maya@kinneret.example", NEW).status_code == 401      # no password until accepted
    assert reset(client, token).status_code == 200
    me = login(client, "maya@kinneret.example", NEW)
    assert me.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {me.json()['access_token']}"}).json()["role"] \
        == "finance_reviewer"


def test_someone_who_already_has_an_account_is_notified_without_a_password_link(client, as_user, outbox):
    from app.demo.spec import DEMO_PASSWORD

    other_admin = {**as_user("admin@yarden.example"), **CSRF}
    r = client.post("/api/org/members", headers=other_admin,
                    json={"email": DEMO, "full_name": "Finance", "role": "read_only"})
    assert r.status_code == 201, r.text
    assert len(outbox) == 1 and "token=" not in outbox[0].text
    assert login(client, DEMO, DEMO_PASSWORD).status_code == 200   # their password is untouched


def test_without_email_an_initial_password_is_still_required(client, as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_backend", "console")
    admin = {**as_user("admin@kinneret.example"), **CSRF}
    body = {"email": "omer@kinneret.example", "full_name": "Omer Cohen", "role": "read_only"}
    assert client.post("/api/org/members", headers=admin, json=body).status_code == 422
    r = client.post("/api/org/members", headers=admin, json={**body, "password": NEW})
    assert r.status_code == 201 and r.json()["invited"] is False


def test_the_app_tells_the_browser_whether_email_is_on(client, monkeypatch):
    assert client.get("/api/auth/options").json()["email_enabled"] is True
    monkeypatch.setattr(get_settings(), "email_backend", "console")
    options = client.get("/api/auth/options").json()
    assert options["email_enabled"] is False and "signup_enabled" in options
