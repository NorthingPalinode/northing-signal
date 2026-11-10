"""Small synthetic engineering regressions; not a real-news or semantic-quality benchmark."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest
from cfaw_news.briefing.app import create_app
from cfaw_news.briefing.collect import parse
from cfaw_news.briefing.engine import active_actions, project
from cfaw_news.briefing.models import Assessment, Interaction, Material, Preferences
from cfaw_news.briefing.settings import ReaderSettings as Settings
from cfaw_news.briefing.store import Store
from cfaw_news.briefing.understand import Analyzer, grounded, validate, validate_numbers


def settings(**changes):
    """Complete synthetic provider settings; tests never depend on the owner's .env."""
    values = dict(llm_mode="baseline", llm_base_url="https://example.org/v1",
                  llm_model="synthetic", llm_api_key="synthetic-key")
    return Settings(_env_file=None, **{**values, **changes})


def material(**changes):
    value = dict(id="release", source_id="official", source_name="Fixture official", source_role="official",
                 title="Atlas 2 released", url="https://example.org/atlas", text="Atlas 2 is available. Free for research.",
                 published_at="2026-11-01T00:00:00+00:00", captured_at="2026-11-01T01:00:00+00:00",
                 origin="synthetic")
    return Material(**{**value, **changes})


def assessment(**changes):
    value = dict(relevance="ai", topic="models", content_type="release", title="Atlas 2 发布",
                 summary="Atlas 2 已发布，研究用途免费。", reason="提供了明确的使用入口和条件。",
                 subject="Atlas", object="Atlas 2", action="release", event_key="atlas-2",
                 significance=3, novelty=3, usefulness=2, evidence="source_attributed",
                 claims=[dict(statement="Atlas 2 已开放。", quote="Atlas 2 is available.", kind="announcement")],
                 conditions=["Free for research."], limitations=[])
    return Assessment(**{**value, **changes})


