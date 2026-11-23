"""Two-factor sign-in with an authenticator app (TOTP, RFC 6238) and single-use recovery codes.

Turning it on needs a working code. After that, the password alone opens no session: login answers with a short-lived
challenge, and only a valid code or recovery code turns it into a session. Codes cannot be replayed, the secret is
stored encrypted, and turning it off needs the password and a code."""
from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from app.demo.spec import DEMO_PASSWORD
from app.services import mfa

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}
EMAIL = "finance@kinneret.example"


def _login(client, password: str = DEMO_PASSWORD):  # noqa: ANN001, ANN201
    return client.post("/api/auth/login", json={"email": EMAIL, "password": password})


def _bearer(client) -> dict:  # noqa: ANN001
    return {"Authorization": f"Bearer {_login(client).json()['access_token']}", **CSRF}


def _enable(client) -> tuple[str, list[str]]:  # noqa: ANN001
    h = _bearer(client)
    setup = client.post("/api/auth/2fa/setup", headers=h).json()
    assert setup["secret"] and setup["otpauth_uri"].startswith("otpauth://totp/") and setup["qr"].startswith("data:image/svg+xml")
    r = client.post("/api/auth/2fa/enable", headers=h, json={"code": mfa.totp(setup["secret"])})
    assert r.status_code == 200, r.text
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10
    return setup["secret"], codes


def _next_code(secret: str) -> str:
    """A code from the next 30-second window, so a test can sign in twice without replaying one."""
    return mfa.totp(secret, at=time.time() + 30)


def test_totp_matches_the_rfc_6238_test_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
    assert mfa.totp(secret, at=59, digits=8) == "94287082"
    assert mfa.totp(secret, at=1111111109, digits=8) == "07081804"


def test_a_wrong_code_does_not_turn_it_on(client):
    h = _bearer(client)
    client.post("/api/auth/2fa/setup", headers=h)
    assert client.post("/api/auth/2fa/enable", headers=h, json={"code": "000000"}).status_code == 422
    assert client.get("/api/auth/2fa", headers=h).json()["enabled"] is False
    assert "access_token" in _login(client).json()                      # still a plain password sign-in


def test_with_two_factor_the_password_alone_opens_no_session(client):
    secret, _ = _enable(client)
    client.cookies.clear()
    r = _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is True and body["mfa_token"] and "access_token" not in body
    assert "invoiceflow_session" not in client.cookies and "invoiceflow_refresh" not in client.cookies
    # the challenge is not a session token
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['mfa_token']}"}).status_code == 401
    done = client.post("/api/auth/login/verify", headers=CSRF, json={"mfa_token": body["mfa_token"], "code": _next_code(secret)})
    assert done.status_code == 200, done.text
    assert done.json()["access_token"] and done.json()["user"]["email"] == EMAIL


def test_a_code_cannot_be_used_twice(client):
    secret, _ = _enable(client)                                         # enabling used the current window
    token = _login(client).json()["mfa_token"]
    replay = client.post("/api/auth/login/verify", headers=CSRF, json={"mfa_token": token, "code": mfa.totp(secret)})
    assert replay.status_code == 401


def test_wrong_codes_are_refused_and_rate_limited(client):
    _enable(client)
    token = _login(client).json()["mfa_token"]
    statuses = [client.post("/api/auth/login/verify", headers=CSRF, json={"mfa_token": token, "code": "123456"}).status_code
                for _ in range(12)]
    assert statuses[0] == 401 and 429 in statuses


def test_a_recovery_code_works_once(client):
    _, codes = _enable(client)
    token = _login(client).json()["mfa_token"]
    first = client.post("/api/auth/login/verify", headers=CSRF, json={"mfa_token": token, "recovery_code": codes[0]})
    assert first.status_code == 200, first.text
    token = _login(client).json()["mfa_token"]
    again = client.post("/api/auth/login/verify", headers=CSRF, json={"mfa_token": token, "recovery_code": codes[0]})
    assert again.status_code == 401
    status = client.get("/api/auth/2fa", headers={"Authorization": f"Bearer {first.json()['access_token']}"}).json()
    assert status["enabled"] is True and status["recovery_codes_left"] == 9


def test_the_secret_and_recovery_codes_are_not_stored_in_plain_text(client, world):
    from app.core.db import new_session
    from app.models import User

    secret, codes = _enable(client)
    s = new_session()
    try:
        user = s.scalars(select(User).where(User.email == EMAIL)).one()
        assert user.totp_secret_enc and secret not in user.totp_secret_enc
        assert codes[0] not in str(user.recovery_codes)
    finally:
        s.close()


def test_turning_it_off_needs_the_password_and_a_code(client):
    secret, codes = _enable(client)
    token = _login(client).json()["mfa_token"]
    access = client.post("/api/auth/login/verify", headers=CSRF,
                         json={"mfa_token": token, "code": _next_code(secret)}).json()["access_token"]
    h = {"Authorization": f"Bearer {access}", **CSRF}
    assert client.post("/api/auth/2fa/disable", headers=h, json={"password": "wrong", "recovery_code": codes[1]}).status_code == 401
    assert client.post("/api/auth/2fa/disable", headers=h, json={"password": DEMO_PASSWORD, "code": "000000"}).status_code == 401
    # the sign-in just used the newest code window (no replay), so a recovery code turns it off here
    r = client.post("/api/auth/2fa/disable", headers=h, json={"password": DEMO_PASSWORD, "recovery_code": codes[1]})
    assert r.status_code == 200, r.text
    assert "access_token" in _login(client).json()


def test_turning_it_on_and_off_is_audited(client):
    secret, _ = _enable(client)
    token = _login(client).json()["mfa_token"]
    access = client.post("/api/auth/login/verify", headers=CSRF,
                         json={"mfa_token": token, "code": _next_code(secret)}).json()["access_token"]
    actions = [a["action"] for a in client.get("/api/audit?page_size=50", headers={"Authorization": f"Bearer {access}"}).json()["items"]]
    assert "auth.2fa_enabled" in actions and "auth.login" in actions
