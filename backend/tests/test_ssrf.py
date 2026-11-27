"""The server-side request forgery guard for webhook targets (no database needed)."""
import pytest

from app.core import ssrf

BLOCKED = [
    "127.0.0.1", "127.1.2.3", "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.254", "192.168.0.1",
    "169.254.169.254",  # the cloud metadata service
    "100.64.0.1",  # carrier-grade NAT
    "0.0.0.0", "224.0.0.1", "255.255.255.255", "192.0.0.8", "198.18.0.1", "240.0.0.1",
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456:789a::1", "ff02::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",  # IPv4 inside IPv6
    "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
    "2002:7f00:1::1",  # 6to4 of 127.0.0.1
]
ALLOWED = ["93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "2a00:1450:4001:81b::200e"]


@pytest.mark.parametrize("address", BLOCKED)
def test_non_public_addresses_are_refused(address):
    assert ssrf.is_public(address) is False


@pytest.mark.parametrize("address", ALLOWED)
def test_public_addresses_are_allowed(address):
    assert ssrf.is_public(address) is True


@pytest.mark.parametrize("url", [
    "http://example.com/hook",  # not HTTPS
    "ftp://example.com/hook", "file:///etc/passwd", "gopher://example.com/", "//example.com/hook", "example.com/hook",
    "https://user:secret@example.com/hook", "https://user@example.com/hook",  # credentials in the URL
    "https:///hook", "https://", "https://example.com/hook#frag",
    "https://example.com:notaport/hook", "https://exa mple.com/", "https://example.com/a\nb", "https://" + "a" * 2100,
])
def test_malformed_or_unsafe_urls_are_refused_before_any_lookup(url):
    def never(_host, _port):
        raise AssertionError("no DNS lookup for a URL that is refused on syntax")

    with pytest.raises(ssrf.UnsafeTarget):
        ssrf.resolve_public(url, never)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/", "https://127.0.0.1:8443/hook", "https://10.1.2.3/", "https://192.168.1.10/hook",
    "https://169.254.169.254/latest/meta-data/", "https://[::1]/", "https://[fe80::1]/", "https://[::ffff:127.0.0.1]/",
    "https://0.0.0.0/", "https://100.64.0.1/",
])
def test_literal_private_addresses_are_refused(url):
    with pytest.raises(ssrf.UnsafeTarget, match="private or internal"):
        ssrf.resolve_public(url, lambda *_: ["93.184.216.34"])  # the resolver must not even be consulted


def test_a_name_must_resolve_to_public_addresses_only():
    resolve = {"ok.example": ["93.184.216.34", "2606:4700:4700::1111"], "inward.example": ["10.0.0.5"],
               "mixed.example": ["93.184.216.34", "127.0.0.1"], "metadata.example": ["169.254.169.254"],
               "empty.example": []}
    resolver = lambda host, _port: resolve[host]  # noqa: E731
    host, path, port, addresses = ssrf.resolve_public("https://ok.example/hooks/in?x=1", resolver)
    assert (host, path, port, addresses) == ("ok.example", "/hooks/in?x=1", 443, ["93.184.216.34", "2606:4700:4700::1111"])
    for name in ("inward.example", "mixed.example", "metadata.example"):
        with pytest.raises(ssrf.UnsafeTarget, match="private or internal"):
            ssrf.resolve_public(f"https://{name}/", resolver)
    with pytest.raises(ssrf.UnsafeTarget, match="does not resolve"):
        ssrf.resolve_public("https://empty.example/", resolver)


def test_localhost_and_unresolvable_names_are_refused_with_the_real_resolver():
    with pytest.raises(ssrf.UnsafeTarget):
        ssrf.resolve_public("https://localhost/hook")
    with pytest.raises(ssrf.UnsafeTarget):
        ssrf.resolve_public("https://does-not-exist.invalid/hook")


def test_the_port_and_a_trailing_dot_are_normalised():
    host, _path, port, _ = ssrf.resolve_public("https://Hooks.Example.COM.:8443", lambda *_: ["93.184.216.34"])
    assert (host, port) == ("hooks.example.com", 8443)