def test_runtime_imports_no_evaluation_framework():
    # Run in a clean process: other legacy tests may have imported evals in this interpreter.
    import subprocess
    result = subprocess.run([sys.executable, "-c", "import sys; import cfaw_news.briefing.app; assert not any(x=='evals' or x.startswith('evals.') for x in sys.modules)"], capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_immutable_revisions_and_idempotent_interactions(tmp_path):
    store = Store(tmp_path / "reader.db")
    first = material()
    assert store.capture(first)
    assert not store.capture(first)
    second = material(text="Atlas 2 was corrected.")
    assert store.capture(second)
    assert store.material(first.version).text == first.text
    assert store.materials()[0].text == second.text
    action = Interaction(request_id="known-0001", event_id="event", version=first.version, kind="known")
    assert store.interact(action)
    assert not store.interact(action)
    with pytest.raises(ValueError):
        store.interact(action.model_copy(update={"kind": "opened"}))
    store.interact(Interaction(request_id="retract-0001", event_id="event", version=first.version,
                               kind="retract", retracts=action.request_id))
    assert not active_actions(store.interactions())


def test_quotes_conditions_and_numbers_must_exist_in_source():
    assert validate(assessment(), material())
    for changed in [dict(conditions=["Free forever."]), dict(summary="速度提升 999 倍。"),
                    dict(claims=[dict(statement="已发布", quote="Something invented", kind="announcement")])]:
        with pytest.raises(ValueError):
            validate(assessment(**changed), material())


def test_low_information_test_does_not_hide_valid_release_and_feedback_is_reversible():
    first = material()
    weak = material(id="weak", source_id="weak", text="Something", url="https://example.org/weak")
    judgments = {first.version: assessment().model_dump(), weak.version: assessment(action="test",
                 significance=0, novelty=0, usefulness=0, evidence="insufficient", claims=[]).model_dump()}
    base = project([first, weak], judgments, Preferences())
    event = base["events"][0]
    assert event["qualified"] and event["version"] == first.version
    action = dict(request_id="useful-001", event_id=event["id"], version=event["version"], kind="useful")
    better = project([first, weak], judgments, Preferences(), [action])
    assert better["events"][0]["score"] > event["score"]
    undo = dict(request_id="undo-001", event_id=event["id"], version=event["version"], kind="retract", retracts="useful-001")
    assert project([first, weak], judgments, Preferences(), [action, undo])["events"][0]["score"] == event["score"]


def test_title_only_never_has_publishable_claims():
    with pytest.raises(ValueError):
        validate(assessment(), material(text=""))
    weak = assessment(claims=[])
    validate(weak, material())
    assert weak.evidence == "insufficient"
    view = project([material()], {material().version: weak.model_dump()}, Preferences())
    assert view["focus"] == []


def test_duplicate_occurrence_different_product_and_correction():
    first = material()
    repost = material(id="repost", source_id="media", source_name="Fixture media", source_role="media",
                      url="https://example.net/repost")
    different = material(id="different", title="Atlas 3 released", text="Atlas 3 is available.",
                         url="https://example.org/atlas3")
    judgments = {first.version: assessment().model_dump(), repost.version: assessment().model_dump(),
                 different.version: assessment(object="Atlas 3", event_key="atlas-3").model_dump()}
    view = project([first, repost, different], judgments, Preferences())
    assert len(view["events"]) == 2
    event = next(e for e in view["events"] if e["report_count"] == 2)
    assert event["source_count"] == 2
    action = dict(request_id="known-01", event_id=event["id"], version=event["version"], kind="known")
    correction = material(id="correction", title="Atlas 2 limits corrected", text="Research access requires approval.",
                          url="https://example.org/corrected", published_at="2026-11-06T00:00:00+00:00")
    judgments[correction.version] = assessment(action="correction", title="Atlas 2 使用条件更正",
        claims=[dict(statement="研究用途需批准。", quote="Research access requires approval.", kind="correction")],
        conditions=["Research access requires approval."]).model_dump()
    revised = project([first, repost, different, correction], judgments, Preferences(), [action])
    changed = next(e for e in revised["events"] if e["id"] == event["id"])
    assert changed["protected"] and not changed["known"]
    assert changed["id"] in revised["focus"]


def test_launch_aliases_group_but_keep_other_versions_and_test_progress():
    first = material()
    repost = material(id="repost", source_id="media", text="Atlas 2 is generally available.",
                      url="https://example.net/atlas2")
    next_version = material(id="next", text="Atlas 3 is generally available.", url="https://example.org/atlas3")
    judgments = {first.version: assessment(event_key="atlas-2-release").model_dump(),
                 repost.version: assessment(event_key="atlas-2-ga").model_dump(),
                 next_version.version: assessment(object="Atlas 3", event_key="atlas-3-ga").model_dump()}
    view = project([first, repost, next_version], judgments, Preferences())
    assert len(view["events"]) == 2
    assert max(e["report_count"] for e in view["events"]) == 2
    judgments[repost.version] = assessment(action="test", event_key="atlas-2-ga",
                                          summary="Independent test reports a limitation.").model_dump()
    tested = project([first, repost], judgments, Preferences())["events"][0]
    assert tested["action"] == "test" and len(tested["timeline"]) == 2


@pytest.mark.parametrize("days", [1, 3, 7])
def test_seen_is_not_known_and_knowledge_does_not_erase_updates(days):
    item = material()
    judgments = {item.version: assessment().model_dump()}
    clock = (datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(days=days)).isoformat()
    initial = project([item], judgments, Preferences(), as_of=clock)
    event = initial["events"][0]
    action = dict(request_id="opened-01", event_id=event["id"], version=event["version"], kind="opened")
    assert not project([item], judgments, Preferences(), [action], as_of=clock)["events"][0]["known"]
    action["kind"] = "known"
    assert project([item], judgments, Preferences(), [action], as_of=clock)["focus"] == []


def test_unknown_unrelated_and_future_material_not_recommended():
    item = material()
    for status in ["uncertain", "unrelated"]:
        result = project([item], {item.version: assessment(relevance=status).model_dump()}, Preferences())
        assert result["events"] == [] and len(result["archive"]) == 1
    assert project([item], {}, Preferences(), as_of="2026-10-01T00:00:00+00:00")["archive"] == []


def test_preferences_and_budget():
    with pytest.raises(ValueError):
        Preferences(topics=[])
    items, judgments = [], {}
    for i in range(20):
        item = material(id=f"item-{i}", url=f"https://example.org/{i}")
        items.append(item)
        judgments[item.version] = assessment(event_key=f"atlas-{i}", object=f"Atlas {i}").model_dump()
    for minutes in [3, 7, 15]:
        result = project(items, judgments, Preferences(budget_minutes=minutes))
        assert result["estimated_seconds"] <= result["budget_seconds"]
        assert not set(result["focus"]) & set(result["radar"])


def test_rss_and_release_parse_strip_scripts_and_keep_original_date():
    source = dict(id="fixture", name="Fixture", role="official", kind="rss")
    body = b'<rss version="2.0"><channel><item><title>Atlas</title><link>https://example.org/news</link><description>&lt;script&gt;steal()&lt;/script&gt;Atlas is open.</description><pubDate>Sun, 01 Nov 2026 01:00:00 GMT</pubDate></item></channel></rss>'
    rows = parse(source, body, 10)
    assert len(rows) == 1 and "steal" not in rows[0].text
    assert rows[0].published_at.startswith("2026-11-01")
    releases = parse({**source, "kind": "releases"}, json.dumps([dict(name="Atlas", html_url="https://example.org/news", body="notes", published_at="2026-11-01T00:00:00Z")]).encode(), 1)
    assert releases[0].content_kind == "release_notes"


def test_budget_stops_before_external_request(tmp_path):
    analyzer = Analyzer(Store(tmp_path / "reader.db"), settings(llm_mode="compatible", llm_api_key="fake", llm_base_url="https://example.org", llm_model="fixture"), requests_per_day=0)
    with pytest.raises(ValueError, match="daily_model_budget_reached"):
        asyncio.run(analyzer.batch([material()]))


def test_unlimited_defaults_continue_past_previous_daily_limits(tmp_path):
    from cfaw_news.briefing.settings import ReaderSettings
    from fastapi.testclient import TestClient
    settings = ReaderSettings(_env_file=None)
    assert settings.reader_requests_per_day is None and settings.reader_tokens_per_day is None
    store = Store(tmp_path / "unlimited.db")
    service_app = create_app(settings, store)
    for _ in range(65):
        key = store.reserve_request({"charged_tokens": 20000, "status": "started"}, None, None)
        store.finish_request(key, {"charged_tokens": 20000, "status": "ok"})
    with TestClient(service_app) as client:
        usage = client.get("/api/reader/status").json()["usage"]
        assert usage == dict(requests_today=65, tokens_today=1300000, request_limit=None, token_limit=None)
        assert client.get("/api/reader").json()["usage"] == usage
    with pytest.raises(ValueError, match="daily_model_budget_reached"):
        store.reserve_request({"charged_tokens": 1}, None, 1300000)
    with pytest.raises(ValueError, match="daily_model_budget_reached"):
        store.reserve_request({"charged_tokens": 1}, 65, None)


def test_typography_and_translated_quantities_do_not_invent_facts():
    assert grounded("It's a model - not a claim.", "It’s a model — not a claim.") == "It’s a model — not a claim."
    validate_numbers("5940亿参数，7月", "594 billion parameters, July")
    validate_numbers("1秒步长", "duration in one-second increments")
    with pytest.raises(ValueError):
        validate_numbers("594亿参数", "594 billion parameters")
    with pytest.raises(ValueError):
        grounded("Words from different sentences", "Words from one sentence. A different sentence.")


def test_shared_budget_reservation_and_immutable_snapshot(tmp_path):
    store = Store(tmp_path / "reader.db")
    first = store.reserve_request({"charged_tokens": 100}, 1, 200)
    with pytest.raises(ValueError, match="daily_model_budget_reached"):
        Store(store.path).reserve_request({"charged_tokens": 100}, 1, 200)
    store.finish_request(first, {"charged_tokens": 50, "status": "ok"})
    key = store.snapshot({"events": ["one"]})
    store.snapshot({"events": ["two"]})
    assert store.snapshots(key) == {"events": ["one"]}
    store.visit("visit-one")
    before = store.last_visit()
    store.visit("visit-one")
    assert store.last_visit() == before


def test_api_boundary_preferences_and_missing_revision(tmp_path):
    from fastapi.testclient import TestClient
    store = Store(tmp_path / "reader.db")
    with TestClient(create_app(settings(), store)) as client:
        from cfaw_news import __version__
        health = client.get("/api/health").json()
        assert health["engine"] == "content-v1" and health["version"] == __version__
        assert client.get("/openapi.json").json()["info"]["version"] == __version__
        assert client.get("/api/reader").json()["counts"]["materials"] == 0
        assert client.put("/api/reader/preferences", json=Preferences().model_dump(),
                          headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.put("/api/reader/preferences", json=Preferences(topics=["research"]).model_dump()).status_code == 200
        assert store.preferences().topics == ["research"]
        assert client.get("/api/reader/materials/missing").status_code == 404


def test_cancel_stops_before_judgment_publication(tmp_path, monkeypatch):
    from cfaw_news.briefing.models import RefreshRequest
    from cfaw_news.briefing.service import ContentService
    async def scenario():
        store = Store(tmp_path / "reader.db")
        store.capture(material())
        service = ContentService(store, settings(llm_mode="compatible", llm_api_key="fake",
                                                 llm_base_url="https://example.org", llm_model="fixture"))
        entered = asyncio.Event()
        async def collect_nothing(*args, **kwargs):
            return []
        async def slow_batch(items):
            entered.set()
            await asyncio.sleep(60)
        monkeypatch.setattr("cfaw_news.briefing.service.collect", collect_nothing)
        monkeypatch.setattr("cfaw_news.briefing.service.enrich", collect_nothing)
        monkeypatch.setattr(service.analyzer, "batch", slow_batch)
        service.start(RefreshRequest(analyze_limit=1))
        await entered.wait()
        await service.cancel()
        assert service.run["state"] == "cancelled"
        assert not store.judgments("any")
    asyncio.run(scenario())


def test_follow_persistence_aliases_and_version_scoped_unread(tmp_path):
    from cfaw_news.briefing.models import FollowInput
    from cfaw_news.briefing.service import ContentService
    from cfaw_news.briefing.understand import POLICY_HASH
    store = Store(tmp_path / "follow.db")
    item = material()
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment().model_dump(), "fixture")
    follow = store.save_follow(FollowInput(name="中文话题", query="unmatched, Atlas 2", active=False))
    service = ContentService(Store(store.path), settings())
    view = service.view()
    topic = view["follows"][0]
    assert topic["id"] == follow["id"] and len(topic["unread_ids"]) == 1
    store.update_follow(follow["id"], seen_versions=topic["versions"])
    assert not service.view()["follows"][0]["unread_ids"]
    revised = material(text="Atlas 2 is available. Research access requires approval.")
    store.capture(revised)
    store.judge(revised.version, POLICY_HASH, assessment(action="correction").model_dump(), "fixture")
    assert len(service.view()["follows"][0]["unread_ids"]) == 1
    assert not service.view()["events"][0]["known"]
    duplicate = store.save_follow(FollowInput(name="另一个名字", query="unmatched, Atlas 2", active=False))
    assert duplicate["id"] == follow["id"] and len(store.follows()) == 1
    store.update_follow(follow["id"], archived=True, active=False)
    assert service.view()["follows"] == []


def test_follow_scheduler_respects_interval_pause_and_shared_worker(tmp_path, monkeypatch):
    from cfaw_news.briefing.models import ConfirmFollow
    from cfaw_news.briefing.service import ContentService
    async def scenario():
        store = Store(tmp_path / "scheduler.db")
        draft = store.create_follow_draft("追踪可复现的本地智能体实现和评估。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        service = ContentService(store, settings())
        calls = []
        entered = asyncio.Event()
        release = asyncio.Event()
        async def controlled_discovery(*args, **kwargs):
            calls.append(args[1])
            entered.set()
            await release.wait()
            return []
        async def no_network(*args, **kwargs):
            return []
        monkeypatch.setattr("cfaw_news.briefing.service.collect", no_network)
        monkeypatch.setattr("cfaw_news.briefing.service.enrich", no_network)
        monkeypatch.setattr("cfaw_news.briefing.service.discover", controlled_discovery)
        service.track_due()
        await entered.wait()
        service.track_due()
        assert len(calls) == 1
        release.set()
        await service.task
        service.track_due()
        assert len(calls) == 2 and store.follows()[0]["last_status"] == "ok"
        store.update_follow(follow["id"], active=False, last_checked=None)
        service.track_due()
        assert len(calls) == 2
        store.update_follow(follow["id"], active=True, last_checked=None)
        restarted = ContentService(Store(store.path), settings())
        restarted.track_due()
        await restarted.task
        assert len(calls) == 4
    asyncio.run(scenario())


def test_saved_version_survives_unprocessed_revision_and_api_unfollow(tmp_path):
    from cfaw_news.briefing.understand import POLICY_HASH
    from fastapi.testclient import TestClient
    store = Store(tmp_path / "saved.db")
    item = material()
    store.capture(item)
    store.judge(item.version, POLICY_HASH, assessment().model_dump(), "fixture")
    with TestClient(create_app(settings(), store)) as client:
        event = client.get("/api/reader").json()["events"][0]
        action = dict(request_id="saved-original-001", event_id=event["id"], version=item.version, kind="saved")
        assert client.post("/api/reader/interactions", json=action).status_code == 200
        store.capture(material(text="A new full document, not analyzed yet."))
        view = client.get("/api/reader").json()
        assert view["saved_events"][0]["version"] == item.version
        assert client.post("/api/reader/interactions", json={**action, "request_id":"undo-saved-001",
                           "kind":"retract", "retracts":action["request_id"]}).status_code == 200
        assert not client.get("/api/reader").json()["saved_events"]
        assert client.post("/api/reader/follows", json={"name":"Atlas 2", "active":True}).status_code == 422
        from cfaw_news.briefing.models import FollowInput
        key = store.save_follow(FollowInput(name="Atlas 2", active=False))["id"]
        assert client.post(f"/api/reader/follows/{key}/refresh").status_code == 409
        assert client.post(f"/api/reader/follows/{key}/seen").status_code == 200
        assert client.delete(f"/api/reader/follows/{key}").status_code == 200
        assert not client.get("/api/reader").json()["follows"]
        assert client.post("/api/reader/follows", json={"name":"  "}).status_code == 422


def test_cancelling_follow_does_not_publish_late_model_output(tmp_path, monkeypatch):
    from cfaw_news.briefing.models import ConfirmFollow
    from cfaw_news.briefing.service import ContentService
    from cfaw_news.briefing.understand import POLICY_HASH
    async def scenario():
        store = Store(tmp_path / "cancel-follow.db")
        draft = store.create_follow_draft("追踪本地智能体的实现、代码和具体评估。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        service = ContentService(store, settings(llm_mode="compatible", llm_api_key="fake"))
        entered = asyncio.Event()
        async def found(*args, **kwargs):
            store.capture(material())
            return [material()]
        async def slow(items):
            entered.set()
            await asyncio.sleep(60)
            return {items[0].version: assessment().model_dump()}
        async def no_network(*args, **kwargs):
            return []
        monkeypatch.setattr("cfaw_news.briefing.service.collect", no_network)
        monkeypatch.setattr("cfaw_news.briefing.service.enrich", no_network)
        monkeypatch.setattr("cfaw_news.briefing.service.discover", found)
        monkeypatch.setattr(service.analyzer, "batch", slow)
        service.start_follow(follow["id"])
        await entered.wait()
        await service.cancel()
        assert not store.judgments(POLICY_HASH)
        assert store.follows()[0]["last_status"] == "cancelled"
        await service.close()
    asyncio.run(scenario())


def intent_plan(**changes):
    from cfaw_news.briefing.models import TrackingPlan
    value = dict(title="本地智能体工程", intent_summary="关注可在个人电脑运行的智能体工程实现与实测，排除融资宣传。",
                 focus=["长期记忆的实际实现", "可复现的开源代码与测试"], exclude=["融资消息与空泛宣传"],
                 entities=["local agents", "memory"], topics=["agents", "engineering"],
                 searches=[dict(source="github", query="agent memory local", purpose="寻找可运行的开源实现"),
                           dict(source="arxiv", query="agent persistent memory", purpose="跟进记忆评测与方法"),
                           dict(source="github", query="offline tool calling", purpose="补充端侧工具调用实践")],
                 include_feeds=True, interval_minutes=30, relevance_criteria="材料需提供本地运行的实现、代码或实测，而非仅出现相关名词。",
                 assumptions=["暂按个人开发实践理解，用户可纠正"], limitations=[])
    return TrackingPlan(**{**value, **changes})


def test_intent_preview_never_starts_tracking_and_confirmation_is_bound(tmp_path, monkeypatch):
    from cfaw_news.briefing.models import ConfirmFollow
    from fastapi.testclient import TestClient
    store = Store(tmp_path / "intent-api.db")
    app = create_app(settings(), store)
    calls = []
    async def synthetic_plan(prompt, payload, validator, **kwargs):
        calls.append(kwargs["purpose"])
        return validator(intent_plan().model_dump())
    async def forbidden_search(*args, **kwargs):
        raise AssertionError("Unconfirmed intent must not start retrieval")
    monkeypatch.setattr(app.state.content.analyzer, "request_json", synthetic_plan)
    monkeypatch.setattr("cfaw_news.briefing.service.discover", forbidden_search)
    monkeypatch.setattr("cfaw_news.briefing.service.collect", forbidden_search)
    with TestClient(app) as client:
        response = client.post("/api/reader/follows/interpret", json={"description":"我想跟进本地智能体的实现和测试，不看融资宣传。"})
        assert response.status_code == 200
        draft = response.json()
        assert not store.follows() and app.state.content.task is None
        body = dict(draft_id=draft["id"], plan=draft["plan"], active=False)
        confirmed = client.post("/api/reader/follows", json=body)
        assert confirmed.status_code == 201 and len(store.follows()) == 1
        assert client.post("/api/reader/follows", json=body).json()["confirmed_follow_id"] == confirmed.json()["confirmed_follow_id"]
        altered = {**body, "plan":{**body["plan"], "focus":["不同的目标"]}}
        assert client.post("/api/reader/follows", json=altered).status_code == 409
        assert calls == ["intent_plan"] and not store.follows()[0]["active"]
        first = store.follows()[0]
        older = store.create_follow_draft("另一个希望关注的具体工程方向，需要评估。", intent_plan(), first["id"])
        newer = store.create_follow_draft("再补充一个不同的工程方向，需要评估。", intent_plan(), first["id"])
        store.confirm_follow(ConfirmFollow(draft_id=newer["id"], plan=intent_plan(interval_minutes=120), active=False))
        with pytest.raises(ValueError, match="已发生变化"):
            store.confirm_follow(ConfirmFollow(draft_id=older["id"], plan=intent_plan(), active=False))
        from cfaw_news.briefing.models import FollowInput
        legacy = store.save_follow(FollowInput(name="旧关键词", active=True))
        assert client.post(f"/api/reader/follows/{legacy['id']}/refresh").status_code == 409
        assert client.patch(f"/api/reader/follows/{legacy['id']}", json={"active":True}).status_code == 409
        app.state.content.start_tracking()
        assert not next(f for f in store.follows() if f["id"] == legacy["id"])["active"]


def test_confirmed_intent_rotates_searches_and_semantics_controls_membership(tmp_path, monkeypatch):
    from cfaw_news.briefing.models import ConfirmFollow
    from cfaw_news.briefing.service import ContentService
    from cfaw_news.briefing.understand import POLICY_HASH
    async def scenario():
        store = Store(tmp_path / "semantic.db")
        draft = store.create_follow_draft("我关注可运行的本地工程实践，不看融资新闻。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        positive = material(id="implementation", title="Remembering across sessions", text="Reusable implementation and reproducible results.")
        negative = material(id="funding", title="Local agents memory funding", text="A funding announcement with no implementation.")
        for i, item in enumerate([positive, negative]):
            store.capture(item)
            store.judge(item.version, POLICY_HASH, assessment(event_key=f"event-{i}", object=f"Object-{i}").model_dump(), "synthetic")
        service = ContentService(store, settings())
        searches, semantic_calls = [], []
        async def retrieve(*args, **kwargs):
            searches.append((args[1], kwargs["channels"]))
            return [positive, negative]
        async def no_network(*args, **kwargs):
            return []
        async def semantic(follow, materials):
            semantic_calls.append(follow["plan_hash"])
            return {m.version:{"relevant":m.id == "implementation", "reason":"提供目标需要的工程实践" if m.id == "implementation" else "属于明确排除的融资消息"} for m in materials}
        monkeypatch.setattr("cfaw_news.briefing.service.discover", retrieve)
        monkeypatch.setattr("cfaw_news.briefing.service.collect", no_network)
        monkeypatch.setattr("cfaw_news.briefing.service.enrich", no_network)
        monkeypatch.setattr(service.intent, "evaluate", semantic)
        service.start_follow(follow["id"])
        await service.task
        view = service.view()
        assert len(view["follows"][0]["event_ids"]) == 1
        assert next(e for e in view["events"] if e["id"] in view["follows"][0]["event_ids"])["version"] == positive.version
        assert searches == [("agent memory local",["github"]),("agent persistent memory",["arxiv"])]
        service.start_follow(follow["id"])
        await service.task
        assert searches[2:] == [("offline tool calling",["github"]),("agent memory local",["github"])]
        assert len(semantic_calls) == 1
        changed = store.create_follow_draft("改为关注不同的工程方向，原判断不能直接沿用。", intent_plan(), follow["id"])
        store.confirm_follow(ConfirmFollow(draft_id=changed["id"], plan=intent_plan(interval_minutes=120), active=False))
        assert not service.view()["follows"][0]["event_ids"]
    asyncio.run(scenario())


def test_cancel_intent_matching_and_shared_model_budget(tmp_path, monkeypatch):
    from cfaw_news.briefing.models import ConfirmFollow
    from cfaw_news.briefing.service import ContentService
    from cfaw_news.briefing.understand import POLICY_HASH
    async def scenario():
        store = Store(tmp_path / "intent-cancel.db")
        draft = store.create_follow_draft("关注有实际代码与测试结果的智能体工程项目。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        item = material()
        store.capture(item)
        store.judge(item.version, POLICY_HASH, assessment().model_dump(), "synthetic")
        service = ContentService(store, settings())
        entered = asyncio.Event()
        async def empty(*args, **kwargs):
            return []
        async def delayed(*args):
            entered.set()
            await asyncio.sleep(60)
            return {item.version:{"relevant":True,"reason":"late result"}}
        monkeypatch.setattr("cfaw_news.briefing.service.discover", empty)
        monkeypatch.setattr("cfaw_news.briefing.service.collect", empty)
        monkeypatch.setattr("cfaw_news.briefing.service.enrich", empty)
        monkeypatch.setattr(service.intent, "evaluate", delayed)
        service.start_follow(follow["id"])
        await entered.wait()
        await service.cancel()
        assert not store.intent_assessments(follow["plan_hash"])
        blocked = Analyzer(store, settings(llm_mode="compatible",llm_api_key="fake"), requests_per_day=0)
        with pytest.raises(ValueError, match="daily_model_budget_reached"):
            await blocked.request_json("prompt", {}, lambda value:value, purpose="intent_plan")
    asyncio.run(scenario())


def test_intent_upstream_failure_is_not_reported_as_bad_description(tmp_path, monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    client_type = httpx.AsyncClient
    def reply(request):
        return httpx.Response(500, json={"error": "private-upstream-body"})
    monkeypatch.setattr("cfaw_news.briefing.understand.httpx.AsyncClient",
                        lambda **kwargs: client_type(transport=httpx.MockTransport(reply), **kwargs))
    store = Store(tmp_path / "upstream-failure.db")
    app = create_app(settings(llm_mode="compatible", llm_api_key="synthetic-key",
                              llm_base_url="https://example.org/v1"), store)
    with TestClient(app) as client:
        response = client.post("/api/reader/follows/interpret", json={"description": "我想跟进人工智能开发工具的官方发布和工程实践。"})
        assert response.status_code == 409
        assert "服务暂时请求失败" in response.json()["detail"]
        assert "调整描述" not in response.json()["detail"]
        assert not store.follows() and app.state.content.task is None
    receipt = store.receipts_today()[-1]
    assert receipt["status"] == "failed" and receipt["http_status"] == 500
    assert "private-upstream-body" not in json.dumps(receipt)


def test_expanded_sources_preserve_evidence_types_and_safe_urls(monkeypatch):
    from cfaw_news.briefing import search_sources as sources
    from cfaw_news.briefing.understand import has_material
    async def scenario():
        async def response(url, host, **kwargs):
            if host == "api.anysearch.com":
                return {"data":{"results":[{"title":"Official guide","url":"https://example.org/guide?utm_source=x&asuniq=y", "snippet":"Index summary only", "content":"Do not treat provider content as publisher evidence"},
                                           {"title":"Private","url":"https://127.0.0.1/private"}]}}
            if host == "api.openalex.org":
                return {"results":[{"id":"https://openalex.org/W1", "title":"Memory research", "doi":"https://doi.org/10.1/example", "publication_date":"2026-11-01", "abstract_inverted_index":{"Agent":[0],"memory":[1],"works":[2]}}]}
            if host == "huggingface.co":
                return [{"id":"owner/model", "tags":["license:mit"], "cardData":{"license":["mit"]}}, {"id":"owner/metadata-only","tags":[]}]
            return {"hits":[{"objectID":"1", "title":"Shared old article", "url":"https://example.org/old", "created_at":"2026-11-01T00:00:00Z"},
                            {"objectID":"2", "title":"Show HN", "story_text":"I released a local tool.", "created_at":"2026-11-01T00:00:00Z"}]}
        async def card(*args, **kwargs):
            return b'# Model card\nMIT licensed model. Runs locally with instructions and tests. ' * 4
        monkeypatch.setattr(sources,"api",response)
        monkeypatch.setattr(sources,"fetch",card)
        web = await sources.web("guide",3)
        assert len(web) == 1 and web[0].url == "https://example.org/guide"
        assert web[0].text == "Index summary only" and not has_material(web[0])
        papers = await sources.openalex("memory",2)
        assert papers[0].content_kind == "index_abstract" and papers[0].text == "Agent memory works"
        assert has_material(papers[0]) and papers[0].discovery_url == "https://openalex.org/W1"
        cards = await sources.huggingface("model",2)
        assert cards[0].content_kind == "publisher_excerpt" and has_material(cards[0])
        assert cards[1].content_kind == "catalog_metadata" and not has_material(cards[1])
        community = await sources.hackernews("local tool",2)
        assert community[0].published_at is None and not has_material(community[0])
        assert community[1].content_kind == "community_post" and community[1].source_role == "community"
    asyncio.run(scenario())


def test_selected_discovery_channel_and_failed_source_are_isolated(tmp_path, monkeypatch):
    from cfaw_news.briefing import discover as discovery
    from cfaw_news.briefing.models import SearchDirection
    from cfaw_news.briefing.search_sources import SEARCH_SOURCES
    from cfaw_news.briefing.understand import has_material
    async def scenario():
        store = Store(tmp_path / "sources.db")
        lead = material(id="lead", text="Search snippet.", content_kind="search_excerpt")
        calls = []
        async def web(query, *args):
            assert query == 'site:example.org/guide "agent tools" -jobs'
            calls.append("web")
            return [lead]
        async def failed(*args):
            calls.append("openalex")
            raise ValueError("Upstream unavailable")
        async def enrich(store, **kwargs):
            assert kwargs["limit"] == 2
            for row in kwargs["materials"]:
                store.capture(row.model_copy(update={"text":"Actual publisher document.","content_kind":"publisher_excerpt"}))
        monkeypatch.setitem(discovery.PROVIDERS,"web",web)
        monkeypatch.setitem(discovery.PROVIDERS,"openalex",failed)
        monkeypatch.setattr(discovery,"enrich",enrich)
        rows = await discovery.discover(store,'site:example.org/guide "agent tools" -jobs',channels=["web","openalex"])
        assert calls == ["web","openalex"]
        assert store.material(lead.version).content_kind == "search_excerpt"
        assert rows[0].content_kind == "publisher_excerpt" and has_material(rows[0])
        assert store.source_states()["web-discovery"]["status"] == "ok"
        assert store.source_states()["openalex-discovery"]["status"] == "error"
        assert not any(k.startswith("github") for k in store.source_states())
        for key in SEARCH_SOURCES:
            assert SearchDirection(source=key,query="local agents",purpose="确认后的搜索方向").source == key
        with pytest.raises(ValueError,match="unsupported_search_channel"):
            await discovery.discover(store,"query",channels=["unknown"])
    asyncio.run(scenario())


def test_social_search_returns_only_platform_post_links_and_preserves_clues(monkeypatch, tmp_path):
    from cfaw_news.briefing import search_sources as sources
    from cfaw_news.briefing.collect import enrich
    from cfaw_news.briefing.models import DiscoveryRequest
    from cfaw_news.briefing.understand import has_material
    async def scenario():
        calls = []
        async def public_search(query, limit, settings):
            calls.append(query)
            return [material(id=str(i), url=url, text="Search excerpt, not a transcript.", content_kind="search_excerpt", published_at=None)
                    for i, url in enumerate(["https://x.com/researcher/status/123", "https://x.com/home",
                                            "https://x.com.example.org/researcher/status/123",
                                            "https://www.douyin.com/video/123", "https://www.douyin.com/search/AI",
                                            "https://www.xiaohongshu.com/explore/abcdef0123456789abcdef01"])]
        async def forbidden_network(*args, **kwargs):
            raise AssertionError("Social search snippets must not be promoted from login shells")
        monkeypatch.setattr(sources, "web", public_search)
        monkeypatch.setattr("cfaw_news.briefing.collect.public_document", forbidden_network)
        store = Store(tmp_path / "social-clues.db")
        for channel in sources.SOCIAL_SOURCES:
            rows = await sources.social_web(channel, "AI agents", 4)
            assert len(rows) == 1 and rows[0].source_id == channel + "-discovery"
            assert rows[0].source_role == "community" and not has_material(rows[0])
            assert rows[0].published_at is None
            store.capture(rows[0])
        assert all("site:" in query for query in calls)
        assert await enrich(store, materials=store.materials()) == []
        assert DiscoveryRequest(query="AI", channels=list(sources.SEARCH_SOURCES)).channels[-3:] == ["x", "douyin", "xiaohongshu"]
    asyncio.run(scenario())


def test_x_native_api_uses_own_token_and_actual_post_text(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from cfaw_news.briefing import search_sources as sources
    from cfaw_news.briefing.settings import ReaderSettings
    async def scenario():
        async def response(url, host, **kwargs):
            assert host == "api.x.com" and kwargs["key"] == "synthetic-project-token"
            assert parse_qs(urlsplit(url).query)["max_results"] == ["10"]
            return {"data": [{"id": "123", "author_id": "1", "text": "Short text",
                              "note_tweet": {"text": "Actual longer post text with methods and source links."},
                              "created_at": "2026-11-01T00:00:00Z"}, {"id": "bad", "text": "invalid id"}],
                    "includes": {"users": [{"id": "1", "username": "researcher"}]}}
        monkeypatch.setattr(sources, "api", response)
        settings = ReaderSettings(_env_file=None, reader_x_bearer_token="synthetic-project-token")
        rows = await sources.x("agent tools", 3, settings)
        assert rows[0].content_kind == "community_post" and rows[0].text.startswith("Actual longer")
        assert rows[0].url == "https://x.com/researcher/status/123"
        assert sources.source_access("x", settings) == "platform_api"
        assert len(rows) == 1
    asyncio.run(scenario())


def test_search_post_does_not_redirect_credentials(monkeypatch):
    import httpx
    from cfaw_news.briefing import collect as collection
    async def scenario():
        client_type = httpx.AsyncClient
        requests = []
        def reply(request):
            requests.append(request)
            return httpx.Response(302,headers={"location":"https://other.example/search"})
        async def addresses(*args):
            yield "8.8.8.8"
        monkeypatch.setattr(collection,"connection_addresses",addresses)
        monkeypatch.setattr(collection,"OriginTLS",lambda host:True)
        monkeypatch.setattr(collection.httpx,"AsyncClient",lambda **kwargs:client_type(transport=httpx.MockTransport(reply),**kwargs))
        with pytest.raises(ValueError,match="api_redirect_rejected"):
            await collection.fetch("https://api.anysearch.com/v1/search",{"api.anysearch.com"},method="POST",payload={"query":"test"},headers={"Authorization":"Bearer synthetic-key"})
        assert len(requests) == 1 and requests[0].headers["host"] == "api.anysearch.com"
    asyncio.run(scenario())
