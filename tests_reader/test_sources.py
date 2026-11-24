"""Small source contracts using synthetic payloads; live availability is checked separately."""

import asyncio
import json

import httpx
from northing_signal.briefing.collect import collect, enrich, parse
from northing_signal.briefing.models import Material
from northing_signal.briefing.source_adapters import hub_models
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import has_material


def source(kind="publisher_index", **changes):
    return dict(id="example", name="Fixture", role="official", kind=kind,
                url="https://example.org/news", hosts=["example.org"],
                article_hosts=["example.org"], path_pattern=r"^/news/[^/]+$", **changes)


def test_publisher_index_remains_a_lead_and_keeps_article_dates_and_revisions(tmp_path, monkeypatch):
    body = b'''<nav><a href="/news/navigation">Navigation title</a></nav><main>
    <a href="/news/atlas">Atlas model launch</a>
    <a href="/news/atlas"><h2>Atlas model launch</h2><footer>Nov 2, 2026</footer></a>
    <a href="https://other.example/news/fake">External fabricated title</a>
    <a href="/news/beta"><h2>Beta model launch</h2><time datetime="2026-11-03"></time></a>
    <a href="/news">All articles</a></main>'''
    rows = parse(source(), body, 5)
    assert [r.title for r in rows] == ["Beta model launch", "Atlas model launch"]
    assert rows[1].published_at.startswith("2026-11-02")
    assert all(r.content_kind == "search_excerpt" and not has_material(r) for r in rows)
    store = Store(tmp_path / "sources.db")
    store.capture(rows[0])

    async def original(*args, **kwargs):
        return "https://example.org/news/beta", "text/html", (b'<html><head><meta property="article:published_time" content="2026-11-03T11:25:00Z"></head>'
            b'<body><article><h1>Beta model release</h1><p>' + b'Actual original model release with concrete runtime conditions. ' * 15 + b'</p></article></body></html>')

    monkeypatch.setattr("northing_signal.briefing.collect.public_document", original)
    asyncio.run(enrich(store, materials=rows[:1]))
    assert store.material(rows[0].version).content_kind == "search_excerpt"
    updated = store.materials()[0]
    assert updated.content_kind == "publisher_excerpt" and has_material(updated)
    assert "runtime conditions" in updated.text


def test_changelog_sections_and_arxiv_preserve_original_evidence_type():
    body = b'<main><h2>Date: 2026-11-02</h2><p>' + b'We released a model. Conditions apply. ' * 5 + b'</p><h2>Date: 2026-99-99</h2><p>bad</p></main>'
    rows = parse(source("changelog"), body, 3)
    assert len(rows) == 1 and rows[0].published_at.startswith("2026-11-02")
    assert rows[0].content_kind == "publisher_excerpt" and "Conditions apply" in rows[0].text
    feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Original paper</title><id>arxiv:2611.00001v2</id><link href="https://arxiv.org/abs/2611.00001v2"/><summary>An original abstract.</summary><published>2026-11-01T01:00:00Z</published></entry></feed>'
    papers = parse(source("arxiv"), feed, 3)
    assert papers[0].content_kind == "index_abstract"
    assert papers[0].url.endswith("v2") and papers[0].published_at.startswith("2026-11-01")
    notes = b'## Changelog\n\n### 2026-01-08\n' + b'An earlier benchmark task change with concrete conditions. ' * 5 + b'\n### 2025-12-23\nOlder change.'
    old = parse(source("markdown"), notes, 1)[0]
    assert old.published_at.startswith("2026-01-08") and "Older change" not in old.text


def test_model_cards_are_public_bounded_and_catalog_dates_are_not_release_dates():
    payload = json.dumps([{"id":"owner/model", "lastModified":"2026-11-08", "tags":["license:other"]},
                          {"id":"other/model"}, {"id":"owner/metadata"}]).encode()
    calls = []

    async def denied(url, hosts):
        calls.append(url)
        raise httpx.HTTPStatusError("restricted", request=httpx.Request("GET", url), response=httpx.Response(403))

    rows = asyncio.run(hub_models(source("hub_models", organization="owner"), payload, 3, denied))
    assert len(rows) == 2 and len(calls) == 1
    assert all(r.published_at is None and r.content_kind == "catalog_metadata" and not has_material(r) for r in rows)

    async def card(url, hosts):
        return ("# Model\nPublic model card with an explicitly stated limitation.\n" * 200).encode()

    rows = asyncio.run(hub_models(source("hub_models", organization="owner"), payload, 3, card))
    assert rows[0].content_kind == "publisher_excerpt" and len(rows[0].text) <= 6000
    assert rows[1].content_kind == "catalog_metadata" and rows[0].published_at is None
    catalog = {"success":True,"data":{"models":[{"id":"owner/model","last_modified":"2026-11-08","private":False},
                                                  {"id":"other/model","private":False}]}}
    rows = parse(source("modelscope_models",organization="owner"),json.dumps(catalog).encode(),3)
    assert len(rows)==1 and rows[0].published_at is None and not has_material(rows[0])


