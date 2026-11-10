"""Public HTTPS reads pinned to checked global addresses; no private or HTTP targets."""

import asyncio
import ipaddress
import socket
from itertools import zip_longest
from time import monotonic
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

DNS_CACHE = {}


class OriginTLS:
    """Keep hostname verification when a proxy tunnels to a checked numeric IP.

    httpcore's HTTP CONNECT path does not honor the sni_hostname extension.
    Delegate TLS configuration to HTTPX, including the configured trust store,
    and bind both SNI and certificate matching to the original publisher host.
    Each client has its own context; the proxy's own TLS context is separate.
    """

    def __init__(self, hostname):
        self.hostname = hostname
        self.context = httpx.create_ssl_context()

    def __getattr__(self, name):
        return getattr(self.context, name)

    def wrap_bio(self, incoming, outgoing, server_side=False, server_hostname=None, session=None):
        return self.context.wrap_bio(
            incoming,
            outgoing,
            server_side=server_side,
            server_hostname=self.hostname,
            session=session,
        )


def public_url(value, base=""):
    parts = urlsplit(urljoin(base, value))
    host = (parts.hostname or "").rstrip(".").lower()
    if (
        parts.scheme not in {"http", "https"}
        or not host
        or parts.username
        or parts.password
        or parts.port not in {None, 80, 443}
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or len(value) > 4096
    ):
        raise ValueError("not_public_https")
    host = host.encode("idna").decode()
    authority = f"[{host}]" if ":" in host else host
    # Try HTTPS for old HTTP links; never downgrade or connect to an HTTP service.
    return urlunsplit(("https", authority, parts.path or "/", parts.query, ""))


def checked_addresses(addresses):
    addresses = list(dict.fromkeys(addresses))
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise ValueError("non_public_address")
    ipv4 = [value for value in addresses if ":" not in value]
    ipv6 = [value for value in addresses if ":" in value]
    # Keep both families in the bounded attempt list, even for CDN hosts with
    # many IPv6 records on networks where only IPv4 is reachable.
    return [value for pair in zip_longest(ipv4, ipv6) for value in pair if value][:3]


async def pinned_addresses(url):
    host = urlsplit(url).hostname
    cached = DNS_CACHE.get(host)
    if cached and cached[0] > monotonic():
        return checked_addresses(cached[1])
    records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    addresses = [record[4][0] for record in records]
    try:
        return checked_addresses(addresses)
    except ValueError:
        # A mixed public/reserved answer can be poisoned DNS. Obtain a fresh
        # public answer instead of silently dropping records or using private
        # ones. Purely private destinations remain rejected without fallback.
        if not any(ipaddress.ip_address(value).is_global for value in addresses):
            raise
        return await encrypted_addresses(host)


async def encrypted_addresses(host):
    """Only public hostnames, never article paths or personal application data."""
    async with httpx.AsyncClient(timeout=4, follow_redirects=False) as client:

        async def lookup(kind):
            response = await client.get(
                "https://dns.google/resolve",
                params={"name": host, "type": kind},
                headers={"Accept": "application/dns-json"},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("Status") != 0:
                return []
            return result.get("Answer", [])

        results = await asyncio.gather(lookup("A"), lookup("AAAA"), return_exceptions=True)
    answers = [
        answer
        for result in results
        if isinstance(result, list)
        for answer in result
        if isinstance(answer, dict) and answer.get("type") in {1, 28}
    ]
    addresses = checked_addresses(answer["data"] for answer in answers)
    ttl = min([max(0, int(answer.get("TTL", 60))) for answer in answers] + [300])
    if len(DNS_CACHE) >= 128:
        DNS_CACHE.pop(next(iter(DNS_CACHE)))
    DNS_CACHE[host] = (monotonic() + ttl, addresses)
    return addresses


async def connection_addresses(url):
    try:
        local = await pinned_addresses(url)
    except socket.gaierror:
        local = []
    for address in local:
        yield address
    # This generator reaches the external resolver only after every local
    # address failed to connect. A HTTP denial or invalid public target stops
    # the caller before this fallback; neither is retried through another route.
    for address in await encrypted_addresses(urlsplit(url).hostname):
        if address not in local:
            yield address


async def public_document(url, *, referer="", json_data=False, max_bytes=None):
    """Pin each connection to a checked IP; retain the original TLS name and Host."""
    url = public_url(url)
    for _ in range(4):
        host = urlsplit(url).hostname
        headers = {
            "Host": host,
            "User-Agent": "CFAW-News/0.3 personal-reader",
            "Accept": "application/json" if json_data else "text/html,application/xhtml+xml",
        }
        if referer:
            page = urlsplit(public_url(referer))
            headers["Referer"] = f"{page.scheme}://{page.netloc}/"
        limit = max_bytes or 524_288
        redirected = False
        last_error = None
        async for address in connection_addresses(url):
            target = httpx.URL(url).copy_with(host=address)
            # Fresh clients isolate cookies and TLS sessions of virtual hosts.
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(7, connect=3),
                    follow_redirects=False,
                    verify=OriginTLS(host),
                    trust_env=True,
                ) as client:
                    async with client.stream(
                        "GET", target, headers=headers, extensions={"sni_hostname": host}
                    ) as response:
                        if response.is_redirect:
                            url = public_url(response.headers.get("location", ""), url)
                            redirected = True
                            break
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "")
                        kind = content_type.split(";")[0].strip().lower()
                        if json_data and kind != "application/json":
                            raise ValueError("not_json")
                        if not json_data and kind not in {"text/html", "application/xhtml+xml"}:
                            return url, content_type, b""
                        body = bytearray()
                        async for chunk in response.aiter_bytes(32768):
                            body.extend(chunk)
                            if len(body) > limit:
                                del body[limit:]
                                break
                        return url, content_type, bytes(body)
            except httpx.ProxyError:
                raise
            except httpx.TransportError as exc:
                last_error = exc
        if redirected:
            continue
        if last_error:
            raise last_error
    raise ValueError("too_many_redirects")
