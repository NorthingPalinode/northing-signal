"""AIHOT 精选摘要 (2026-11-25, owner's choice A): picks with a readable original are leads on that
original; picks from X or WeChat keep AIHOT's summary as a labelled second-hand source that may
fill the radar but never focus, never counts as another outlet and is never republished."""

import asyncio
from datetime import datetime, timezone

from northing_signal.briefing.collect import collect
from northing_signal.briefing.engine import RETURN_SOURCES, project
from northing_signal.briefing.models import Preferences
from northing_signal.briefing.publish import public_events
from northing_signal.briefing.source_adapters import aihot_picks
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import has_material
from test_carried import CLOCK, CURRENT, FINISHED, PREVIOUS, SEEN, report
from test_reader import assessment

SOURCE = {"id": "aihot-selected", "name": "AIHOT · 精选摘要", "role": "community", "url": "https://aihot.news/feed.xml",
          "hosts": ["aihot.news"], "kind": "aihot", "max_items": 50}


def item(guid, title, original, author, summary="Atlas 2 已开放。", date="Wed, 25 Nov 2026 07:30:08 GMT"):
    return (f"<item><title>{title}</title><link>https://aihot.news/items/{guid}</link>"
            f"<description>&lt;p&gt;{summary}&lt;/p&gt;&lt;p&gt;🔗 &lt;a href=\"{original}\"&gt;阅读原文&lt;/a&gt;&lt;/p&gt;"
            f"&lt;p&gt;via AIHOT · &lt;a href=\"https://aihot.news/items/{guid}\"&gt;link&lt;/a&gt;&lt;/p&gt;</description>"
            f"<pubDate>{date}</pubDate><guid isPermaLink=\"false\">{guid}</guid>"
            f"<author>noreply@aihot.news ({author})</author></item>")


FEED = ("<rss version=\"2.0\"><channel>"
        + item("g1", "Atlas 2 在 X 上公布", "https://x.com/atlas/status/1", "Atlas Lab")
        + item("g2", "公众号介绍 Atlas 2", "https://mp.weixin.qq.com/s/abc", "公众号：Atlas")
        + item("g3", "OpenAI 发布 Atlas 2", "https://openai.com/index/atlas-2/", "OpenAI：官网动态")
        + item("g4", "媒体报道 Atlas 2", "https://example.org/news/atlas-2", "Example News")
        + "</channel></rss>").encode()


def test_picks_split_by_whether_the_original_can_be_read():
    rows = aihot_picks({**SOURCE, "known_hosts": {"openai.com": "official"}}, FEED, 50)
    assert [(r.content_kind, r.source_role) for r in rows] == [
        ("curated_summary", "author"), ("curated_summary", "author"),
        ("search_excerpt", "official"), ("search_excerpt", "media")]
    x, _, official, _ = rows
    # The original is the material's address; AIHOT's page is where it was found.
    assert x.url == "https://x.com/atlas/status/1" and x.discovery_url == "https://aihot.news/items/g1"
    assert x.source_name == "Atlas Lab · 经 AIHOT 精选" and x.text == "Atlas 2 已开放。"
    assert x.published_at.startswith("2026-11-25T07:30:08")
    # Only the unreadable ones are judged from AIHOT's words; the rest wait for their original.
    assert has_material(x) and not has_material(official)


def test_registered_official_sites_keep_their_role_through_collect(tmp_path, monkeypatch):
    store = Store(tmp_path / "reader.db")
    openai = {"id": "openai", "name": "OpenAI", "role": "official", "url": "https://openai.com/news/rss.xml",
              "hosts": ["openai.com"], "kind": "rss"}

    async def fetch(url, hosts, **_):
        if "aihot" in url:
            return FEED
        raise ValueError("offline")

    monkeypatch.setattr("northing_signal.briefing.collect.fetch", fetch)
    asyncio.run(collect(store, [openai, SOURCE]))
    roles = {m.url: m.source_role for m in store.materials()}
    assert roles["https://openai.com/index/atlas-2/"] == "official"
    assert roles["https://example.org/news/atlas-2"] == "media"


def curated(name, **changes):
    value = report(name, **changes)
    return value.model_copy(update={"content_kind": "curated_summary", "source_id": "aihot-selected",
                                    "discovery_url": f"https://aihot.news/items/{name}"})


def view(materials, **judged):
    judgments = {m.version: assessment(**judged).model_dump() for m in materials}
    return project(materials, judgments, Preferences(), as_of=CLOCK, briefing_at=FINISHED, new_since=CURRENT,
                   refreshed=[PREVIOUS])


def test_a_story_known_only_from_aihot_summaries_never_leads():
    value = view([curated("x-post")])
    event = value["events"][0]
    assert event["qualified"] and event["curated_only"] and event["aihot"]
    assert event["id"] not in value["focus"] and event["id"] in value["radar"]
    assert event["standing"].startswith("仅有 AIHOT 精选摘要，未读到原文")
    assert event["timeline"][0]["via"] == "https://aihot.news/items/x-post"
    assert any("AIHOT" in line for line in event["limitations"])
    # A correction told only by a second-hand summary does not stand above everything.
    assert not view([curated("x-post")], action="correction")["events"][0]["protected"]
    # With a report we could read, it is an ordinary story again (still marked as an AIHOT pick).
    mixed = view([curated("x-post"), report("wire")])
    assert not mixed["events"][0]["curated_only"] and mixed["events"][0]["aihot"]
    assert mixed["events"][0]["id"] in mixed["focus"]


def test_aihot_is_not_one_more_outlet_for_a_carried_story():
    later = dict(published="2026-11-20T19:00:00+00:00", captured="2026-11-20T20:00:00+00:00")
    reports = [report("wire"), *[report(f"outlet{i}", **later) for i in range(RETURN_SOURCES - 1)],
               curated("pick", **later)]
    judgments = {m.version: assessment().model_dump() for m in reports}
    first = project(reports, judgments, Preferences(), as_of=CLOCK, briefing_at=FINISHED, new_since=CURRENT,
                    refreshed=[PREVIOUS])["events"][0]
    shown = [dict(request_id="shown-0001", event_id=first["id"], version=first["version"], kind="shown", at=SEEN)]
    value = project(reports, judgments, Preferences(), shown, as_of=CLOCK, briefing_at=FINISHED, new_since=CURRENT,
                    refreshed=[PREVIOUS], briefed={first["id"]})
    assert value["events"][0]["carried"]


def test_the_public_digest_never_republishes_another_site_summary():
    clock = datetime.fromisoformat(CLOCK)
    since = datetime(2026, 11, 19, tzinfo=timezone.utc)
    only = view([curated("x-post")])["events"]
    assert public_events(only, since, clock) == []
    assert public_events(view([report("wire")])["events"], since, clock)
