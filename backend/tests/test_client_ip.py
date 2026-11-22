"""Rate limits key on the real client address. Behind the web app's proxy every request arrives from the proxy, so
without X-Forwarded-For all users share one bucket and one attacker can lock everyone out of signing in. The header
is trusted only from a trusted proxy, and the rightmost untrusted hop is used, so a client cannot spoof it."""
from __future__ import annotations

from starlette.requests import Request

from app.core.client_ip import client_ip


def req(peer: str | None, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers,
                    "client": (peer, 1234) if peer else None})


def test_direct_clients_are_identified_by_their_own_address():
    assert client_ip(req("203.0.113.7")) == "203.0.113.7"


def test_an_untrusted_client_cannot_choose_its_address_with_the_header():
    assert client_ip(req("203.0.113.7", "198.51.100.1")) == "203.0.113.7"


def test_behind_the_proxy_the_forwarded_client_is_used():
    assert client_ip(req("172.18.0.5", "198.51.100.23")) == "198.51.100.23"


def test_a_spoofed_entry_before_the_real_client_is_ignored():
    # the attacker sends "X-Forwarded-For: 1.2.3.4"; the proxy appends the real address
    assert client_ip(req("172.18.0.5", "1.2.3.4, 198.51.100.23")) == "198.51.100.23"


def test_a_client_on_a_private_network_cannot_spoof_either():
    # an office network (self-hosted): the client's own address is private too
    assert client_ip(req("172.18.0.5", "203.0.113.7, 192.168.1.20")) == "192.168.1.20"


def test_a_load_balancer_in_front_of_the_web_proxy_is_one_more_hop(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 2)
    assert client_ip(req("10.0.0.2", "1.2.3.4, 198.51.100.23, 10.0.0.9")) == "198.51.100.23"


def test_two_users_behind_the_same_proxy_get_separate_buckets():
    assert client_ip(req("172.18.0.5", "198.51.100.1")) != client_ip(req("172.18.0.5", "198.51.100.2"))


def test_garbage_in_the_header_falls_back_safely():
    assert client_ip(req("172.18.0.5", "not-an-ip, <script>")) == "172.18.0.5"
    assert client_ip(req("172.18.0.5", "")) == "172.18.0.5"
    assert client_ip(req(None)) == "unknown"


def test_a_local_developer_behind_the_proxy_is_still_one_client():
    assert client_ip(req("172.18.0.5", "172.18.0.1")) == "172.18.0.1"
