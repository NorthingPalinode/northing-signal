"""Scheduled updates, "new" marks, known-on-open and the weekly report (2026-11-11)."""

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from northing_signal.briefing.engine import project
from northing_signal.briefing.models import Interaction, Preferences
from northing_signal.briefing.report import report_range, weekly_report
from northing_signal.briefing.service import ContentService, refresh_slots
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings

SHANGHAI = ZoneInfo("Asia/Shanghai")


def local(*args):
    return datetime(*args, tzinfo=SHANGHAI)


def two_events():
    old = material(id="old", captured_at="2026-11-01T01:00:00+00:00")
    fresh = material(id="fresh", url="https://example.org/fresh", captured_at="2026-11-02T05:00:00+00:00",
                     published_at="2026-11-02T04:00:00+00:00")
    judgments = {old.version: assessment().model_dump(),
                 fresh.version: assessment(subject="Nova", object="Nova 1", event_key="nova-1",
                                           title="Nova 1 发布").model_dump()}
    return [old, fresh], judgments


def test_known_while_reading_greys_the_story_but_keeps_this_briefing_stable():
    items, judgments = two_events()
    clock = "2026-11-02T06:00:00+00:00"
    base = project(items, judgments, Preferences(), as_of=clock)
    event = next(e for e in base["events"] if e["title"] == "Atlas 2 发布")
    assert event["id"] in base["focus"]
    known = dict(request_id="known-0001", event_id=event["id"], version=event["version"], kind="known",
                 at="2026-11-02T05:30:00+00:00")
    # Marked after the latest update finished: still in this briefing, shown as known.
    reading = project(items, judgments, Preferences(), [known], as_of=clock,
                      briefing_at="2026-11-02T05:10:00+00:00")
    again = next(e for e in reading["events"] if e["id"] == event["id"])
    assert again["known"] and not again["known_earlier"] and event["id"] in reading["focus"]
    # The next update settles it: known stories leave the focus.
    later = project(items, judgments, Preferences(), [known], as_of=clock,
                    briefing_at="2026-11-02T05:45:00+00:00")
    assert event["id"] not in later["focus"]
    # Without update history (older databases) a known story leaves at once, as before.
    assert event["id"] not in project(items, judgments, Preferences(), [known], as_of=clock)["focus"]


def test_new_and_updated_follow_the_latest_update():
    items, judgments = two_events()
    follow_up = material(id="old-test", url="https://example.org/old-test", captured_at="2026-11-02T05:05:00+00:00",
                         text="Atlas 2 is available. Free for research. Independent test.")
    judgments[follow_up.version] = assessment(action="test").model_dump()
    value = project([*items, follow_up], judgments, Preferences(), as_of="2026-11-02T06:00:00+00:00",
                    new_since="2026-11-02T05:00:00+00:00")
    flags = {e["title"]: (e["new"], e["updated"]) for e in value["events"]}
    assert flags["Nova 1 发布"] == (True, False)
    assert flags["Atlas 2 发布"] == (False, True)
    assert value["counts"]["new"] == 1
    plain = project(items, judgments, Preferences(), as_of="2026-11-02T06:00:00+00:00")
    assert not any(e["new"] or e["updated"] for e in plain["events"]) and plain["counts"]["new"] == 0


def test_refresh_slots_are_midnight_and_noon_in_reader_time():
    assert refresh_slots(local(2026, 11, 11, 5, 30), SHANGHAI) == (local(2026, 11, 11, 0), local(2026, 11, 11, 12))
    assert refresh_slots(local(2026, 11, 11, 12, 0), SHANGHAI) == (local(2026, 11, 11, 12), local(2026, 11, 12, 0))
    assert refresh_slots(local(2026, 11, 11, 23, 59), SHANGHAI) == (local(2026, 11, 11, 12), local(2026, 11, 12, 0))