def test_model_catalogs_date_entries_by_repository_creation_not_last_edit():
    # moonshotai/Kimi-K3 (2026-11-23): an edit in November put a June model first in the list.
    payload = json.dumps([{"id": "owner/old-model", "createdAt": "2026-06-13T06:42:57.000Z",
                           "lastModified": "2026-11-20T02:36:10.000Z"}]).encode()

    async def card(url, hosts):
        return ("# Old model\nA model card that was edited recently.\n" * 50).encode()

    rows = asyncio.run(hub_models(source("hub_models", organization="owner"), payload, 3, card))
    assert rows[0].published_at.startswith("2026-06-13")
    catalog = {"success": True, "data": {"models": [{"id": "owner/model", "created_at": "2026-08-12T09:25:21Z",
                                                     "last_modified": "2026-11-08", "private": False}]}}
    rows = parse(source("modelscope_models", organization="owner"), json.dumps(catalog).encode(), 3)
    assert rows[0].published_at.startswith("2026-08-12")


def test_paper_indexes_do_not_promote_curation_time_or_private_reviews():
    rows = parse(source("daily_papers"), json.dumps([{"publishedAt":"2026-11-08", "paper":{
        "id":"2611.00001", "title":"Research", "summary":"Original abstract.", "publishedAt":"2026-11-01"}}]).encode(), 3)
    assert rows[0].content_kind == "index_abstract" and rows[0].published_at == "2026-11-01"
    data = {"notes":[{"id":"public", "readers":["everyone"], "cdate":123, "content":{
        "title":{"value":"Public paper"}, "abstract":{"value":"Public abstract."}}},
        {"id":"private", "readers":["a/private/group"], "content":{"title":{"value":"Private"}}}]}
    rows = parse(source("openreview"), json.dumps(data).encode(), 3)
    assert len(rows) == 1 and rows[0].title == "Public paper" and rows[0].published_at is None


def test_benchmark_excerpts_keep_checks_conditions_and_stable_versions():
    board = {"leaderboards":[{"name":"Verified","results":[{
        "name":"Submitted agent", "date":"2026-11-01", "resolved":70.2,"checked":False,
        "tags":["Attempts - 1"],"warning":"Different harness","per_instance_details":"not needed"}]}]}
    config = source("swebench", original_url="https://example.org/leaderboard")
    result = parse(config,json.dumps(board).encode(),1)[0]
    assert result.content_kind == "benchmark_snapshot" and result.published_at is None
    assert '"checked": false' in result.text and "Different harness" in result.text and "per_instance_details" not in result.text
    assert parse(config,json.dumps(board).encode(),1)[0].version == result.version
    arena = {"rows":[{"row":{"model_name":"Atlas","category":"overall","rating":1000,
                              "rating_lower":950,"vote_count":500,"leaderboard_publish_date":"2026-11-02"}},
                     {"row":{"model_name":"Other category","category":"math"}}]}
    result = parse(source("arena",original_url="https://example.org/arena"),json.dumps(arena).encode(),1)[0]
    assert result.published_at.startswith("2026-11-02") and '"rating_lower": 950' in result.text
    assert "Other category" not in result.text


def test_collection_reports_denial_without_blocking_other_sources(tmp_path,monkeypatch):
    from northing_signal.briefing import collect as collection

    async def read(config,limit):
        if config["id"] == "denied":
            raise httpx.HTTPStatusError("do not log body", request=httpx.Request("GET","https://example.org/"), response=httpx.Response(403))
        return [Material(id="lead",source_id="ok",source_name="Fixture",source_role="official",
                         title="New model",url="https://example.org/model",text="",content_kind="search_excerpt")]

    monkeypatch.setattr(collection,"read_source",read)
    store=Store(tmp_path / "isolation.db")
    asyncio.run(collect(store,[{"id":"denied","name":"Denied"},{"id":"ok","name":"OK"}],limit=1))
    states=store.source_states()
    assert states["denied"]["http_status"]==403 and "do not log body" not in json.dumps(states)
    assert states["ok"]["count"]==1 and states["ok"]["with_text"]==0 and len(store.materials())==1


