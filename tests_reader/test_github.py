"""Open source rankings: GitHub Trending and search, AI projects only, never judged (2026-11-24)."""

import asyncio
import json
from datetime import datetime, timezone

import httpx
from northing_signal.briefing import github
from northing_signal.briefing.collect import collect
from northing_signal.briefing.store import Store

TRENDING = """<main>
<article class="Box-row"><h2><a href="/acme/agent-kit">acme / agent-kit</a></h2>
<p>An agent framework for coding agents</p><span itemprop="programmingLanguage">Python</span>
<a href="/acme/agent-kit/stargazers">12,345</a><a href="/acme/agent-kit/forks">1,200</a>
<span>1,034 stars today</span></article>
<article class="Box-row"><h2><a href="/acme/css-reset">acme / css-reset</a></h2>
<p>A tiny CSS reset</p><a href="/acme/css-reset/stargazers">900</a><a href="/acme/css-reset/forks">40</a>
<span>88 stars today</span></article>
<article class="Box-row"><h2><a href="/lists/awesome-llm">lists / awesome-llm</a></h2>
<p>A curated list of LLM resources</p><a href="/lists/awesome-llm/stargazers">50,000</a>
<a href="/lists/awesome-llm/forks">900</a><span>300 stars today</span></article>
</main>""".encode()


def test_trending_keeps_ai_projects_with_stars_gained_and_flags():
    rows = github.rank(github.trending(TRENDING), 10)
    assert [r["name"] for r in rows] == ["acme/agent-kit", "lists/awesome-llm"]
    kit, collection = rows
    assert (kit["stars"], kit["forks"], kit["gained"], kit["language"]) == (12345, 1200, 1034, "Python")
    assert kit["url"] == "https://github.com/acme/agent-kit" and kit["flags"] == []
    assert collection["flags"] == ["collection", "few_forks"]  # 900 forks for 50,000 stars


def test_search_merges_topics_by_stars_and_fills_the_date():
    clock = datetime(2026, 11, 24, tzinfo=timezone.utc)
    source = {"id": "github-new", "kind": "github_search", "url": "https://api.github.com/search/repositories",
              "hosts": ["api.github.com"], "topics": ["llm", "ai-agents"], "query": "created:>{days_ago:30}",
              "max_items": 5}
    asked = []

    async def fetch(url, hosts, headers=None, **_):
        asked.append((url, headers))
        name = "a/one-llm" if "llm" in url else "b/two-agent"
        stars = 10 if "llm" in url else 20
        return json.dumps({"items": [
            {"full_name": name, "html_url": "https://github.com/" + name, "description": "agent tool",
             "stargazers_count": stars, "forks_count": 5, "created_at": "2026-11-01T00:00:00Z", "topics": ["llm"]},
            {"full_name": "a/one-llm", "html_url": "https://github.com/a/one-llm", "description": "agent tool",
             "stargazers_count": 10, "forks_count": 5, "created_at": "2026-11-01T00:00:00Z", "topics": []},
        ]}).encode()

    rows = asyncio.run(github.read_ranking(source, fetch, token="secret", clock=clock))
    assert [r["name"] for r in rows] == ["b/two-agent", "a/one-llm"]  # by stars, each once
    assert "created%3A%3E2026-10-25" in asked[0][0] and "topic%3Allm" in asked[0][0]
    assert asked[0][1]["Authorization"] == "Bearer secret"


def test_rankings_live_in_source_state_and_survive_a_failed_fetch(tmp_path, monkeypatch):
    store = Store(tmp_path / "reader.db")
    source = {"id": "github-trending-daily", "name": "Trending", "kind": "github_trending",
              "url": "https://github.com/trending", "hosts": ["github.com"], "max_items": 5}

    async def ok(url, hosts, **_):
        return TRENDING

    monkeypatch.setattr("northing_signal.briefing.collect.fetch", ok)
    asyncio.run(collect(store, [source]))
    state = store.source_states()["github-trending-daily"]
    assert state["status"] == "ok" and state["count"] == 2 and not store.materials()
    first = state["ranking_at"]

    async def down(url, hosts, **_):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("northing_signal.briefing.collect.fetch", down)
    asyncio.run(collect(store, [source]))
    state = store.source_states()["github-trending-daily"]
    assert state["status"] == "error" and state["ranking_at"] == first
    assert [r["name"] for r in state["ranking"]] == ["acme/agent-kit", "lists/awesome-llm"]


def test_the_view_carries_rankings_and_source_status_omits_their_rows(tmp_path):
    from northing_signal.briefing.service import ContentService
    from test_reader import settings
    store = Store(tmp_path / "reader.db")
    store.source_state("github-trending-daily", {"status": "ok", "ranking": [{"name": "acme/agent-kit"}],
                                                 "ranking_at": "2026-11-24T00:00:00+00:00"})
    view = ContentService(store, settings()).view()
    daily = next(r for r in view["rankings"] if r["id"] == "github-trending-daily")
    assert daily["rows"] == [{"name": "acme/agent-kit"}] and daily["at"].startswith("2026-11-24")
    assert {r["id"] for r in view["rankings"]} >= {"github-trending-weekly", "github-new", "github-top"}
    listed = next(s for s in view["sources"] if s["id"] == "github-trending-daily")
    assert "ranking" not in listed["state"]
