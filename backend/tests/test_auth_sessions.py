"""Server-side sessions: short-lived access tokens, rotating refresh tokens, revocation,
and single-use SSE tickets (integration: PostgreSQL + Redis)."""
from __future__ import annotations

import jwt
import pytest

from app.core.config import get_settings
from app.demo.spec import DEMO_PASSWORD

pytestmark = pytest.mark.integration
CSRF = {"X-Requested-With": "invoiceflow"}
EMAIL = "finance@kinneret.example"


def _login(client) -> dict:
    r = client.post("/api/auth/login", json={"email": EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _claims(tok: str) -> dict:
    return jwt.decode(tok, options={"verify_signature": False})


def test_access_tokens_are_short_lived_and_bound_to_a_session(client):
    tok = _login(client)["access_token"]
    c = _claims(tok)
    assert c["sid"]
    assert c["exp"] - c["iat"] == get_settings().access_token_minutes * 60
    assert get_settings().access_token_minutes <= 15
    assert "invoiceflow_refresh" in client.cookies


def test_logout_revokes_the_access_token_immediately(client):
    tok = _login(client)["access_token"]
    assert client.get("/api/auth/me", headers=_bearer(tok)).status_code == 200
    assert client.post("/api/auth/logout", headers={**_bearer(tok), **CSRF}).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(tok)).status_code == 401


def test_refresh_rotates_and_reuse_of_an_old_refresh_token_revokes_the_session(client):
    _login(client)
    old_refresh = client.cookies.get("invoiceflow_refresh")
    r = client.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200, r.text
    new_access = r.json()["access_token"]
    assert client.cookies.get("invoiceflow_refresh") != old_refresh
    assert client.get("/api/auth/me", headers=_bearer(new_access)).status_code == 200

    # a stolen, already-rotated refresh token is replayed: the whole session is revoked
    client.cookies.set("invoiceflow_refresh", old_refresh)
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(new_access)).status_code == 401


def test_refresh_needs_the_csrf_header_and_a_refresh_cookie(client):
    _login(client)
    assert client.post("/api/auth/refresh").status_code == 403
    client.cookies.clear()
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401


def test_logout_everywhere_revokes_all_sessions_of_the_user(client):
    a = _login(client)["access_token"]
    b = _login(client)["access_token"]
    assert _claims(a)["sid"] != _claims(b)["sid"]
    assert client.post("/api/auth/logout-all", headers={**_bearer(a), **CSRF}).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(a)).status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(b)).status_code == 401


def test_expired_session_cannot_be_refreshed(client):
    from datetime import UTC, datetime, timedelta
    import uuid

    from app.core.db import session_scope
    from app.models import AuthSession

    tok = _login(client)["access_token"]
    with session_scope() as s:
        s.get(AuthSession, uuid.UUID(_claims(tok)["sid"])).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(tok)).status_code == 401


def test_token_without_a_session_is_rejected(client, world):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    forged = jwt.encode({"sub": str(world["users"][EMAIL]), "org": str(world["org_id"]), "role": "admin",
                         "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=5)).timestamp())},
                        get_settings().jwt_secret.get_secret_value(), algorithm="HS256")
    assert client.get("/api/auth/me", headers=_bearer(forged)).status_code == 401


def test_sse_tickets_are_single_use_and_short_lived(client):
    from app.services import sse_tickets

    tok = _login(client)["access_token"]
    r = client.post("/api/events/ticket", headers={**_bearer(tok), **CSRF})
    assert r.status_code == 200, r.text
    ticket = r.json()["ticket"]
    assert r.json()["expires_in"] <= 60
    claims = sse_tickets.consume(ticket)
    assert claims and claims["sid"] == _claims(tok)["sid"]
    assert sse_tickets.consume(ticket) is None  # single use
    client.cookies.clear()  # otherwise the session cookie would open an (endless) stream
    assert client.get("/api/events?ticket=not-a-ticket").status_code == 401
    assert client.get("/api/events").status_code == 401  # no cookie, no ticket


def test_open_event_streams_notice_revocation(client):
    from app.services import auth_sessions

    tok = _login(client)["access_token"]
    sid = _claims(tok)["sid"]
    assert auth_sessions.is_active(sid)
    client.post("/api/auth/logout", headers={**_bearer(tok), **CSRF})
    assert not auth_sessions.is_active(sid)


def _session_row(tok: str):
    import uuid

    from app.core.db import session_scope
    from app.models import AuthSession

    with session_scope() as s:
        row = s.get(AuthSession, uuid.UUID(_claims(tok)["sid"]))
        return row.created_at, row.expires_at, row.absolute_expires_at


def test_default_session_suits_a_small_business_workday(client):
    created, idle, absolute = _session_row(_login(client)["access_token"])
    assert abs((idle - created).total_seconds() - 8 * 3600) < 120       # sign in again each morning
    assert abs((absolute - created).total_seconds() - 7 * 86400) < 120  # and at least weekly


def test_admin_can_tune_session_length_within_bounds(client, as_user):
    admin = as_user("admin@kinneret.example")
    url = "/api/org/settings"
    assert client.patch(url, headers={**admin, **CSRF}, json={"security": {"session_idle_hours": 0}}).status_code == 422
    assert client.patch(url, headers={**admin, **CSRF}, json={"security": {"session_max_days": 90}}).status_code == 422
    assert client.patch(url, headers={**admin, **CSRF}, json={"security": {"session_idle_hours": 2}}).status_code == 200
    created, idle, _ = _session_row(_login(client)["access_token"])
    assert abs((idle - created).total_seconds() - 2 * 3600) < 120
    fin = as_user(EMAIL)
    assert client.patch(url, headers={**fin, **CSRF}, json={"security": {"session_idle_hours": 72}}).status_code == 403


def test_priority_threshold_is_an_org_setting(client, as_user):
    admin = as_user("admin@kinneret.example")
    r = client.patch("/api/org/settings", headers={**admin, **CSRF}, json={"priority": {"critical_amount": "2500"}})
    assert r.status_code == 200 and r.json()["settings"]["priority"]["critical_amount"] == "2500"