def test_public_get_proxy_denial_stops_without_another_route(monkeypatch):
    from northing_signal.briefing import collect as collection
    client_type = httpx.AsyncClient
    requests = []

    async def addresses(url):
        yield "8.8.8.8"
        raise AssertionError("Proxy denial must not try another address or resolver")

    def reply(request):
        requests.append(request)
        raise httpx.ProxyError("denied", request=request)

    def client(**kwargs):
        assert kwargs["trust_env"] is True
        return client_type(transport=httpx.MockTransport(reply), **kwargs)

    monkeypatch.setattr(collection, "connection_addresses", addresses)
    monkeypatch.setattr(collection, "OriginTLS", lambda host: True)
    monkeypatch.setattr(collection.httpx, "AsyncClient", client)
    async def scenario():
        try:
            await collection.fetch("https://example.org/feed", {"example.org"})
        except httpx.ProxyError:
            return
        raise AssertionError("Expected proxy denial")
    asyncio.run(scenario())
    assert len(requests) == 1 and requests[0].headers["host"] == "example.org"


def test_arxiv_fixed_feeds_and_discovery_share_serial_request_spacing(monkeypatch):
    from northing_signal.briefing import collect as collection
    clock = [0.0]
    calls = []
    active = [0]
    original_sleep = asyncio.sleep

    async def sleep(seconds):
        clock[0] += seconds
        await original_sleep(0)

    async def request(url, hosts, **kwargs):
        active[0] += 1
        assert active[0] == 1
        calls.append(clock[0])
        await original_sleep(0)
        active[0] -= 1
        return b"public abstract"

    monkeypatch.setattr(collection, "monotonic", lambda: clock[0])
    monkeypatch.setattr(collection.asyncio, "sleep", sleep)
    monkeypatch.setattr(collection, "_fetch", request)
    async def scenario():
        await asyncio.gather(collection.fetch("https://export.arxiv.org/api/query", {"export.arxiv.org"}),
                             collection.fetch("https://rss.arxiv.org/rss/cs.AI", {"rss.arxiv.org"}))
    asyncio.run(scenario())
    assert calls == [0.0, 3.0]


def test_every_model_catalog_is_told_a_card_is_not_a_launch():
    from northing_signal.briefing.understand import PROMPT, is_model_card
    from test_reader import material as fixture
    assert is_model_card(fixture(source_id="hf-kimi")) and is_model_card(fixture(source_id="modelscope-qwen"))
    assert is_model_card(fixture(source_id="huggingface-discovery"))
    assert not is_model_card(fixture(source_id="hf-daily-papers")) and not is_model_card(fixture(source_id="openai"))
    # The title rules that keep explainers, past launches and model cards from reading as releases.
    assert "不改写成发布" in PROMPT and "本身不证明刚发布" in PROMPT


def test_update_blocks_are_split_by_day_and_same_day_blocks_join():
    """Zhipu (Mintlify ids) and Alibaba Cloud Model Studio (date at the block's start)."""
    text = b"A new flagship model is available with stated conditions. " * 3
    mintlify = (b'<main><div class="update flex" id="2026-8-19"><p>' + text + b'</p></div>'
                b'<div class="update" id="2026-06-16"><p>' + text + b'</p></div>'
                b'<div class="update" id="notes"><p>' + text + b'</p></div></main>')
    rows = parse(source("updates"), mintlify, 5)
    assert [r.published_at[:10] for r in rows] == ["2026-08-19", "2026-06-16"]
    assert rows[0].title == "Fixture · 2026-08-19" and rows[0].content_kind == "publisher_excerpt"
    alibaba = (b'<div class="rkb-update"><div class="rkb-update-meta"><h3>2026-11-16</h3></div>'
               b'<div class="rkb-update-body">qwen4-max ' + text + b'</div></div>'
               b'<div class="rkb-update"><div class="rkb-update-meta"><h3>2026-11-16</h3></div>'
               b'<div class="rkb-update-body">mindlab/macaron ' + text + b'</div></div>')
    joined = parse(source("updates", block="rkb-update"), alibaba, 5)
    assert len(joined) == 1 and "qwen4-max" in joined[0].text and "mindlab/macaron" in joined[0].text


def test_general_newsrooms_keep_only_ai_entries():
    feed = (b'<rss><channel>'
            b'<item><title>Formula 1 streams live this weekend</title><link>https://example.org/news/f1</link>'
            b'<description>Racing on TV.</description><pubDate>Mon, 23 Nov 2026 10:00:00 GMT</pubDate></item>'
            b'<item><title>Siri AI comes to more languages</title><link>https://example.org/news/siri</link>'
            b'<description>Assistant update.</description><pubDate>Mon, 23 Nov 2026 11:00:00 GMT</pubDate></item>'
            b'</channel></rss>')
    rows = parse(source("rss", require=r"(?i)\b(AI|Siri)\b"), feed, 5)
    assert [r.url for r in rows] == ["https://example.org/news/siri"]
    assert len(parse(source("rss"), feed, 5)) == 2
