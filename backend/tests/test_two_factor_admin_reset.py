"""An administrator resets two-factor sign-in for a teammate who lost their phone and recovery codes.

Only an administrator, with their own password, only for someone in their business (never themselves), and never for
an account that also belongs to a business where they are not an administrator. The teammate's sessions end, they get
an email naming who did it, and the reset is audited."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import new_session
from app.demo.spec import DEMO_PASSWORD
from app.models import Membership, Organization, Role, User
from app.services import mfa

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}
TARGET = "finance@kinneret.example"


def _bearer(client, email: str) -> dict:  # noqa: ANN001
    r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", **CSRF}


def _enable_for(client, email: str) -> dict:  # noqa: ANN001
    h = _bearer(client, email)
    secret = client.post("/api/auth/2fa/setup", headers=h).json()["secret"]
    assert client.post("/api/auth/2fa/enable", headers=h, json={"code": mfa.totp(secret)}).status_code == 200
    return h


def _user_id(email: str) -> str:
    s = new_session()
    try:
        return str(s.scalars(select(User.id).where(User.email == email)).one())
    finally:
        s.close()


def _reset(client, admin: dict, email: str, password: str = DEMO_PASSWORD):  # noqa: ANN001, ANN201
    return client.post(f"/api/org/members/{_user_id(email)}/reset-2fa", headers=admin, json={"password": password})


def test_the_team_list_shows_who_has_two_factor(client):
    _enable_for(client, TARGET)
    admin = _bearer(client, "admin@kinneret.example")
    rows = {m["email"]: m for m in client.get("/api/org/members", headers=admin).json()["items"]}
    assert rows[TARGET]["two_factor"] is True and rows["viewer@kinneret.example"]["two_factor"] is False


def test_an_admin_resets_it_and_the_teammate_signs_in_with_the_password_again(client, monkeypatch):
    from app.core.config import get_settings
    from app.services import email as mail

    sent: list = []
    monkeypatch.setattr(get_settings(), "email_backend", "memory")
    monkeypatch.setattr(mail, "send", lambda m: sent.append(m) or True)
    target_session = _enable_for(client, TARGET)
    admin = _bearer(client, "admin@kinneret.example")
    r = _reset(client, admin, TARGET)
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=target_session).status_code == 401     # their sessions ended
    assert "access_token" in client.post("/api/auth/login", json={"email": TARGET, "password": DEMO_PASSWORD}).json()
    assert sent and sent[0].to == TARGET and "admin@kinneret.example" in sent[0].text
    audit = client.get("/api/audit?action=member.2fa_reset", headers=admin).json()["items"]
    assert audit and audit[0]["entity_id"] == _user_id(TARGET)


def test_the_admin_must_confirm_with_their_own_password(client):
    _enable_for(client, TARGET)
    admin = _bearer(client, "admin@kinneret.example")
    assert _reset(client, admin, TARGET, password="not-my-password").status_code == 403
    assert client.post("/api/auth/login", json={"email": TARGET, "password": DEMO_PASSWORD}).json()["mfa_required"] is True


def test_only_administrators_and_never_for_themselves(client):
    _enable_for(client, "admin@kinneret.example")
    assert _reset(client, _bearer(client, "procurement@kinneret.example"), TARGET).status_code == 403
    # the admin now has two-factor, so sign in through the code step is needed; use a fresh admin session via setup
    s = new_session()
    try:
        admin_user = s.scalars(select(User).where(User.email == "admin@kinneret.example")).one()
        admin_user.totp_enabled_at = None                                         # sign in with the password again
        s.commit()
    finally:
        s.close()
    admin = _bearer(client, "admin@kinneret.example")
    assert _reset(client, admin, "admin@kinneret.example").status_code == 422


def test_not_for_someone_outside_the_business(client):
    _enable_for(client, "admin@yarden.example")
    admin = _bearer(client, "admin@kinneret.example")
    assert _reset(client, admin, "admin@yarden.example").status_code == 404


def test_not_for_an_account_that_also_belongs_to_another_business(client):
    _enable_for(client, TARGET)
    s = new_session()
    try:
        yarden = s.scalars(select(Organization).where(Organization.slug.like("%yarden%"))).first()
        s.add(Membership(user_id=s.scalars(select(User.id).where(User.email == TARGET)).one(),
                         organization_id=yarden.id, role=Role.READ_ONLY))
        s.commit()
    finally:
        s.close()
    admin = _bearer(client, "admin@kinneret.example")
    r = _reset(client, admin, TARGET)
    assert r.status_code == 409 and "another business" in r.json()["detail"]
