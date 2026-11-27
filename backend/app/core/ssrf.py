"""Server-side request forgery guard for URLs an administrator gives us (webhook targets).

A target must be HTTPS, carry no credentials, and name a host whose every address is a public one:
loopback, private (RFC 1918 / ULA), link-local (including the cloud metadata address), carrier-grade NAT,
multicast, reserved and unspecified ranges are refused. Addresses are checked when the URL is registered *and*
again, freshly resolved, on every delivery, and the connection goes to the address that was checked (never to a
second DNS answer), so a name that later points inward (DNS rebinding) is refused too.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2000
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], list[str]]

# ranges Python's is_global does not flag on every supported version, or that smuggle an IPv4 address inside IPv6
_EXTRA_BLOCKED = tuple(ipaddress.ip_network(n) for n in (
    "100.64.0.0/10",   # carrier-grade NAT
    "64:ff9b::/96",    # NAT64: an IPv4 address in disguise
    "64:ff9b:1::/48",  # local-use NAT64
    "2002::/16",       # 6to4
    "2001::/32",       # Teredo
    "192.0.0.0/24", "198.18.0.0/15", "240.0.0.0/4",
))


class UnsafeTarget(ValueError):
    """The URL must not be requested (the message is safe to show to the administrator)."""


def is_public(address: str | IPAddress) -> bool:
    ip = ipaddress.ip_address(address) if isinstance(address, str) else address
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        return False
    return not any(ip in net for net in _EXTRA_BLOCKED if net.version == ip.version)


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTarget("The host name does not resolve") from exc
    out: list[str] = []
    for info in infos:
        address = info[4][0].split("%")[0]
        if address not in out:
            out.append(address)
    return out


def parse_target(url: str) -> tuple[str, str, int]:
    """Syntax checks that need no network: returns (host, path-with-query, port)."""
    if len(url) > MAX_URL_LENGTH or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise UnsafeTarget("Enter a valid HTTPS URL")
    try:
        parts = urlsplit(url)
        port = parts.port or 443
    except ValueError as exc:
        raise UnsafeTarget("Enter a valid HTTPS URL") from exc
    if parts.scheme != "https":
        raise UnsafeTarget("The URL must start with https://")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeTarget("The URL must not contain a user name or password")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeTarget("Enter a valid HTTPS URL")
    if parts.fragment:
        raise UnsafeTarget("The URL must not contain a fragment")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return host, path, port


def resolve_public(url: str, resolver: Resolver | None = None) -> tuple[str, str, int, list[str]]:
    """Validate ``url`` and return (host, path, port, public addresses). Refuses it if any address is not public."""
    host, path, port = parse_target(url)
    try:
        addresses = [str(ipaddress.ip_address(host))]  # a literal address: no DNS involved
    except ValueError:
        addresses = (resolver or system_resolver)(host, port)
    if not addresses:
        raise UnsafeTarget("The host name does not resolve")
    for address in addresses:
        if not is_public(address):
            raise UnsafeTarget("The URL points to a private or internal address")
    return host, path, port, addresses
