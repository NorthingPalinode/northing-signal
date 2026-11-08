"""One bounded local worker, persistent content, and explicit refresh/cancel operations."""

import asyncio
import json
import logging
import time
from uuid import uuid4

from .collect import collect, enrich
from .discover import discover
from .engine import active_actions, project, stamp
from .intent import IntentEngine, recall_candidates
from .models import now
from .search_sources import SEARCH_SOURCES, source_access
from .tracking import matches, project_follows
from .understand import POLICY_HASH, Analyzer, has_material


class ContentService:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.sources = json.loads((settings.root / "data/briefing_sources.json").read_text("utf-8"))["sources"]
        self.analyzer = Analyzer(store, settings,
                                 requests_per_day=getattr(settings, "reader_requests_per_day", None),
                                 tokens_per_day=getattr(settings, "reader_tokens_per_day", None))
        self.task = None
        self.run = None
        self.tracker = None
        self.last_topic_collection = None
        self.intent = IntentEngine(self.analyzer, store)

    def view(self):
        materials, judgments = self.store.materials(), self.store.judgments(POLICY_HASH)
        preferences, interactions = self.store.preferences(), self.store.interactions()
        value = project(materials, judgments, preferences, interactions)
        saved_versions = {a["version"] for a in active_actions(interactions) if a["kind"] == "saved"}
        saved_materials = [self.store.material(v) for v in saved_versions]
        saved_view = project([m for m in saved_materials if m], judgments, preferences, interactions)
        value["saved_events"] = [e for e in saved_view["events"] if e["saved"]]
        follows = self.store.follows()
        assessments = {f["plan_hash"]: self.store.intent_assessments(f["plan_hash"])
                       for f in follows if f.get("intent_plan")}
        value["follows"] = project_follows(follows, value["events"], materials, assessments)
        value["search_sources"] = [{"id": key, **meta, "access": source_access(key, self.settings)} for key, meta in SEARCH_SOURCES.items()]
        value["usage"] = self.model_usage()
        value.update(preferences=self.store.preferences().model_dump(), sources=self.source_list(),
                     model_configured=self.analyzer.configured, run=self.run, policy=POLICY_HASH,
                     last_visit=self.store.last_visit())
        return value

    def source_list(self):
        states = self.store.source_states()
        result = [{**{k: s[k] for k in ("id", "name", "role", "url", "kind")},
                   "state": states.get(s["id"], {"status": "not_checked"})} for s in self.sources]
        for key, meta in SEARCH_SOURCES.items():
            source_id = key + "-discovery"
            state = states.get(source_id, {"status": "not_checked"})
            result.append({"id": source_id, "name": meta["name"], "role": meta["role"],
                           "url": meta["url"], "description": "官方 API 检索近期公开帖子正文" if source_access(key, self.settings) == "platform_api" else meta["description"],
                           "access": source_access(key, self.settings), "kind": "search", "state": state})
        return result

    def model_usage(self):
        receipts = self.store.receipts_today()
        return {"requests_today": len(receipts),
                "tokens_today": sum(r.get("charged_tokens", 0) for r in receipts),
                "request_limit": self.analyzer.requests_per_day,
                "token_limit": self.analyzer.tokens_per_day}

    def start_discovery(self, request):
        if self.task and not self.task.done():
            raise ValueError("已有更新正在处理")
        self.run = {"id": str(uuid4()), "kind": "discovery", "query": request.query,
                    "channels": request.channels,
                    "state": "running", "stage": "discovering", "started_at": now(),
                    "sources_done": 0, "analyzed": 0, "failed": 0, "errors": [], "snapshot_id": None}
        self.task = asyncio.create_task(self.discover(request.query, self.run))
        return self.run

    async def discover(self, query, run):
        try:
            related = []
            intent_follow = None
            if run.get("follow_id"):
                follow = next(f for f in self.store.follows() if f["id"] == run["follow_id"])
                plan = follow.get("intent_plan")
                intent_follow = follow if plan else None
                if plan and not follow.get("confirmed_at"):
                    raise ValueError("追踪方案尚未确认")
                if (not plan or plan["include_feeds"]) and (self.last_topic_collection is None or time.monotonic() - self.last_topic_collection >= 1800):
                    await collect(self.store, self.sources, limit=3)
                    self.last_topic_collection = time.monotonic()
                if plan:
                    related = recall_candidates(plan, self.store.materials(), self.store.intent_assessments(follow["plan_hash"]), self.store.judgments(POLICY_HASH))
                else:
                    related = [m for m in self.store.materials() if matches(follow, m.title + " " + m.text)]
                    related.sort(key=lambda m: m.published_at or m.captured_at, reverse=True)
                await enrich(self.store, limit=2, materials=related[:4])
                latest = {m.id: m for m in self.store.materials()}
                related = [latest[m.id] for m in related[:6]]
            if intent_follow:
                searches = intent_follow["intent_plan"]["searches"]
                cursor = intent_follow.get("search_cursor", 0)
                selected = [searches[(cursor + i) % len(searches)] for i in range(min(2, len(searches)))]
                run["searches"] = selected
                found = []
                for search in selected:
                    found.extend(await discover(self.store, search["query"], limit=3, channels=[search["source"]], settings=self.settings))
                self.store.update_follow(intent_follow["id"], search_cursor=cursor + len(selected), last_searches=selected)
            else:
                found = await discover(self.store, query, limit=4, channels=run.get("channels"), settings=self.settings)
            found = list({m.version: m for m in related + found}.values())
            run.update(found=len(found), result_versions=[m.version for m in found])
            if run.get("follow_id"):
                follow = next(f for f in self.store.follows() if f["id"] == run["follow_id"])
                ids = list(dict.fromkeys([m.id for m in found] + follow.get("material_ids", [])))[:200]
                self.store.update_follow(follow["id"], material_ids=ids)
            states = self.store.source_states()
            checked = {s["source"] + "-discovery" for s in run.get("searches", [])} if intent_follow else {s + "-discovery" for s in run.get("channels", ["web", "arxiv", "github"])}
            if any(states.get(key, {}).get("status") == "error" for key in checked):
                run["errors"].append("source_unavailable")
            candidates = found
            if intent_follow:
                candidates = recall_candidates(intent_follow["intent_plan"], self.store.materials(),
                                                self.store.intent_assessments(intent_follow["plan_hash"]),
                                                self.store.judgments(POLICY_HASH))
                ids = list(dict.fromkeys([m.id for m in candidates] + ids))[:200]
                self.store.update_follow(intent_follow["id"], material_ids=ids)
            await self.analyze(candidates, run, 6)
            if intent_follow:
                judgments = self.store.judgments(POLICY_HASH)
                eligible = [m for m in candidates if m.version in judgments]
                if eligible:
                    try:
                        run["stage"] = "matching_intent"
                        results = await self.intent.evaluate(intent_follow, eligible[:6])
                        await asyncio.sleep(0)
                        self.store.assess_intent(intent_follow["plan_hash"], results)
                        run["intent_matched"] = sum(v["relevant"] for v in results.values())
                    except ValueError as error:
                        run["errors"].append(str(error))
            await asyncio.sleep(0)
            run.update(state="completed", finished_at=now())
            run["snapshot_id"] = self.store.snapshot(self.view())
        except asyncio.CancelledError:
            run.update(state="cancelled", finished_at=now())
        except Exception as error:
            run.update(state="failed", finished_at=now())
            code = str(error) if isinstance(error, ValueError) else type(error).__name__
            run["errors"].append(code)
        finally:
            if run.get("follow_id"):
                status = "ok" if run["state"] == "completed" and not run["failed"] and not run["errors"] else "partial"
                if run["state"] in {"cancelled", "failed"}:
                    status = run["state"]
                self.store.update_follow(run["follow_id"], last_checked=now(), last_status=status,
                                         last_found=run.get("found", 0), last_errors=run["errors"])

    async def analyze(self, materials, run, limit):
        old = self.store.judgments(POLICY_HASH)
        pending = [m for m in materials if m.version not in old and has_material(m)][:limit]
        run.update(stage="understanding", total=len(pending))
        if not self.analyzer.configured and pending:
            run["failed"] += len(pending)
            run["errors"].append("model_not_configured")
            return
        for i in range(0, len(pending), 2):
            batch = pending[i:i + 2]
            try:
                results = await self.analyzer.batch(batch)
                await asyncio.sleep(0)
                for version, value in results.items():
                    self.store.judge(version, POLICY_HASH, value, self.settings.llm_model)
                run["analyzed"] += len(results)
                run["failed"] += len(batch) - len(results)
            except ValueError as error:
                code = str(error)
                run["failed"] += len(batch)
                if code not in run["errors"]:
                    run["errors"].append(code)
                if code in {"daily_model_budget_reached", "model_not_configured"}:
                    break

    def start_follow(self, key):
        follow = next((f for f in self.store.follows() if f["id"] == key), None)
        if not follow or not follow["active"]:
            raise ValueError("请先启用这个话题的追踪")
        if not follow.get("intent_plan") or not follow.get("confirmed_at"):
            raise ValueError("请先描述需求并确认追踪方案")
        if self.task and not self.task.done():
            raise ValueError("已有更新正在处理，话题会在之后继续追踪")
        self.store.update_follow(key, last_checked=now(), last_status="checking")
        self.run = {"id": str(uuid4()), "kind": "following", "follow_id": key, "query": follow["query"],
                    "follow_name": follow["name"], "state": "running", "stage": "discovering", "started_at": now(),
                    "sources_done": 0, "analyzed": 0, "failed": 0, "errors": [], "snapshot_id": None}
        self.task = asyncio.create_task(self.discover(follow["query"], self.run))
        return self.run

    def start_tracking(self):
        for follow in self.store.follows():
            if follow["active"] and not follow.get("intent_plan"):
                self.store.update_follow(follow["id"], active=False, last_status="needs_intent")
        if not self.tracker or self.tracker.done():
            self.tracker = asyncio.create_task(self.tracking_loop())

    def track_due(self):
        if self.task and not self.task.done():
            return
        clock = stamp(now())
        due = [f for f in self.store.follows() if f["active"] and f.get("intent_plan") and f.get("confirmed_at") and
               (not f.get("last_checked") or (clock - stamp(f["last_checked"])).total_seconds() >=
                f.get("intent_plan", {}).get("interval_minutes", 30) * 60)]
        if due:
            self.start_follow(min(due, key=lambda f: f.get("last_checked") or "")["id"])

    async def tracking_loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                self.track_due()
            except Exception as error:
                logging.getLogger(__name__).warning("Topic tracking check failed: %s", type(error).__name__)

    def start(self, request):
        if self.task and not self.task.done():
            raise ValueError("已有更新正在处理")
        self.run = {"id": str(uuid4()), "kind": "refresh", "state": "running", "stage": "collecting", "started_at": now(),
                    "sources_done": 0, "analyzed": 0, "failed": 0, "errors": [], "snapshot_id": None}
        self.task = asyncio.create_task(self.refresh(request, self.run))
        return self.run

    async def refresh(self, request, run):
        def progress(name, state):
            run["sources_done"] += 1
            run["current_source"] = name
        try:
            await collect(self.store, self.sources, request.limit_per_source, progress)
            run["stage"] = "reading"
            await enrich(self.store, limit=min(24, request.analyze_limit))
            run["stage"] = "understanding"
            candidates = self.store.materials()
            candidates.sort(key=lambda m: m.published_at or m.captured_at, reverse=True)
            await self.analyze(candidates, run, request.analyze_limit)
            run["stage"] = "publishing"
            await asyncio.sleep(0)
            run["state"] = "completed"
            run["finished_at"] = now()
            run["snapshot_id"] = self.store.snapshot(self.view())
        except asyncio.CancelledError:
            run.update(state="cancelled", finished_at=now())
        except Exception as error:
            run.update(state="failed", finished_at=now())
            run["errors"].append(type(error).__name__)

    async def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await self.task
        return self.run

    async def close(self):
        if self.tracker and not self.tracker.done():
            self.tracker.cancel()
            try:
                await self.tracker
            except asyncio.CancelledError:
                pass
        await self.cancel()
