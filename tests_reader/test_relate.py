"""Model-judged event relations (2026-11-24, adapted from AIHOT's grouping)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from northing_signal.briefing.models import Interaction
from northing_signal.briefing.relate import Relation, candidates, validate
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, material, settings

NOW = datetime.now(timezone.utc)


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def event(key, *, source, subject, obj, title, summary="", hours=10, qualified=True):
    return {"id": key, "source_id": source, "subject": subject, "object": obj, "title": title,
            "summary": summary, "published_at": ago(hours), "qualified": qualified, "source_role": "media"}


def test_recall_pairs_shared_names_across_outlets_and_languages():
    events = [
        event("nv", source="nvidia", subject="NVIDIA", obj="GR00T 2 世界动作模型", hours=30,
              title="NVIDIA 在 CoRL 发布 GR00T 2 世界动作模型", summary="GR00T 2 从人类视频学习动作"),
        event("dec", source="decoder", subject="英伟达", obj="GR00T 2", title="英伟达 GR00T 2 模型从人类视频学习",
              summary="GR00T 2 从人类视频学习并迁移手部动作"),
        # Same outlet, different builds, only a company in common: none of these pair up.
        event("b1", source="llama", subject="llama.cpp", obj="llama.cpp b12221", title="llama.cpp b12221 修复 Metal"),
        event("b2", source="llama2", subject="llama.cpp", obj="llama.cpp b12307", title="llama.cpp b12307 修复 Metal"),
        event("rev", source="techcrunch", subject="OpenAI", obj="季度营收", title="OpenAI 季度营收破百亿"),
        event("nato", source="openai", subject="OpenAI", obj="Daybreak 网络安全合作", title="OpenAI 与北约合作"),
        event("old", source="other", subject="英伟达", obj="GR00T 2", title="英伟达 GR00T 2", hours=24 * 20),
    ]
    pairs = candidates(events, clock=NOW)
    assert [(older["id"], newer["id"]) for _, older, newer in pairs] == [("nv", "dec")]  # older first
    assert candidates(events, {frozenset(("nv", "dec"))}, clock=NOW) == []  # judged pairs are not asked again


def test_every_pair_must_be_answered_exactly_once():
    check = validate(["p-1", "p-2"])
    answer = {"items": [{"id": "p-1", "relation": "SAME_STORY"}, {"id": "p-2", "relation": "UNRELATED"}]}
    assert check(answer)["p-1"].relation == "SAME_STORY"
    with pytest.raises(ValueError):
        check({"items": [{"id": "p-1", "relation": "SAME_STORY"}]})
    with pytest.raises(ValueError):
        check({"items": [{"id": "p-1", "relation": "MAYBE"}, {"id": "p-2", "relation": "UNRELATED"}]})


def library(tmp_path):
    store = Store(tmp_path / "reader.db")
    official = material(id="nv", url="https://example.org/nv", source_id="nvidia", source_name="NVIDIA",
                        published_at=ago(30), captured_at=ago(29), text="NVIDIA GR00T 2 learns actions from human video.")
    media = material(id="dec", url="https://example.org/dec", source_id="decoder", source_name="The Decoder",
                     source_role="media", published_at=ago(10), captured_at=ago(9),
                     text="Nvidia's GR00T 2 model learns from human video and transfers hand motion.")
    store.capture(official)
    store.capture(media)
    store.judge(official.version, POLICY_HASH, assessment(
        subject="NVIDIA", object="GR00T 2 世界动作模型", event_key="nvidia-gr00t-2",
        title="NVIDIA 发布 GR00T 2 世界动作模型", summary="GR00T 2 从人类视频学习动作，并迁移到机器人。").model_dump(), "fixture")
    store.judge(media.version, POLICY_HASH, assessment(
        subject="英伟达", object="GR00T 2", event_key="gr00t-2-human-video",
        title="英伟达 GR00T 2 从人类视频学习", summary="GR00T 2 从人类视频学习并迁移手部动作到机器人。").model_dump(), "fixture")
    service = ContentService(store, settings(llm_mode="compatible"))
    return store, service, official, media


def answering(service, relation, calls):
    async def fake(prompt, payload, validator, *, purpose, maximum):
        calls.append(payload)
        return validator({"items": [{"id": row["id"], "relation": relation, "reason": "test"} for row in payload]})
    service.analyzer.request_json = fake


def test_same_occurrence_merges_into_the_older_event_and_reader_actions_follow(tmp_path):
    store, service, official, media = library(tmp_path)
    before = {e["id"]: e for e in service.view()["events"]}
    assert len(before) == 2  # different frames: two one-source events
    newer = next(e for e in before.values() if e["source_id"] == "decoder")
    service.record_interaction(Interaction(request_id="saved-0001", event_id=newer["id"],
                                           version=newer["version"], kind="saved"))
    calls = []
    answering(service, "SAME_OCCURRENCE", calls)
    run = service.new_run("refresh", "grouping")
    asyncio.run(service.relate_events(run))
    assert run["relations"] == {"checked": 1, "merged": 1} and len(calls) == 1
    after = service.view()["events"]
    assert len(after) == 1 and after[0]["source_count"] == 2 and after[0]["saved"]
    # Asked once: the next update does not ask again.
    asyncio.run(service.relate_events(service.new_run("refresh", "grouping")))
    assert len(calls) == 1


def test_unrelated_pairs_stay_apart_and_reader_splits_are_never_undone(tmp_path):
    store, service, official, media = library(tmp_path)
    calls = []
    answering(service, "UNRELATED", calls)
    run = service.new_run("refresh", "grouping")
    asyncio.run(service.relate_events(run))
    assert run["relations"] == {"checked": 1, "merged": 0} and len(service.view()["events"]) == 2
    # A reader once split the media report out: the model's merge leaves it alone.
    store2, service2, _, media2 = library(tmp_path / "split")
    events = {e["source_id"]: e for e in service2.view()["events"]}
    service2.merge_events(events["decoder"]["id"], events["nvidia"]["id"])
    merged = service2.view()["events"][0]
    service2.split_event(merged["id"], media2.version)
    answering(service2, "SAME_OCCURRENCE", [])
    run = service2.new_run("refresh", "grouping")
    asyncio.run(service2.relate_events(run))
    assert run["relations"]["merged"] == 0 and len(service2.view()["events"]) == 2


def test_a_model_failure_stops_grouping_but_not_the_update(tmp_path):
    store, service, *_ = library(tmp_path)

    async def failing(*args, **kwargs):
        raise ValueError("intent_model_request_failed")
    service.analyzer.request_json = failing
    run = service.new_run("refresh", "grouping")
    asyncio.run(service.relate_events(run))
    assert run["errors"] == ["relation_model_request_failed"] and run["relations"] == {"checked": 0, "merged": 0}
    assert store.relation_pairs() == set()  # nothing recorded: asked again next time
    assert Relation(id="p", relation="ROUNDUP").relation == "ROUNDUP"