def test_scheduled_update_runs_once_per_slot_and_can_be_turned_off(tmp_path, monkeypatch):
    async def collect_nothing(*args, **kwargs):
        return []
    monkeypatch.setattr("northing_signal.briefing.service.collect", collect_nothing)
    monkeypatch.setattr("northing_signal.briefing.service.enrich", collect_nothing)

    async def scenario():
        store = Store(tmp_path / "reader.db")
        service = ContentService(store, settings(reader_timezone="Asia/Shanghai"))
        now = datetime.now(timezone.utc)
        # Nothing has run yet: the latest slot was missed, so the check catches up once.
        run = service.refresh_due(now)
        assert run and run["trigger"] == "scheduled" and not run["manual"]
        assert service.refresh_due(now) is None  # already running
        await service.task
        last = store.last_refresh(completed=True)
        assert last["id"] == run["id"] and last["trigger"] == "scheduled" and last["finished_at"]
        assert service.refresh_due(now) is None  # this slot is done
        _, upcoming = refresh_slots(now, SHANGHAI)
        nxt = service.refresh_due(upcoming)
        assert nxt and nxt["id"] != run["id"]
        await service.task
        store.save_preferences(Preferences(auto_refresh=False))
        _, after = refresh_slots(upcoming, SHANGHAI)
        assert service.refresh_due(after) is None
        view = service.view()
        assert view["last_refresh"]["id"] == nxt["id"] and view["schedule"]["enabled"] is False
        assert [r["trigger"] for r in store.refreshes()] == ["scheduled", "scheduled"]
        assert store.snapshots()[0]["trigger"] == "scheduled" and store.snapshots()[0]["kind"] == "refresh"
    asyncio.run(scenario())


def test_opening_marks_known_once_and_respects_taking_it_back(tmp_path):
    store = Store(tmp_path / "reader.db")
    item = material()
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment().model_dump(), "fixture")
    service = ContentService(store, settings())
    event = service.view()["events"][0]
    assert not event["known"]

    def act(request_id, kind, **extra):
        return service.record_interaction(Interaction(request_id=request_id, event_id=event["id"],
                                                      version=event["version"], kind=kind, **extra))

    act("opened-0001", "opened")
    assert service.view()["events"][0]["known"]
    auto = next(a for a in store.interactions(["known"]))
    act("retract-0001", "retract", retracts=auto["request_id"])
    assert not service.view()["events"][0]["known"]
    act("opened-0002", "opened")  # reopening keeps the reader's choice
    assert not service.view()["events"][0]["known"]
    act("opened-0002", "opened")  # an idempotent repeat adds nothing either
    assert len(store.interactions(["known"])) == 1


def test_weekly_report_lists_the_range_by_importance_and_topic():
    clock = datetime(2026, 11, 11, 4, tzinfo=timezone.utc)
    start, end = report_range("recent", clock, SHANGHAI)
    assert (start, end) == (local(2026, 11, 5), local(2026, 11, 12))
    assert report_range("last_week", clock, SHANGHAI) == (local(2026, 11, 2), local(2026, 11, 9))

    def event(key, **changes):
        value = dict(id=key, title=f"事件 {key}", summary="摘要。", reason="原因。", topic="models",
                     url=f"https://example.org/{key}", source="Fixture", source_count=1, source_role="official",
                     evidence="source_attributed", content_kind="publisher_excerpt", qualified=True,
                     dismissed=False, protected=False, score=10, published_at="2026-11-10T02:00:00+00:00",
                     captured_at="2026-11-10T03:00:00+00:00", actions=[])
        return {**value, **changes}

    events = [event("a", score=20), event("b", topic="agents", evidence="reported_test", content_kind=None),
              event("old", published_at="2026-10-01T00:00:00+00:00"), event("hidden", dismissed=True),
              event("weak", qualified=False),
              event("saved", published_at="2026-10-20T00:00:00+00:00",
                    actions=[{"kind": "saved", "at": "2026-11-09T00:00:00+00:00"}])]
    follows = [{"name": "Agent 工程", "event_ids": ["b", "old"]}]
    report = weekly_report(events, follows, start, end, generated_at=clock, zone=SHANGHAI)
    text = report["markdown"]
    assert report["count"] == 2 and report["filename"] == "northing-signal-weekly-2026-11-05.md"
    assert "2026-11-05 至 2026-11-11" in text
    top = text.split("## 按方向")[0]
    assert top.index("事件 a") < top.index("事件 b")
    assert "### 模型与多模态（1）" in text and "### Agent 与开发（1）" in text
    assert "文中报告测试" in text and "原文陈述" in text
    assert "事件 old" not in text and "事件 hidden" not in text and "事件 weak" not in text
    assert "## 本周收藏" in text and "事件 saved" in text
    assert "Agent 工程：1 项相关进展" in text
    empty = weekly_report([], [], start, end, generated_at=clock, zone=SHANGHAI)
    assert empty["count"] == 0 and "没有整理好的进展" in empty["markdown"]


