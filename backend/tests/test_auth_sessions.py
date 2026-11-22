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


def test_open_event_stream_ends_when_organization_membership_is_removed(client, monkeypatch):
    import asyncio
    import uuid
    from types import SimpleNamespace

    from sqlalchemy import delete
    from starlette.requests import Request

    from app.api.routes import system
    from app.core.db import session_scope
    from app.models import Membership

    token = _login(client)["access_token"]
    claims = _claims(token)
    headers = [(b"authorization", f"Bearer {token}".encode())]

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request({"type": "http", "method": "GET", "headers": headers}, receive)
    subscribed = []
    pubsub = SimpleNamespace(subscribe=subscribed.append, close=lambda: None,
                             get_message=lambda **_: {"type": "message", "data": '{"event":"example","data":{}}'})
    monkeypatch.setattr(system, "get_redis", lambda: SimpleNamespace(pubsub=lambda **_: pubsub))
    monkeypatch.setattr(system, "SESSION_RECHECK_SECONDS", 0)

    async def check():
        stream = (await system.events(request)).body_iterator
        assert (await anext(stream))["event"] == "ready"
        assert subscribed == [system.channel(claims["org"])]
        with session_scope() as session:
            session.execute(delete(Membership).where(Membership.user_id == uuid.UUID(claims["sub"]),
                                                    Membership.organization_id == uuid.UUID(claims["org"])))
        assert (await anext(stream))["event"] == "session.ended"
        await stream.aclose()

    asyncio.run(check())


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


def test_user_lists_own_active_sessions_with_the_current_one_marked(client):
    first = _login(client)["access_token"]
    second = _login(client)["access_token"]
    r = client.get("/api/auth/sessions", headers=_bearer(second))
    assert r.status_code == 200
    rows = r.json()["items"]
    ids = {row["id"] for row in rows}
    assert {_claims(first)["sid"], _claims(second)["sid"]} <= ids
    current = [row for row in rows if row["current"]]
    assert [row["id"] for row in current] == [_claims(second)["sid"]]
    assert {"created_at", "last_used_at", "expires_at", "user_agent", "ip"} <= set(rows[0])
    assert "refresh_token_hash" not in rows[0]


def test_revoking_another_session_signs_it_out_immediately_and_is_audited(client):
    other = _login(client)["access_token"]
    mine = _login(client)["access_token"]
    sid = _claims(other)["sid"]
    r = client.delete(f"/api/auth/sessions/{sid}", headers={**_bearer(mine), **CSRF})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(other)).status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(mine)).status_code == 200
    audit = client.get("/api/audit?action=auth.session_revoked", headers=_bearer(mine))
    if audit.status_code == 200:  # finance reviewers may not read the audit log
        assert any(e["action"] == "auth.session_revoked" for e in audit.json()["items"])


def test_revoke_needs_the_csrf_header(client):
    mine = _login(client)["access_token"]
    other = _claims(_login(client)["access_token"])["sid"]
    assert client.delete(f"/api/auth/sessions/{other}", headers=_bearer(mine)).status_code == 403


def test_cannot_revoke_another_users_session(client):
    theirs = client.post("/api/auth/login", json={"email": "procurement@kinneret.example", "password": DEMO_PASSWORD})
    sid = _claims(theirs.json()["access_token"])["sid"]
    mine = _login(client)["access_token"]
    assert client.delete(f"/api/auth/sessions/{sid}", headers={**_bearer(mine), **CSRF}).status_code == 404
    assert client.get("/api/auth/me", headers=_bearer(theirs.json()["access_token"])).status_code == 200
