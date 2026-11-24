"""Public digest: static HTML + RSS from a neutral projection (2026-11-23)."""

import asyncio
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from northing_signal.briefing.models import Interaction
from northing_signal.briefing.publish import safe_url
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings


def at(day, hour=0):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def add(store, item, **judged):
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment(**judged).model_dump(), "fixture")


def make(tmp_path, **changes):
    store = Store(tmp_path / "reader.db")
    service = ContentService(store, settings(reader_timezone="Asia/Shanghai", **changes))
    return store, service


def test_reader_actions_never_reach_the_public_digest(tmp_path):
    store, service = make(tmp_path)
    add(store, material())
    event = service.view()["events"][0]
    for request_id, kind in [("saved-0001", "saved"), ("irrelevant-0001", "irrelevant"), ("known-0001", "known")]:
        service.record_interaction(Interaction(request_id=request_id, event_id=event["id"],
                                               version=event["version"], kind=kind))
    out = tmp_path / "site"
    result = service.publish_digest(out, clock=at(2, 0))
    assert result["count"] == 1  # dismissed and known by the owner, still public
    edition = json.loads(next((out / "editions").glob("*.json")).read_text("utf-8"))
    entry = edition["events"][0]
    assert entry["title"] == "Atlas 2 发布" and entry["url"] == "https://example.org/atlas"
    assert not {"actions", "saved", "known", "dismissed", "score", "claims", "timeline"} & set(entry)
    page = (out / "index.html").read_text("utf-8")
    assert "Atlas 2 is available." not in page  # original quotes and excerpts stay local
    assert "Atlas 2 发布" in page and "<h2>头条</h2>" in page


def test_each_edition_holds_only_what_arrived_since_the_last_one(tmp_path):
    store, service = make(tmp_path)
    out = tmp_path / "site"
    add(store, material())
    first = service.publish_digest(out, clock=at(2, 0))
    assert first["edition"] == "2026-11-02-0800" and first["count"] == 1  # Asia/Shanghai edition time
    again = service.publish_digest(out, clock=at(2, 4))
    assert again["edition"] is None and again["count"] == 0  # nothing new: no empty edition
    add(store, material(id="nova", url="https://example.org/nova", captured_at="2026-11-02T06:00:00+00:00",
                        published_at="2026-11-02T05:00:00+00:00", text="Nova 1 is available."),
        subject="Nova", object="Nova 1", event_key="nova-1", title="Nova 1 发布")
    add(store, material(id="atlas-test", url="https://example.org/atlas-test", source_id="lab", source_name="Lab",
                        source_role="research", captured_at="2026-11-02T07:00:00+00:00",
                        published_at="2026-11-02T06:30:00+00:00", text="Atlas 2 is available. Independent test."),
        action="test", evidence="reported_test")
    second = service.publish_digest(out, clock=at(2, 12))
    assert second["count"] == 2
    edition = json.loads((out / "editions" / f"{second['edition']}.json").read_text("utf-8"))
    status = {e["title"]: e["status"] for e in edition["events"]}
    # Atlas was in the first edition: its new test report makes it a follow-up, still in the
    # main list because the lab's own test is a party action.
    assert status == {"Nova 1 发布": "new", "Atlas 2 发布": "followup"}
    atlas = next(e for e in edition["events"] if e["title"] == "Atlas 2 发布")
    assert atlas["source_count"] == 2 and len(atlas["sources"]) == 2
    index = (out / "index.html").read_text("utf-8")
    assert "2026年11月2日 20:00 版" in index and "editions/2026-11-02-0800.html" in index  # earlier edition linked
    assert (out / "editions" / "2026-11-02-0800.html").exists() and (out / ".nojekyll").exists()


def test_old_stories_collected_late_are_not_news(tmp_path):
    store, service = make(tmp_path)
    add(store, material(published_at="2026-10-01T00:00:00+00:00", captured_at="2026-11-01T01:00:00+00:00"))
    assert service.publish_digest(tmp_path / "site", clock=at(2, 0))["count"] == 0


def test_pages_escape_text_and_drop_unsafe_links(tmp_path):
    store, service = make(tmp_path, reader_public_url="https://reader.example/daily")
    add(store, material(), title="<script>alert(1)</script> 发布",
        summary="A & B <b>bold</b>")
    out = tmp_path / "site"
    service.publish_digest(out, clock=at(2, 0))
    page = (out / "index.html").read_text("utf-8")
    assert "<script>alert" not in page and "&lt;script&gt;" in page and "&lt;b&gt;bold" in page
    feed = ET.fromstring((out / "feed.xml").read_text("utf-8"))
    items = feed.findall("./channel/item")
    assert len(items) == 1
    assert items[0].findtext("link") == "https://reader.example/daily/editions/2026-11-02-0800.html"
    assert "&lt;script&gt;" in items[0].findtext("description")  # still escaped once decoded from XML


