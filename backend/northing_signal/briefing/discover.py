"""Explicit, bounded searches of public research and repository indexes."""

import asyncio
import base64
import json
import re
from urllib.parse import urlencode

from .collect import enrich, fetch, parse, text
from .models import Material, digest, now
from .search_sources import PROVIDERS, SEARCH_SOURCES, source_access


async def discover(store, query, limit=4, channels=None, settings=None):
    terms = " ".join(query.split())[:100] or "AI agents"

    async def papers():
        source = {"id": "arxiv-discovery", "name": "arXiv · 预印本", "role": "research", "kind": "rss"}
        params = urlencode({"search_query": 'all:"' + terms.replace('"', ' ') + '"', "start": 0,
                            "max_results": limit, "sortBy": "submittedDate", "sortOrder": "descending"})
        body = await asyncio.wait_for(fetch("https://export.arxiv.org/api/query?" + params,
                                           {"export.arxiv.org", "arxiv.org"}), 35)
        return parse(source, body, limit)

    async def repositories():
        params = urlencode({"q": terms + " stars:>30 archived:false fork:false",
                            "sort": "updated", "per_page": limit})
        body = await asyncio.wait_for(fetch("https://api.github.com/search/repositories?" + params,
                                           {"api.github.com"}), 30)
        output = []
        for index, repo in enumerate(json.loads(body).get("items", [])[:limit]):
            name = repo.get("full_name", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
                continue
            excerpt = repo.get("description") or ""
            # At most two README requests, only for repositories with a declared open license.
            license_id = (repo.get("license") or {}).get("spdx_id")
            if index < 2 and license_id in {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause"}:
                try:
                    raw = json.loads(await asyncio.wait_for(fetch(
                        "https://api.github.com/repos/" + name + "/readme", {"api.github.com"}), 20))
                    excerpt += "\n" + base64.b64decode(raw["content"]).decode("utf-8", errors="replace")[:4500]
                except (ValueError, KeyError, TimeoutError):
                    pass
            url = repo["html_url"]
            output.append(Material(id=digest(["github-discovery", url])[:24], source_id="github-discovery",
                                   source_name="GitHub · " + name, source_role="author", title=name,
                                   url=url, text=text(excerpt), published_at=None,
                                   content_kind="publisher_excerpt"))
        return output

    names = [("arxiv-discovery", "arXiv · 预印本", "https://arxiv.org/", "research"),
             ("github-discovery", "GitHub · 项目发现", "https://github.com/", "author")]
    selected = set(channels if channels is not None else ("web", "arxiv", "github"))
    if not selected or selected - set(SEARCH_SOURCES):
        raise ValueError("unsupported_search_channel")
    jobs = []
    if "arxiv" in selected:
        jobs.append((papers, names[0]))
    if "github" in selected:
        jobs.append((repositories, names[1]))
    for channel, provider in PROVIDERS.items():
        if channel in selected:
            async def run_provider(provider=provider):
                return await provider(terms, limit, settings)
            meta = SEARCH_SOURCES[channel]
            jobs.append((run_provider, (channel + "-discovery", meta["name"], meta["url"], meta["role"])))
    results = await asyncio.gather(*(job() for job, _ in jobs), return_exceptions=True)
    found = []
    for result, (_, (source_id, name, url, role)) in zip(results, jobs, strict=True):
        if isinstance(result, Exception):
            previous = store.source_states().get(source_id, {})
            state = {"status": "error", "at": now(), "last_success": previous.get("last_success"),
                     "error": type(result).__name__, "query": terms}
            if getattr(result, "response", None) is not None:
                state["http_status"] = result.response.status_code
        else:
            found.extend(result)
            added = sum(store.capture(m) for m in result)
            state = {"status": "ok" if result else "empty", "at": now(), "last_success": now(),
                     "count": len(result), "added": added, "query": terms}
        store.source_state(source_id, {**state, "name": name, "url": url, "role": role,
                                      "access": source_access(source_id.removesuffix("-discovery"), settings)})
    # Search-engine snippets are only leads. Read at most two originals through the existing public-network boundary.
    page_leads = [m for m in found if m.content_kind == "search_excerpt"]
    if page_leads:
        await enrich(store, limit=2, materials=page_leads)
        latest = {m.id: m for m in store.materials()}
        found = [latest.get(m.id, m) for m in found]
    grouped = {}
    for material in found:
        grouped.setdefault(material.source_id, []).append(material)
    balanced = []
    while grouped:
        for source_id in list(grouped):
            balanced.append(grouped[source_id].pop(0))
            if not grouped[source_id]:
                del grouped[source_id]
    return balanced
