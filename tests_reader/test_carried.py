"""Carried stories (2026-11-25, after AIHOT's daily edition): an event an earlier briefing put in
focus or radar, seen there and not opened, does not take a briefing place again without news."""

from datetime import datetime, timedelta, timezone

from northing_signal.briefing.engine import CARRIED_PENALTY, RETURN_SOURCES, project
from northing_signal.briefing.models import Preferences
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from test_reader import assessment, material, settings

PREVIOUS = "2026-11-20T12:00:00+00:00"   # the earlier briefing
CURRENT = "2026-11-21T00:00:00+00:00"    # this briefing's update began
FINISHED = "2026-11-21T00:10:00+00:00"
SEEN = "2026-11-20T13:00:00+00:00"       # the reader saw the story in the earlier briefing
CLOCK = "2026-11-21T01:00:00+00:00"


def report(name, role="media", published="2026-11-20T08:00:00+00:00", captured="2026-11-20T09:00:00+00:00"):
    return material(id=name, source_id=name, source_name=name, source_role=role, url=f"https://example.org/{name}",
                    text=f"{name} reports that Atlas 2 is available.", published_at=published, captured_at=captured)


def briefing(materials, shown_at=None, briefed=True):
    judgments = {m.version: assessment().model_dump() for m in materials}
    plain = project(materials, judgments, Preferences(), as_of=CLOCK, briefing_at=FINISHED, new_since=CURRENT,
                    refreshed=[PREVIOUS])
    event = plain["events"][0]
    actions = [] if not shown_at else [dict(request_id="shown-0001", event_id=event["id"], version=event["version"],
                                             kind="shown", at=shown_at)]
    value = project(materials, judgments, Preferences(), actions, as_of=CLOCK, briefing_at=FINISHED,
                    new_since=CURRENT, refreshed=[PREVIOUS], briefed={event["id"]} if briefed else set())
    return plain, value


def test_a_story_seen_in_an_earlier_briefing_waits_in_more_with_a_lower_score():
    plain, value = briefing([report("wire")], shown_at=SEEN)
    before, after = plain["events"][0], value["events"][0]
    assert before["id"] in plain["focus"] and not before["carried"]
    assert after["carried"] and after["qualified"] and after["timely"]
    assert after["id"] not in value["focus"] + value["radar"]
    assert after["score"] == before["score"] - CARRIED_PENALTY


def test_only_a_story_the_reader_saw_in_an_earlier_briefing_is_carried():
    # Never on screen: the reader did not come, so it still has its place.
    assert briefing([report("wire")])[1]["events"][0]["id"] in briefing([report("wire")])[1]["focus"]
    # In no earlier briefing (seen in a search or a roadmap): not carried.
    assert not briefing([report("wire")], shown_at=SEEN, briefed=False)[1]["events"][0]["carried"]
    # Seen while reading this briefing: the briefing does not reshuffle under the reader.
    assert not briefing([report("wire")], shown_at="2026-11-21T00:30:00+00:00")[1]["events"][0]["carried"]


def test_an_official_report_or_enough_new_outlets_bring_it_back():
    later = dict(published="2026-11-20T19:00:00+00:00", captured="2026-11-20T20:00:00+00:00")
    official = briefing([report("wire"), report("lab", role="official", **later)], shown_at=SEEN)[1]
    assert not official["events"][0]["carried"] and official["events"][0]["id"] in official["focus"]
    few = [report(f"outlet{i}", **later) for i in range(RETURN_SOURCES - 1)]
    assert briefing([report("wire"), *few], shown_at=SEEN)[1]["events"][0]["carried"]
    many = [report(f"outlet{i}", **later) for i in range(RETURN_SOURCES)]
    assert not briefing([report("wire"), *many], shown_at=SEEN)[1]["events"][0]["carried"]


def test_earlier_briefings_come_from_snapshots_by_version_within_a_week(tmp_path):
    store = Store(tmp_path / "reader.db")
    lead, other, old = report("lead"), report("other"), report("old")
    for m in (lead, other, old):
        store.capture(m)
    service = ContentService(store, settings())
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    store.snapshot({"focus": ["then-lead"], "radar": [], "events": [
        {"id": "then-lead", "version": lead.version}, {"id": "then-other", "version": other.version}]})
    store.snapshot({"focus": ["then-old"], "radar": [], "events": [{"id": "then-old", "version": old.version}]})
    with store.connection() as db:  # the second snapshot is from two weeks ago
        db.execute("UPDATE snapshots SET created_at=? WHERE data LIKE '%then-old%'",
                   ((start - timedelta(days=14)).isoformat(),))
    # Event ids are today's (a merge since may have renamed them): mapped through the versions.
    membership = {"lead": "now-lead", "other": "now-other", "old": "now-old"}
    assert service.briefed({"started_at": start.isoformat()}, membership) == {"now-lead"}
    assert service.briefed(None, membership) == frozenset()