def test_only_web_links_are_published():
    assert safe_url("https://example.org/a") == "https://example.org/a"
    assert safe_url("javascript:alert(1)") == safe_url("data:text/html,x") == safe_url(None) == ""


def test_completed_update_publishes_when_a_directory_is_set(tmp_path, monkeypatch):
    async def collect_nothing(*args, **kwargs):
        return []
    monkeypatch.setattr("northing_signal.briefing.service.collect", collect_nothing)
    monkeypatch.setattr("northing_signal.briefing.service.enrich", collect_nothing)
    out = tmp_path / "public"
    store, service = make(tmp_path, reader_publish_dir=str(out))
    now = datetime.now(timezone.utc).isoformat()
    add(store, material(published_at=now, captured_at=now))

    async def scenario():
        from northing_signal.briefing.models import RefreshRequest
        run = service.start(RefreshRequest())
        await service.task
        return run
    run = asyncio.run(scenario())
    assert run["state"] == "completed" and run["published_edition"] and not run["errors"]
    assert (out / "index.html").exists() and (out / "feed.xml").exists()


def test_publishing_without_a_directory_is_refused(tmp_path):
    _, service = make(tmp_path)
    try:
        service.publish_digest()
    except ValueError as error:
        assert "READER_PUBLISH_DIR" in str(error)
    else:
        raise AssertionError("expected a refusal")


def test_undated_stories_are_not_published_as_news(tmp_path):
    store, service = make(tmp_path)
    add(store, material(published_at=None))
    assert service.publish_digest(tmp_path / "site", clock=at(2, 0))["count"] == 0


def story(key, *, score=20, source="Outlet", repeat_party=None, sources=1, official=False, heat=1):
    """A projected event as the digest sees it."""
    timeline = [{"source": source, "role": "official" if official else "media", "url": f"https://example.org/{key}",
                 "published_at": "2026-11-02T05:00:00+00:00", "captured_at": "2026-11-02T06:00:00+00:00",
                 "action": repeat_party or "release"}]
    return {"id": key, "version": key, "title": key, "summary": "", "reason": "", "topic": "models",
            "topic_label": "模型与多模态", "qualified": True, "timely": True, "protected": False,
            "score": score, "heat": heat, "source": source, "source_id": source, "source_count": sources,
            "url": f"https://example.org/{key}", "published_at": "2026-11-02T05:00:00+00:00",
            "latest_captured_at": "2026-11-02T06:00:00+00:00", "first_captured_at": "2026-11-02T06:00:00+00:00",
            "timeline": timeline, "limitations": [], "action": "release", "evidence": "source_attributed"}


def test_editorial_rules_cap_outlets_and_keep_repeats_out_of_the_main_list():
    from northing_signal.briefing.publish import MAIN_LIMIT, QUICK_LIMIT, compose
    since, clock = at(2, 0), at(2, 12)
    events = [story("seen-again", score=40), story("seen-party", score=39, official=True, repeat_party="test"),
              story("seen-wide", score=38, sources=4)]
    events += [story(f"a{i}", score=30 - i, source="Big outlet") for i in range(3)]
    events += [story(f"n{i}", score=20 - i, source=f"Outlet {i}") for i in range(14)]
    placed = {e["id"]: (section, followup) for e, section, followup in
              compose(events, since, clock, recent_ids={"seen-again", "seen-party", "seen-wide"})}
    # Reported recently: back in the main list only on the party's own action or wide coverage.
    assert placed["seen-again"] == ("quick", True)
    assert placed["seen-party"] == ("main", True) and placed["seen-wide"] == ("main", True)
    # One outlet at most twice in the main list; its third story waits in the quick list.
    assert [placed[f"a{i}"][0] for i in range(3)] == ["main", "main", "quick"]
    sections = [section for section, _ in placed.values()]
    assert sections.count("main") == MAIN_LIMIT and sections.count("quick") == QUICK_LIMIT


def test_an_edition_reads_as_headline_highlights_and_quick_items(tmp_path):
    from northing_signal.briefing.publish import publish
    events = [story(f"n{i}", score=30 - i, source=f"Outlet {i}") for i in range(16)]
    out = tmp_path / "site"
    assert publish(events, out, clock=at(2, 12))["count"] == 15
    page = (out / "index.html").read_text("utf-8")
    order = [page.index(h) for h in ("<h2>头条</h2>", "<h2>今日看点</h2>", "模型与多模态（6）", "快讯（5）")]
    assert order == sorted(order)
