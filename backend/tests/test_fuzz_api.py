"""Schema-driven API fuzzing: every route, every path/query parameter and JSON field, hostile values.

The rule is simple: a server error (5xx) is never an acceptable answer to bad input. Each route is called as an
administrator (the widest permissions) with values of the wrong type, out of range, oversized, injected, or full
of control and bidirectional characters. Any 5xx is collected and reported with the exact request.
"""
from __future__ import annotations

import json
import uuid

import pytest

pytestmark = pytest.mark.integration

HOSTILE_STRINGS = [
    "", " ", "x" * 10_000, "'; DROP TABLE invoices; --", "\" OR 1=1 --", "../../../../etc/passwd", "\x00", "a\x00b",
    "‮⁦חשבונית⁩", "😀🧾💸", "%00%ff", "<script>alert(1)</script>", "{{7*7}}", "${jndi:ldap://x}",
    "NaN", "Infinity", "-0", "1e309", "0.0000000001", "-99999999999999999999.99", "2026-13-45", "null",
]
HOSTILE_IDS = ["not-a-uuid", "0", "-1", "99999999999999999999", str(uuid.uuid4()), "'; DROP TABLE x;--",
               "..%2F..%2Fetc", "x" * 300, "😀", "00000000-0000-0000-0000-000000000000"]
HOSTILE_NUMBERS = [-1, 0, 10**18, -(10**18), 1.5, "abc", None, True, [], {}]
HOSTILE_ANY = [None, 1, -1, 10**20, 1.5e308, True, "x" * 5000, [], [None] * 50, {}, {"a": {"b": {"c": [1, 2]}}}]

SKIP = {
    ("post", "/api/auth/logout"), ("post", "/api/auth/logout-all"),  # would sign the fuzzer out (still checked once)
    ("post", "/api/invoices/upload"), ("post", "/api/knowledge/documents"),  # multipart: see test_fuzz_uploads
    ("get", "/api/events"),  # an endless event stream: see test_event_stream_rejects_hostile_tickets
}
SLOW_SECONDS = 2.0


def _resolve(schema: dict, spec: dict) -> dict:
    while "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    if "allOf" in schema:
        merged: dict = {}
        for part in schema["allOf"]:
            merged.update(_resolve(part, spec))
        return merged
    return schema


def _sample(schema: dict, spec: dict, depth: int = 0):  # noqa: ANN202 - a plausible valid value for a schema
    schema = _resolve(schema, spec)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"] or schema[key]
            return _sample(options[0], spec, depth)
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        if depth > 3:
            return {}
        return {k: _sample(v, spec, depth + 1) for k, v in schema.get("properties", {}).items()
                if k in schema.get("required", [])}
    if t == "array":
        return []
    if t == "integer":
        return schema.get("minimum", 1)
    if t == "number":
        return 1
    if t == "boolean":
        return False
    if schema.get("format") == "uuid":
        return str(uuid.uuid4())
    if schema.get("format") == "date":
        return "2026-01-01"
    return "fuzz" if not schema.get("pattern") else ""


def _hostile_for(schema: dict, spec: dict) -> list:
    schema = _resolve(schema, spec)
    types = {schema.get("type")} | {(_resolve(s, spec)).get("type") for s in schema.get("anyOf", [])}
    if schema.get("format") == "uuid":
        return HOSTILE_IDS[:6] + [None, 5]
    if types & {"integer", "number"}:
        return HOSTILE_NUMBERS
    if "string" in types:
        return HOSTILE_STRINGS + [None, 7, []]
    return HOSTILE_ANY


@pytest.fixture()
def fuzz_client(client, as_user, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_minute", 100_000)  # rate limiting is tested elsewhere
    headers = {**as_user("admin@kinneret.example"), "X-Requested-With": "invoiceflow"}
    return client, headers


def test_no_route_returns_a_server_error_for_hostile_input(fuzz_client):
    from app.main import app

    client, headers = fuzz_client
    spec = app.openapi()
    failures: list[str] = []
    slow: list[str] = []
    count = 0

    def call(method: str, url: str, **kw) -> None:  # noqa: ANN003
        nonlocal count
        import time

        count += 1
        t0 = time.perf_counter()
        merged = {**headers, **kw.pop("headers", {})}
        try:
            r = client.request(method.upper(), url, headers=merged, **kw)
        except Exception as exc:  # noqa: BLE001 - an exception escaping the app is a failure too
            failures.append(f"{method.upper()} {url} {json.dumps(kw, default=str)[:300]} -> EXCEPTION {exc!r}"[:600])
            return
        if r.status_code >= 500:
            failures.append(f"{method.upper()} {url} {json.dumps(kw, default=str)[:300]} -> {r.status_code} {r.text[:200]}")
        elapsed = time.perf_counter() - t0
        if elapsed > SLOW_SECONDS:
            slow.append(f"{elapsed:.1f}s {method.upper()} {url} {json.dumps(kw, default=str)[:160]}")

    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if (method, path) in SKIP or method not in ("get", "post", "put", "patch", "delete"):
                continue
            params = op.get("parameters", [])
            path_params = [p for p in params if p["in"] == "path"]
            query_params = [p for p in params if p["in"] == "query"]
            body_schema = (op.get("requestBody", {}).get("content", {}).get("application/json", {}) or {}).get("schema")
            base_path = path
            for p in path_params:
                base_path = base_path.replace("{" + p["name"] + "}", str(uuid.uuid4()))
            base_body = _sample(body_schema, spec) if body_schema else None
            # 1. hostile path parameters
            for p in path_params:
                for value in HOSTILE_IDS:
                    url = path
                    for q in path_params:
                        url = url.replace("{" + q["name"] + "}", value if q is p else str(uuid.uuid4()))
                    call(method, url, json=base_body)
            # 2. hostile query parameters
            for p in query_params:
                for value in _hostile_for(p.get("schema", {}), spec):
                    if value is None or isinstance(value, (list, dict)):
                        continue
                    call(method, base_path, params={p["name"]: value}, json=base_body)
            # 3. hostile JSON fields, and wholly wrong bodies
            if body_schema:
                props = _resolve(body_schema, spec).get("properties", {})
                for name, sub in props.items():
                    for value in _hostile_for(sub, spec):
                        call(method, base_path, json={**(base_body or {}), name: value})
                for body in (None, [], "text", 12, {"unexpected": "x" * 2000}, [{"a": 1}] * 100):
                    call(method, base_path, json=body)
                call(method, base_path, content=b"{not json", headers={**headers, "content-type": "application/json"})
    # the two sign-out routes, once, at the end
    for url in ("/api/auth/logout", "/api/auth/logout-all"):
        call("post", url, json={"x": "\x00"})
    print(f"\nfuzz: {count} requests, {len(failures)} server errors, {len(slow)} slower than {SLOW_SECONDS}s")
    for line in slow[:30]:
        print("SLOW", line)
    assert not failures, f"{len(failures)} server errors:\n" + "\n".join(failures[:60])
    assert not slow, f"{len(slow)} requests slower than {SLOW_SECONDS}s:\n" + "\n".join(slow[:30])


@pytest.mark.parametrize("ticket", ["x", "", "'; DROP TABLE x;--", "a" * 5000, "\x00", "😀"])
def test_event_stream_rejects_hostile_tickets(client, ticket):
    r = client.get("/api/events", params={"ticket": ticket} if ticket else None)
    assert r.status_code in (401, 403, 422), r.status_code  # 422: NUL characters are refused before auth