def test_weekly_report_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from northing_signal.briefing.app import create_app
    store = Store(tmp_path / "reader.db")
    with TestClient(create_app(settings(), store)) as client:
        body = client.get("/api/reader/reports/weekly?range=last_week").json()
        assert body["count"] == 0 and body["markdown"].startswith("# Northing Signal 周报")
        assert client.get("/api/reader/reports/weekly?range=year").status_code == 422


def test_late_and_undated_reports_are_archived_not_news():
    # Kimi K3 (2026-11-23): a June model card collected in November must not read as today's news.
    from northing_signal.briefing.engine import timely
    clock = "2026-11-02T06:00:00+00:00"
    card = material(id="card", url="https://example.org/card", published_at=None,
                    captured_at="2026-11-02T05:00:00+00:00", text="Nova 1 model card.")
    late = material(id="late", url="https://example.org/late", published_at="2026-10-20T00:00:00+00:00",
                    captured_at="2026-11-02T05:00:00+00:00", text="Vega 2 is available.")
    fresh = material(id="fresh", url="https://example.org/fresh", captured_at="2026-11-02T05:00:00+00:00",
                     published_at="2026-11-02T04:00:00+00:00", text="Orion 3 is available.")
    judgments = {card.version: assessment(subject="Nova", object="Nova 1", event_key="nova-1",
                                          title="Nova 1 发布").model_dump(),
                 late.version: assessment(subject="Vega", object="Vega 2", event_key="vega-2",
                                          title="Vega 2 发布").model_dump(),
                 fresh.version: assessment(subject="Orion", object="Orion 3", event_key="orion-3",
                                           title="Orion 3 发布").model_dump()}
    value = project([card, late, fresh], judgments, Preferences(), as_of=clock,
                    new_since="2026-11-02T04:30:00+00:00")
    events = {e["title"]: e for e in value["events"]}
    assert events["Nova 1 发布"]["stale_reason"] == "undated" and events["Vega 2 发布"]["stale_reason"] == "late"
    assert events["Orion 3 发布"]["timely"] and events["Orion 3 发布"]["new"]
    shown = set(value["focus"]) | set(value["radar"])
    assert shown == {events["Orion 3 发布"]["id"]}
    assert not events["Nova 1 发布"]["new"] and not events["Vega 2 发布"]["new"]  # no 【新】 for late finds
    # Days the service was off do not make their news old: the window starts at the update before.
    off = material(published_at="2026-10-28T00:00:00+00:00", captured_at="2026-11-02T05:00:00+00:00")
    assert not timely(off)
    assert timely(off, refreshed=[stamp_("2026-10-27T12:00:00+00:00")])
    # A curated list that lags by nature gets its own window.
    paper = material(published_at="2026-10-29T00:00:00+00:00", captured_at="2026-11-02T05:00:00+00:00")
    assert not timely(paper) and timely(paper, hours=168)


def test_an_old_report_found_late_does_not_mark_an_event_updated():
    first = material(id="first", captured_at="2026-11-01T01:00:00+00:00")
    old_copy = material(id="old-copy", url="https://example.org/old-copy", source_id="blog", source_name="Blog",
                        published_at="2026-09-01T00:00:00+00:00", captured_at="2026-11-02T05:10:00+00:00",
                        text="Atlas 2 is available. Free for research. A blog recap.")
    judgments = {first.version: assessment().model_dump(), old_copy.version: assessment().model_dump()}
    value = project([first, old_copy], judgments, Preferences(), as_of="2026-11-02T06:00:00+00:00",
                    new_since="2026-11-02T05:00:00+00:00")
    event = value["events"][0]
    assert event["report_count"] == 2 and event["timely"] and not event["updated"]


def stamp_(value):
    from northing_signal.briefing.engine import stamp
    return stamp(value)
