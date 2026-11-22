"""The real client address for rate limits and session records.

The browser reaches the API through the web app's proxy (and in production often a load balancer too), so the
connection's peer is a proxy. ``X-Forwarded-For`` is honoured only when that peer is a trusted proxy
(``TRUSTED_PROXIES``), and then the entry appended by the outermost of ``TRUSTED_PROXY_HOPS`` proxies is used
(1 = just the web app's proxy; 2 = a load balancer in front of it). Entries a client writes itself sit to the left of
that one, so they are never chosen, even when the client's own address is private (an office network).
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache

from starlette.requests import Request

from app.core.config import get_settings


@lru_cache(maxsize=8)
def _networks(spec: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(part.strip(), strict=False) for part in spec.split(",") if part.strip())


def _ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    trusted = _networks(get_settings().trusted_proxies)
    peer_ip = _ip(peer)
    if peer_ip is None or not any(peer_ip in n for n in trusted):
        return peer
    entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
    if not entries:
        return peer
    hops = max(1, get_settings().trusted_proxy_hops)
    chosen = _ip(entries[-hops] if len(entries) >= hops else entries[0])
    return str(chosen) if chosen is not None else peer
