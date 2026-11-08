"""Fixed public feeds, bounded responses, pinned DNS/TLS; no publisher-page scraping."""

import asyncio
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx

from ..media import OriginTLS, connection_addresses, public_document
from .models import Material, digest, now, public_url


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def text(value, limit=5000):
    parser = Text()
    parser.feed(str(value))
    return " ".join(" ".join(parser.parts).split())[:limit]


async def fetch(url, hosts, *, method="GET", payload=None, headers=None):
    for _ in range(4):
        url = public_url(url)
        host = urlsplit(url).hostname
        if host not in hosts:
            raise ValueError("source_redirect_outside_registry")
        redirected = False
        last_error = None
        async for address in connection_addresses(url):
            try:
                async with httpx.AsyncClient(timeout=12, verify=OriginTLS(host),
                                             follow_redirects=False, trust_env=False) as client:
                    async with client.stream(
                        method, httpx.URL(url).copy_with(host=address), json=payload,
                        headers={"Host": host, "User-Agent": "CFAW-News/0.3 personal-reader",
                                 "Accept": "application/atom+xml,application/rss+xml,application/json,text/xml,*/*", **(headers or {})},
                        extensions={"sni_hostname": host},
                    ) as response:
                        if response.is_redirect:
                            if method != "GET":
                                raise ValueError("api_redirect_rejected")
                            url = urljoin(url, response.headers.get("location", ""))
                            redirected = True
                            break
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes(32768):
                            body.extend(chunk)
                            if len(body) > 2_000_000:
                                raise ValueError("source_response_too_large")
                        return bytes(body)
            except httpx.TransportError as error:
                last_error = error
        if redirected:
            continue
        if last_error:
            raise last_error
    raise ValueError("source_redirect_limit")


def parse(source, body, limit):
    if source["kind"] == "releases":
        rows = json.loads(body)
        if not isinstance(rows, list):
            raise ValueError("invalid_release_list")
        entries = [{"title": r.get("name") or r.get("tag_name"), "link": r.get("html_url"),
                    "summary": r.get("body", ""), "date": r.get("published_at")}
                   for r in rows if not r.get("draft")]
    else:
        feed = feedparser.parse(body)
        if not feed.entries:
            raise ValueError("feed_contains_no_items")
        entries = []
        for entry in feed.entries:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            date = datetime(*stamp[:6], tzinfo=timezone.utc).isoformat() if stamp else None
            # Keep explicitly bounded excerpts; never call these a full publisher document.
            supplied = entry.get("summary") or " ".join(p.get("value", "") for p in entry.get("content", []))
            entries.append({"title": entry.get("title"), "link": entry.get("link"),
                            "summary": supplied, "date": date})
    output = []
    seen = set()
    for entry in entries:
        try:
            link = entry.get("link") or ""
            url = public_url("https://" + link[7:] if link.startswith("http://") else link)
            title = text(entry.get("title") or "", 600)
            if not title or url in seen:
                continue
            seen.add(url)
            output.append(Material(
                id=digest([source["id"], url])[:24], source_id=source["id"],
                source_name=source["name"], source_role=source["role"], url=url, title=title,
                text=text(entry.get("summary") or ""), published_at=entry["date"],
                content_kind="release_notes" if source["kind"] == "releases" else "feed_excerpt",
            ))
            if len(output) >= limit:
                break
        except (ValueError, TypeError):
            continue
    return output


async def collect(store, sources, limit=10, progress=None):
    semaphore = asyncio.Semaphore(4)

    async def one(source):
        async with semaphore:
            previous = store.source_states().get(source["id"], {})
            try:
                body = await asyncio.wait_for(fetch(source["url"], set(source["hosts"])), 35)
                rows = parse(source, body, limit)
                added = sum(store.capture(row) for row in rows)
                value = {"status": "ok" if rows else "empty", "at": now(), "last_success": now(),
                         "count": len(rows), "added": added, "error": None}
            except Exception as error:
                value = {"status": "error", "at": now(), "last_success": previous.get("last_success"),
                         "count": 0, "added": 0, "error": type(error).__name__}
            store.source_state(source["id"], value)
            if progress:
                progress(source["name"], value)
            return value
    return await asyncio.gather(*(one(source) for source in sources))


async def enrich(store, limit=24, progress=None, materials=None):
    """Read bounded necessary excerpts from first-party pages; keep feed-only versions intact."""
    import trafilatura
    grouped = {}
    for material in sorted(materials if materials is not None else store.materials(),
                           key=lambda m: m.published_at or m.captured_at, reverse=True):
        host = urlsplit(material.url).hostname or ""
        if material.content_kind == "search_excerpt" and any(
            host == domain or host.endswith("." + domain)
            for domain in ("x.com", "twitter.com", "douyin.com", "xiaohongshu.com")
        ):
            # A login shell, caption or navigation page is not a post body or a video transcript.
            continue
        if ((material.source_role in {"official", "research"} and len(material.text) < 250
                and material.content_kind == "feed_excerpt") or material.content_kind == "search_excerpt"):
            grouped.setdefault(material.source_id, []).append(material)
    queue = []
    # Round robin: one prolific source cannot exhaust the whole page-reading budget.
    while grouped and len(queue) < limit:
        for source_id in list(grouped):
            queue.append(grouped[source_id].pop(0))
            if not grouped[source_id]:
                del grouped[source_id]
            if len(queue) >= limit:
                break
    semaphore = asyncio.Semaphore(3)

    async def one(material):
        async with semaphore:
            try:
                _, _, body = await asyncio.wait_for(public_document(material.url, max_bytes=700000), 30)
                extracted = trafilatura.extract(body.decode("utf-8", errors="replace"),
                                                include_comments=False, include_tables=True) or ""
                excerpt = " ".join(extracted.split())[:6000]
                if len(excerpt) <= len(material.text) or len(excerpt) < 100:
                    raise ValueError("publisher_text_unavailable")
                revised = material.model_copy(update={"text": excerpt, "captured_at": now(),
                                                       "content_kind": "publisher_excerpt"})
                store.capture(revised)
                result = {"id": material.id, "status": "ok", "chars": len(excerpt)}
            except Exception as error:
                result = {"id": material.id, "status": "unavailable", "error": type(error).__name__}
            if progress:
                progress(result)
            return result
    return await asyncio.gather(*(one(m) for m in queue))
