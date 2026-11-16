import asyncio
import socket
import ssl
from unittest.mock import patch

import httpx
import pytest
from northing_signal.briefing.net import (
    DNS_CACHE,
    OriginTLS,
    encrypted_addresses,
    pinned_addresses,
    public_document,
)

PAGE = b"<html><body><p>Public article</p></body></html>"


@pytest.fixture(autouse=True)
def clear_dns_cache():
    DNS_CACHE.clear()
    yield
    DNS_CACHE.clear()


@pytest.fixture
def pinned_transport(monkeypatch):
    calls = []
    controls = {"redirect": False, "private_dns": False, "oversize": False,
                "denial": False, "proxy_denial": False}

    def addresses(*args, **kwargs):
        host = "127.0.0.1" if controls["private_dns"] else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, 443))]

    def handler(request):
        calls.append(request)
        if controls["proxy_denial"]:
            raise httpx.ProxyError("403 Forbidden", request=request)
        if controls["denial"]:
            return httpx.Response(403)
        if controls["redirect"]:
            return httpx.Response(302, headers={"location": "https://127.0.0.1/secret"})
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                              content=PAGE + (b"x" * 600_000 if controls["oversize"] else b""))

    original = httpx.AsyncClient
    monkeypatch.setattr("socket.getaddrinfo", addresses)
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    return calls, controls


def test_outbound_connection_is_pinned_but_tls_and_host_use_original_name(pinned_transport):
    calls, _ = pinned_transport
    result = asyncio.run(public_document(
        "https://publisher.example/story",
        referer="https://publisher.example/article?private=query",
    ))
    assert result[2] == PAGE
    assert calls[0].url.host == "93.184.216.34"
    assert calls[0].headers["host"] == "publisher.example"
    assert calls[0].extensions["sni_hostname"] == "publisher.example"
    assert calls[0].headers["referer"] == "https://publisher.example/"
    assert "cookie" not in calls[0].headers and "authorization" not in calls[0].headers


def test_address_attempt_limit_keeps_ipv4_when_host_has_many_ipv6_records(monkeypatch):
    addresses = ["2606:4700::1111", "2606:4700::1001", "2001:4860:4860::8888",
                 "2001:4860:4860::8844", "93.184.216.34", "1.1.1.1"]
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda *args, **kwargs: [(0, 1, 6, "", (value, 443)) for value in addresses])
    assert asyncio.run(pinned_addresses("https://publisher.example/story")) == [
        "93.184.216.34", "2606:4700::1111", "1.1.1.1"]


def test_private_dns_and_redirect_targets_are_rejected_before_connection(pinned_transport):
    calls, controls = pinned_transport
    controls["private_dns"] = True
    with pytest.raises(ValueError):
        asyncio.run(public_document("https://publisher.example/story"))
    assert not calls
    controls.update(private_dns=False, redirect=True)

    # Both original and redirect URLs are checked; make the redirect resolve locally.
    def addresses(host, *args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443))]

    with patch("socket.getaddrinfo", addresses), pytest.raises(ValueError):
        asyncio.run(public_document("https://publisher.example/story"))
    assert len(calls) == 1


def test_oversize_documents_are_truncated_at_the_limit(pinned_transport):
    _, controls = pinned_transport
    controls["oversize"] = True
    _, _, body = asyncio.run(public_document("https://publisher.example/long", max_bytes=1000))
    assert len(body) == 1000 and body.startswith(PAGE)


def test_proxy_tls_verifies_original_domain_when_tunnel_target_is_numeric():
    context = OriginTLS("publisher.example")
    connection = context.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(), server_hostname="93.184.216.34")
    assert connection.server_hostname == "publisher.example"
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.context.get_ca_certs()


@pytest.mark.parametrize("dns_error", [False, True])
def test_failed_system_route_uses_public_dns_and_reuses_verified_address(monkeypatch, dns_error):
    calls = []

    def addresses(*args, **kwargs):
        if dns_error:
            raise socket.gaierror("system DNS unavailable")
        return [(2, 1, 6, "", ("8.8.4.4", 443))]

    def handler(request):
        calls.append(request)
        if request.url.host == "dns.google":
            assert dict(request.url.params) in [{"name": "publisher.example", "type": "A"},
                                                {"name": "publisher.example", "type": "AAAA"}]
            return httpx.Response(200, json={
                "Status": 0, "Answer": [{"type": 1, "TTL": 120, "data": "93.184.216.34"}]})
        if request.url.host == "8.8.4.4":
            raise httpx.ConnectError("unreachable local DNS result", request=request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "publisher.example"
        return httpx.Response(200, headers={"content-type": "text/html"}, content=PAGE)

    original = httpx.AsyncClient
    monkeypatch.setattr("socket.getaddrinfo", addresses)
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))

    async def check():
        assert (await public_document("https://publisher.example/one"))[2] == PAGE
        before = len(calls)
        assert (await public_document("https://publisher.example/two"))[2] == PAGE
        assert len(calls) == before + 1

    asyncio.run(check())
    assert len([r for r in calls if r.url.host == "dns.google"]) == 2
    assert all("cookie" not in r.headers and "authorization" not in r.headers for r in calls)


def test_encrypted_dns_cannot_introduce_a_private_destination(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={
            "Status": 0, "Answer": [{"type": 1, "TTL": 60, "data": "127.0.0.1"}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError, match="non_public_address"):
        asyncio.run(encrypted_addresses("publisher.example"))
    assert all(r.url.host == "dns.google" for r in calls)
    assert not DNS_CACHE


@pytest.mark.parametrize("proxy_denial", [False, True])
def test_http_or_proxy_denial_does_not_trigger_dns_fallback(pinned_transport, proxy_denial):
    calls, controls = pinned_transport
    controls.update(denial=True, proxy_denial=proxy_denial)
    with pytest.raises(httpx.HTTPError):
        asyncio.run(public_document("https://publisher.example/story"))
    assert len(calls) == 1 and calls[0].url.host == "93.184.216.34"
    assert not DNS_CACHE


def test_mixed_public_reserved_dns_rechecks_public_dns_before_any_connection(monkeypatch):
    def addresses(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443)), (10, 1, 6, "", ("2001::1", 443))]

    async def clean(host):
        assert host == "publisher.example"
        return ["1.1.1.1"]

    monkeypatch.setattr("socket.getaddrinfo", addresses)
    monkeypatch.setattr("northing_signal.briefing.net.encrypted_addresses", clean)
    assert asyncio.run(pinned_addresses("https://publisher.example/story")) == ["1.1.1.1"]
