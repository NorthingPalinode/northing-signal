"""Judgment backoff, partial batches, policy epochs, the task queue and local-day budgets."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from northing_signal.briefing import engine as engine_module
from northing_signal.briefing import service as service_module
from northing_signal.briefing import store as store_module
from northing_signal.briefing.app import create_app
from northing_signal.briefing.models import (
    ConfirmFollow,
    DiscoveryRequest,
    RefreshRequest,
    day_start,
)
from northing_signal.briefing.service import ContentService
from northing_signal.briefing.store import Store
from northing_signal.briefing.understand import POLICY_HASH
from test_reader import assessment, intent_plan, material, settings

MODEL = dict(llm_mode="compatible", llm_api_key="synthetic-key", llm_base_url="https://example.org/v1",
             llm_model="fixture")


def item(index):
    return material(id=f"m{index}", url=f"https://example.org/{index}",
                    title=f"Atlas {index} released", text=f"Atlas {index} is available. Free for research.")


def judged(index, **changes):
    value = dict(title=f"Atlas {index} 发布", summary=f"Atlas {index} 已发布，研究用途免费。",
                 subject="Atlas", object=f"Atlas {index}", event_key=f"atlas-{index}",
                 claims=[dict(statement=f"Atlas {index} 已开放。", quote=f"Atlas {index} is available.",
                              kind="announcement")])
    return assessment(**{**value, **changes}).model_dump()


def fake_model(monkeypatch, answer):
    """answer(versions) -> (items, finish_reason) or an httpx.Response; records each request."""
    calls = []
    client_type = httpx.AsyncClient

    def reply(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        versions = [row["id"] for row in payload]
        calls.append(versions)
        result = answer(versions)
        if isinstance(result, httpx.Response):
            return result
        items, finish = result
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {
            "content": json.dumps({"items": items})}}], "usage": {"total_tokens": 100}})
    monkeypatch.setattr("northing_signal.briefing.understand.httpx.AsyncClient",
                        lambda **kwargs: client_type(transport=httpx.MockTransport(reply), **kwargs))
    return calls


def seeded(tmp_path, count, **changes):
    store = Store(tmp_path / "reader.db")
    items = [item(i) for i in range(count)]
    for value in items:
        store.capture(value)
    return store, items, ContentService(store, settings(**{**MODEL, **changes}))


def analyze(service, items, limit=24):
    run = service.new_run("analyze", "understanding")
    asyncio.run(service.analyze(items, run, limit))
    return run


def test_partial_reply_keeps_valid_items_and_records_the_rest(tmp_path, monkeypatch):
    store, items, service = seeded(tmp_path, 4)
    by_version = {m.version: i for i, m in enumerate(items)}

    def answer(versions):
        rows = [{"id": v, "assessment": judged(by_version[v])} for v in versions[:2]]
        rows[1]["assessment"]["claims"][0]["quote"] = "Not in the source."  # fails grounding
        rows.append({"id": versions[0], "assessment": judged(by_version[versions[0]])})  # duplicate
        rows.append({"id": "unknown-version", "assessment": judged(0)})  # never requested
        return rows, "stop"  # versions[2:] are missing
    fake_model(monkeypatch, answer)
    run = analyze(service, items)
    assert set(store.judgments()) == {items[0].version}
    assert run["analyzed"] == 1 and run["failed"] == 3 and not run["errors"]
    failures = store.failures()
    assert failures[items[1].version]["code"] == "quote_not_in_original"
    assert failures[items[1].version]["attempts"] == 2  # content mismatches skip the first step
    assert {failures[m.version]["code"] for m in items[2:]} == {"missing_from_output"}
    receipt = store.receipts_today()[-1]
    assert receipt["status"] == "partial" and receipt["dropped_items"] == 2


def test_backoff_steps_then_stops_and_retry_or_success_clears_it(tmp_path):
    store, items, service = seeded(tmp_path, 3)
    version = items[0].version
    first = store.record_failure(version, "schema_validation")
    retry_at = datetime.fromisoformat(first["retry_at"])
    assert first["attempts"] == 1 and timedelta(minutes=59) < retry_at - datetime.now(timezone.utc) <= timedelta(hours=1)
    assert store.record_failure(version, "schema_validation")["attempts"] == 2
    third = store.record_failure(version, "schema_validation")
    assert third["gave_up"] and third["retry_at"] is None
    store.record_failure(items[1].version, "missing_from_output")  # waiting for its retry time
    assert service.pending_judgments(items, 10) == [items[2]]
    # Due again once the wait is over.
    with store.connection() as db:
        row = json.loads(db.execute("SELECT data FROM judgment_failures WHERE version=?",
                                    (items[1].version,)).fetchone()[0])
        row["retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.execute("UPDATE judgment_failures SET data=? WHERE version=?", (json.dumps(row), items[1].version))
    assert service.pending_judgments(items, 10) == [items[1], items[2]]
    assert store.clear_failure(version) and not store.clear_failure(version)
    store.record_failure(items[2].version, "schema_validation")
    store.judge(items[2].version, POLICY_HASH, judged(2), "fixture")
    assert items[2].version not in store.failures()


def test_failed_materials_are_labelled_and_can_be_retried_over_http(tmp_path):
    from fastapi.testclient import TestClient
    store, items, _ = seeded(tmp_path, 2)
    for _ in range(3):
        store.record_failure(items[0].version, "schema_validation")
    store.record_failure(items[1].version, "missing_from_output")
    with TestClient(create_app(settings(), store)) as client:
        view = client.get("/api/reader").json()
        status = {row["version"]: row for row in view["archive"]}
        assert status[items[0].version]["status"] == "failed"
        assert status[items[0].version]["failure"]["attempts"] == 3
        assert status[items[1].version]["status"] == "retrying"
        assert view["counts"]["failed"] == 1 and view["counts"]["pending"] == 1
        retried = client.post(f"/api/reader/materials/{items[0].version}/retry").json()
        assert {r["version"]: r["status"] for r in retried["archive"]}[items[0].version] == "pending"
        assert client.post(f"/api/reader/materials/{items[0].version}/retry").status_code == 404


def test_provider_errors_stop_the_run_without_blaming_materials(tmp_path, monkeypatch):
    store, items, service = seeded(tmp_path, 8)
    calls = fake_model(monkeypatch, lambda versions: httpx.Response(503, json={"error": "busy"}))
    run = analyze(service, items)
    assert len(calls) == 1  # the second batch is not sent to a failing provider
    assert run["errors"] == ["model_request_failed"] and not store.failures()
    receipt = store.receipts_today()[-1]
    assert receipt["error_code"] == "model_request_failed" and receipt["http_status"] == 503


def test_truncated_batches_split_and_single_items_record_failure(tmp_path, monkeypatch):
    store, items, service = seeded(tmp_path, 3, reader_batch_size=2)
    by_version = {m.version: i for i, m in enumerate(items)}

    def answer(versions):
        if len(versions) > 1 or by_version[versions[0]] == 2:
            return [], "length"
        return [{"id": versions[0], "assessment": judged(by_version[versions[0]])}], "stop"
    calls = fake_model(monkeypatch, answer)
    run = analyze(service, items)
    assert [len(c) for c in calls] == [2, 1, 1, 1]
    assert set(store.judgments()) == {items[0].version, items[1].version}
    assert store.failures()[items[2].version]["code"] == "model_output_truncated"
    assert run["analyzed"] == 2 and run["failed"] == 1


def test_unreadable_reply_counts_against_every_item(tmp_path, monkeypatch):
    store, items, service = seeded(tmp_path, 2)
    fake_model(monkeypatch, lambda versions: httpx.Response(200, json={"choices": [
        {"finish_reason": "stop", "message": {"content": "not json"}}]}))
    run = analyze(service, items)
    assert run["errors"] == ["model_validation_failed:invalid_response"]
    assert {f["code"] for f in store.failures().values()} == {"invalid_response"} and len(store.failures()) == 2


def test_model_concurrency_is_bounded_by_settings(tmp_path, monkeypatch):
    for limit in (1, 2):
        store, items, service = seeded(tmp_path / str(limit), 6, reader_batch_size=1, reader_model_concurrency=limit)
        active, peak = 0, 0

        async def batch(materials):
            nonlocal active, peak
            async with service.analyzer.slots:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1
            return {}
        monkeypatch.setattr(service.analyzer, "batch", batch)
        analyze(service, items)
        assert peak == limit


def test_reworded_prompt_keeps_judgments_and_a_new_epoch_marks_them_stale(tmp_path, monkeypatch):
    store, items, service = seeded(tmp_path, 2)
    store.judge(items[0].version, "an-older-prompt-hash", judged(0), "fixture")  # epoch 1 by default
    event = service.view()["events"][0]
    assert event["version"] == items[0].version and not event["policy_stale"]
    for module in (store_module, service_module, engine_module):
        monkeypatch.setattr(module, "POLICY_EPOCH", 2)
    stale = ContentService(store, settings(**MODEL))
    event = stale.view()["events"][0]
    assert event["policy_stale"]  # still readable while it waits for re-judgment
    assert stale.pending_judgments(items, 10) == [items[1], items[0]]  # unjudged first
    by_version = {m.version: i for i, m in enumerate(items)}
    fake_model(monkeypatch, lambda versions: (
        [{"id": v, "assessment": judged(by_version[v], title=f"Atlas {by_version[v]} 新规则")} for v in versions], "stop"))
    analyze(stale, items)
    assert {v["epoch"] for v in store.judgments().values()} == {2}
    event = next(e for e in stale.view()["events"] if e["version"] == items[0].version)
    assert not event["policy_stale"] and event["title"] == "Atlas 0 新规则"


def test_queue_orders_manual_work_first_and_cancels_by_id(tmp_path, monkeypatch):
    async def scenario():
        store = Store(tmp_path / "queue.db")
        draft = store.create_follow_draft("追踪可复现的本地智能体实现和评估。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        service = ContentService(store, settings())
        release, order = asyncio.Event(), []

        async def blocking_collect(*args, **kwargs):
            order.append("collect")
            await release.wait()
            return []

        async def nothing(*args, **kwargs):
            return []

        async def searching(store, query, **kwargs):
            order.append(query)
            return []
        monkeypatch.setattr("northing_signal.briefing.service.collect", blocking_collect)
        monkeypatch.setattr("northing_signal.briefing.service.enrich", nothing)
        monkeypatch.setattr("northing_signal.briefing.service.discover", searching)
        refresh = service.start(RefreshRequest(analyze_limit=0))
        await asyncio.sleep(0)
        assert refresh["state"] == "running" and service.start(RefreshRequest())["id"] == refresh["id"]
        first = service.start_discovery(DiscoveryRequest(query="first query", channels=["web"]))
        service.track_due()  # scheduled: goes behind manual work
        assert store.follows()[0]["last_status"] == "queued"
        second = service.start_discovery(DiscoveryRequest(query="second query", channels=["web"]))
        assert [r.get("query") for r in service.queued()] == ["first query", "second query", follow["query"]]
        assert service.start_follow(follow["id"])["id"] == service.queued()[2]["id"]  # not queued twice
        assert (await service.cancel(first["id"]))["state"] == "cancelled"
        with pytest.raises(LookupError):
            await service.cancel("no-such-run")
        release.set()
        while service.busy() or service.queued():
            await asyncio.sleep(0.01)
        # The topic also reads its feeds (include_feeds) before its two searches.
        assert order == ["collect", "second query", "collect", "agent memory local", "agent persistent memory"]
        assert second["state"] == "completed" and store.follows()[0]["last_status"] == "ok"
        await service.close()
    asyncio.run(scenario())


def test_pausing_a_topic_drops_its_queued_check_and_the_queue_is_bounded(tmp_path, monkeypatch):
    async def scenario():
        store = Store(tmp_path / "queue.db")
        draft = store.create_follow_draft("追踪可复现的本地智能体实现和评估。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        service = ContentService(store, settings())
        release = asyncio.Event()

        async def blocking(*args, **kwargs):
            await release.wait()
            return []
        monkeypatch.setattr("northing_signal.briefing.service.collect", blocking)
        monkeypatch.setattr("northing_signal.briefing.service.enrich", blocking)
        monkeypatch.setattr("northing_signal.briefing.service.discover", blocking)
        service.start(RefreshRequest(analyze_limit=0))
        service.start_follow(follow["id"])
        assert await service.cancel_follow(follow["id"]) and not service.queued()
        assert store.follows()[0]["last_status"] == "cancelled"
        for index in range(service_module.QUEUE_LIMIT):
            service.start_discovery(DiscoveryRequest(query=f"query {index}", channels=["web"]))
        with pytest.raises(ValueError):
            service.start_discovery(DiscoveryRequest(query="one too many", channels=["web"]))
        await service.close()
        assert not service.queued() and service.run["state"] == "cancelled"
    asyncio.run(scenario())


def test_budget_day_follows_the_reader_timezone(tmp_path):
    start = datetime.fromisoformat(day_start("Asia/Shanghai"))
    local = start.astimezone(ZoneInfo("Asia/Shanghai"))
    assert (local.hour, local.minute) == (0, 0) and start.utcoffset() == timedelta(0)
    assert datetime.now(timezone.utc) - start < timedelta(days=1)
    store = Store(tmp_path / "reader.db")
    for offset in (timedelta(seconds=-1), timedelta(seconds=1)):
        key = store.reserve_request({"charged_tokens": 10}, None, None)
        with store.connection() as db:
            db.execute("UPDATE receipts SET created_at=? WHERE id=?", ((start + offset).isoformat(), key))
    assert len(store.receipts_today(start.isoformat())) == 1
    with pytest.raises(ValueError):
        settings(reader_timezone="Mars/Olympus")


def test_cancel_before_the_first_step_still_settles_and_advances_the_queue(tmp_path, monkeypatch):
    async def scenario():
        service = ContentService(Store(tmp_path / "queue.db"), settings())
        searched = []

        async def nothing(*args, **kwargs):
            return []

        async def searching(store, query, **kwargs):
            searched.append(query)
            return []
        monkeypatch.setattr("northing_signal.briefing.service.collect", nothing)
        monkeypatch.setattr("northing_signal.briefing.service.enrich", nothing)
        monkeypatch.setattr("northing_signal.briefing.service.discover", searching)
        refresh = service.start(RefreshRequest(analyze_limit=0))
        waiting = service.start_discovery(DiscoveryRequest(query="next query", channels=["web"]))
        assert (await service.cancel())["id"] == refresh["id"]  # the task never ran a step
        assert refresh["state"] == "cancelled" and waiting["state"] == "running"
        await service.task
        assert searched == ["next query"] and waiting["state"] == "completed"
    asyncio.run(scenario())


def test_cancel_endpoint_accepts_no_body_or_a_run_id(tmp_path):
    from fastapi.testclient import TestClient
    with TestClient(create_app(settings(), Store(tmp_path / "reader.db"))) as client:
        assert client.post("/api/reader/cancel").status_code == 200
        assert client.post("/api/reader/cancel", json={}).status_code == 200
        assert client.post("/api/reader/cancel", json={"id": "missing"}).status_code == 404
        status = client.get("/api/reader/status").json()
        assert status["queue"] == [] and client.get("/api/reader").json()["queue"] == []


def test_asking_now_promotes_a_scheduled_check_and_restarts_clear_stale_queue_states(tmp_path, monkeypatch):
    async def scenario():
        store = Store(tmp_path / "queue.db")
        draft = store.create_follow_draft("追踪可复现的本地智能体实现和评估。", intent_plan())
        follow, _ = store.confirm_follow(ConfirmFollow(draft_id=draft["id"], plan=intent_plan()))
        service = ContentService(store, settings())
        release = asyncio.Event()

        async def blocking(*args, **kwargs):
            await release.wait()
            return []
        monkeypatch.setattr("northing_signal.briefing.service.collect", blocking)
        monkeypatch.setattr("northing_signal.briefing.service.enrich", blocking)
        monkeypatch.setattr("northing_signal.briefing.service.discover", blocking)
        service.start(RefreshRequest(analyze_limit=0))
        service.track_due()
        service.start_discovery(DiscoveryRequest(query="manual query", channels=["web"]))
        assert [r["kind"] for r in service.queued()] == ["discovery", "following"]
        promoted = service.start_follow(follow["id"])
        assert promoted["manual"] and [r["kind"] for r in service.queued()] == ["discovery", "following"]
        service.start_discovery(DiscoveryRequest(query="later query", channels=["web"]))
        assert [r.get("query") for r in service.queued()][-1] == "later query"  # behind the promoted check
        assert store.follows()[0]["last_status"] == "queued"
        # A restart loses the in-memory queue; the topic must not keep claiming to wait.
        restarted = ContentService(Store(store.path), settings())
        restarted.start_tracking()
        assert store.follows()[0]["last_status"] == "cancelled"
        await restarted.close()
        await service.close()
    asyncio.run(scenario())
