"""One bounded local worker, persistent content, and explicit refresh/cancel operations."""

import asyncio
import json
import logging
import time
from collections import deque
from uuid import uuid4

from .collect import collect, enrich
from .discover import discover
from .engine import active_actions, frame_key, occurrences, project, stamp, text_key
from .events import assign, frame_of, resolve
from .intent import IntentEngine, recall_candidates
from .models import POLICY_EPOCH, Preferences, assessment_of, day_start, digest, now
from .search_sources import SEARCH_SOURCES, source_access
from .tracking import matches, project_follows
from .understand import POLICY_HASH, Analyzer, has_material

PROJECTION_MAX_AGE = 600
# Later batches would fail the same way: no budget, no model, or the provider is unreachable.
QUEUE_LIMIT = 8
STOP_ANALYSIS = {"daily_model_budget_reached", "model_not_configured", "model_request_failed"}


class ContentService:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.sources = json.loads((settings.root / "data/briefing_sources.json").read_text("utf-8"))["sources"]
        self.analyzer = Analyzer(store, settings,
                                 requests_per_day=getattr(settings, "reader_requests_per_day", None),
                                 tokens_per_day=getattr(settings, "reader_tokens_per_day", None))
        self.task = None
        self.run = None
        self.queue = []  # [(run, job)] waiting for the single worker
        self.closing = False
        self.tracker = None
        self.last_topic_collection = None
        self.intent = IntentEngine(self.analyzer, store)
        store.adopt_policy(POLICY_HASH)
        self._projection = (None, 0, None)
        self._assigned = None  # content revision whose materials all have events

    def projection(self):
        """Events, saved events and follows: recomputed only after stored data changes.

        Revisions cover every table the projection reads; the age limit keeps time-based
        ranking (recency decay, the 30-day window) from going stale on an idle database.
        """
        self.assign_events()
        revision = self.store.revision()
        cached_revision, cached_at, cached = self._projection
        if cached_revision == revision and time.monotonic() - cached_at < PROJECTION_MAX_AGE:
            return cached
        materials, judgments = self.store.materials(), self.store.judgments()
        preferences = self.store.preferences()
        membership = self.membership()
        interactions = self.attribute(self.store.interactions(), membership)
        value = project(materials, judgments, preferences, interactions, membership=membership)
        saved_versions = {a["version"] for a in active_actions(interactions) if a["kind"] == "saved"}
        saved_view = project(self.store.materials_by_versions(saved_versions), judgments, preferences,
                             interactions, membership=membership)
        value["saved_events"] = [e for e in saved_view["events"] if e["saved"]]
        follows = self.store.follows()
        assessments = {f["plan_hash"]: self.store.intent_assessments(f["plan_hash"])
                       for f in follows if f.get("intent_plan")}
        value["follows"] = project_follows(follows, value["events"], materials, assessments)
        value["preferences"] = preferences.model_dump()
        failures = self.store.failures()
        for row in value["archive"]:
            failure = failures.get(row["version"]) if row["status"] == "pending" else None
            if failure:
                row.update(status="failed" if failure["gave_up"] else "retrying",
                           failure={k: failure[k] for k in ("code", "attempts", "retry_at")})
        value["counts"].update(pending=sum(r["status"] in {"pending", "retrying"} for r in value["archive"]),
                               failed=sum(r["status"] == "failed" for r in value["archive"]))
        self._projection = (revision, time.monotonic(), value)
        return value

    def view(self):
        value = dict(self.projection())
        value["search_sources"] = [{"id": key, **meta, "access": source_access(key, self.settings)} for key, meta in SEARCH_SOURCES.items()]
        value["usage"] = self.model_usage()
        value.update(sources=self.source_list(),
                     model_configured=self.analyzer.configured, run=self.run, queue=self.queued(),
                     policy=POLICY_HASH,
                     last_visit=self.store.last_visit())
        return value

    def assign_events(self):
        """Give newly judged materials a lasting event; the first run adopts the old grouping.

        Returns the content revision at which every material has its event.
        """
        revision = self.store.revision()[0]
        if revision == self._assigned:
            return revision
        materials, judgments = self.store.materials(), self.store.judgments()
        found = list(occurrences(materials, judgments))
        if not self.store.flag("events_backfilled"):
            # Same grouping the projection computed until now: event ids and actions stay valid.
            version_ids = {m.version: m.id for m in materials}
            first = {}
            for material, assessment in found:
                first.setdefault(material.id, (material, assessment))
            rows, created = [], {}
            for event in project(materials, judgments, Preferences())["events"]:
                ids = [version_ids[t["version"]] for t in event["timeline"]]
                rows += [(material_id, event["id"], "migrated", None) for material_id in ids]
                created[event["id"]] = frame_of(*min((first[i] for i in ids),
                                                      key=lambda row: (row[0].captured_at, row[0].id)))
            self.store.assign_events(rows, created, backfill=True)
        members, live, aliases = self.store.event_state()
        texts = {}
        for material, _ in found:
            if material.id in members and (key := text_key(material)):
                texts.setdefault(key, resolve(members[material.id], aliases))
        rows, created = assign(found, dict(members), dict(live), aliases, texts)
        if rows:
            self.store.assign_events(rows, created)
        self._assigned = self.store.revision()[0]
        return self._assigned

    def membership(self, revision=None):
        members, _, aliases = self.store.event_state(revision)
        if not aliases:
            return members  # nothing merged: stored ids are current (read-only use)
        return {material: resolve(event, aliases) for material, event in members.items()}

    def attribute(self, interactions, membership):
        """Credit each action to the event its version's material belongs to now (splits, merges)."""
        version_ids = self.store.version_ids()
        return [{**a, "event_id": membership.get(version_ids.get(a["version"]), a["event_id"])}
                for a in interactions]

    def record_interaction(self, body):
        if body.kind != "retract":
            revision = self.assign_events()  # read once: this runs for every card shown
            if self.event_of(body.version, revision) != self.resolve(body.event_id, revision):
                raise LookupError("内容版本不存在，请重新读取")
        return self.store.interact(body)

    def resolve(self, event_id, revision=None):
        return resolve(event_id, self.store.event_state(revision)[2])

    def event_of(self, version, revision=None):
        """The event a material version is shown under, or None when it is not in any event."""
        if revision is None:
            revision = self.assign_events()
        material_id = self.store.version_ids(revision).get(version)
        if material_id is None:
            return None
        event = self.membership(revision).get(material_id)
        if event:
            return event
        # Not assigned (e.g. a saved revision whose newest text is not judged as AI news):
        # the projection names it from its own judgment, as before persistence.
        judgment = self.store.judgment(version)
        if not judgment or judgment.get("relevance") != "ai":
            return None
        return frame_key(assessment_of(judgment)) or material_id

    def split_event(self, event_id, version):
        """Move one material (and its later revisions) out of an event into its own."""
        self.assign_events()
        event, material_id = self.resolve(event_id), self.store.version_ids().get(version)
        membership = self.membership()
        if material_id is None or membership.get(material_id) != event:
            raise LookupError("这条报道不在该事件中，请重新读取")
        if sum(e == event for e in membership.values()) < 2:
            raise ValueError("事件只剩这一条报道，无法再拆分")
        target = "split-" + digest([event, material_id, now()])[:18]
        judgment = self.store.judgment(version)
        material = self.store.material(version)
        frame = frame_of(material, assessment_of(judgment)) if judgment else {}
        self.store.regroup({"kind": "split", "event": event, "material": material_id, "new_event": target},
                           [material_id], target, frame=frame)
        return target

    def merge_events(self, source, target):
        """Fold one event into another; the old id keeps resolving to the merged event."""
        self.assign_events()
        source, target = self.resolve(source), self.resolve(target)
        _, live, _ = self.store.event_state()
        if source not in live or target not in live:
            raise LookupError("事件不存在，请重新读取")
        if source == target:
            raise ValueError("不能把事件合并到它自己")
        moving = [m for m, e in self.membership().items() if e == source]
        self.store.regroup({"kind": "merge", "event": source, "into": target, "materials": moving},
                           moving, target, alias=source)

    def snapshot_view(self):
        """What a past briefing needs to be re-read: its ranked events, not the whole library."""
        value = self.view()
        shown = set(value["focus"]) | set(value["radar"])
        return {**value, "events": [e for e in value["events"] if e["id"] in shown],
                "archive": [], "saved_events": [], "follows": [], "run": None, "queue": []}

    def source_list(self):
        states = self.store.source_states()
        result = [{**{k: s[k] for k in ("id", "name", "role", "url", "kind")},
                   "url": s.get("original_url", s["url"]),
                   "description": s.get("description", ""), "priority": s.get("priority", 1),
                   "state": states.get(s["id"], {"status": "not_checked"})}
                  for s in sorted(self.sources, key=lambda s: s.get("priority", 1))]
        for key, meta in SEARCH_SOURCES.items():
            source_id = key + "-discovery"
            state = states.get(source_id, {"status": "not_checked"})
            result.append({"id": source_id, "name": meta["name"], "role": meta["role"],
                           "url": meta["url"], "description": "官方 API 检索近期公开帖子正文" if source_access(key, self.settings) == "platform_api" else meta["description"],
                           "access": source_access(key, self.settings), "kind": "search", "state": state})
        return result

    def model_usage(self):
        receipts = self.store.receipts_today(day_start(getattr(self.settings, "reader_timezone", "")))
        return {"requests_today": len(receipts),
                "tokens_today": sum(r.get("charged_tokens", 0) for r in receipts),
                "request_limit": self.analyzer.requests_per_day,
                "token_limit": self.analyzer.tokens_per_day}

    def start_discovery(self, request):
        run = self.new_run("discovery", "discovering", query=request.query, channels=request.channels)
        return self.submit(run, lambda run: self.discover(request.query, run))

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
                    related = recall_candidates(plan, await asyncio.to_thread(self.store.materials), self.store.intent_assessments(follow["plan_hash"]), self.store.judgments())
                else:
                    related = [m for m in await asyncio.to_thread(self.store.materials) if matches(follow, m.title + " " + m.text)]
                    related.sort(key=lambda m: m.published_at or m.captured_at, reverse=True)
                await enrich(self.store, limit=2, materials=related[:4])
                latest = {m.id: m for m in await asyncio.to_thread(self.store.materials)}
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
                candidates = recall_candidates(intent_follow["intent_plan"], await asyncio.to_thread(self.store.materials),
                                                self.store.intent_assessments(intent_follow["plan_hash"]),
                                                self.store.judgments())
                ids = list(dict.fromkeys([m.id for m in candidates] + ids))[:200]
                self.store.update_follow(intent_follow["id"], material_ids=ids)
            await self.analyze(candidates, run, getattr(self.settings, "reader_follow_analyze_limit", 6))
            if intent_follow:
                judgments = self.store.judgments()
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
            # Build the snapshot first: a cancel while it is prepared publishes nothing.
            snapshot = await asyncio.to_thread(self.snapshot_view)
            run.update(state="completed", finished_at=now())
            run["snapshot_id"] = self.store.snapshot(snapshot)
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

    def pending_judgments(self, materials, limit):
        """Unjudged materials first, then ones judged under an older epoch; skips backoff."""
        judgments, failures, clock = self.store.judgments(), self.store.failures(), now()

        def ready(material):
            failure = failures.get(material.version)
            return has_material(material) and (not failure or (not failure["gave_up"] and failure["retry_at"] <= clock))
        fresh = [m for m in materials if m.version not in judgments and ready(m)]
        stale = [m for m in materials if m.version in judgments
                 and judgments[m.version]["epoch"] < POLICY_EPOCH and ready(m)]
        return (fresh + stale)[:limit]

    async def analyze(self, materials, run, limit):
        pending = self.pending_judgments(materials, limit)
        run.update(stage="understanding", total=len(pending))
        if not self.analyzer.configured and pending:
            run["failed"] += len(pending)
            run["errors"].append("model_not_configured")
            return
        size = getattr(self.settings, "reader_batch_size", 4)
        batches = deque(pending[i:i + size] for i in range(0, len(pending), size))
        stopped = set()

        async def worker():
            while batches and not stopped:
                batch = batches.popleft()
                try:
                    results = await self.analyzer.batch(batch)
                    await asyncio.sleep(0)
                    for version, value in results.items():
                        self.store.judge(version, POLICY_HASH, value, self.settings.llm_model, POLICY_EPOCH)
                    run["analyzed"] += len(results)
                    run["failed"] += len(batch) - len(results)
                except ValueError as error:
                    code = str(error)
                    if code.endswith(":model_output_truncated") and len(batch) > 1:
                        half = len(batch) // 2  # shorter replies fit; retry both halves next
                        batches.extendleft([batch[half:], batch[:half]])
                        continue
                    run["failed"] += len(batch)
                    if code not in run["errors"]:
                        run["errors"].append(code)
                    if code in STOP_ANALYSIS:
                        stopped.add(code)
        await asyncio.gather(*(worker() for _ in range(getattr(self.settings, "reader_model_concurrency", 1))))

    def new_run(self, kind, stage, **fields):
        return {"id": str(uuid4()), "kind": kind, **fields, "state": "queued", "stage": stage,
                "queued_at": now(), "sources_done": 0, "analyzed": 0, "failed": 0, "errors": [],
                "snapshot_id": None}

    def busy(self):
        return bool(self.task and not self.task.done())

    def pending(self, match):
        """The running or queued run that satisfies match, if any."""
        if self.busy() and self.run and match(self.run):
            return self.run
        return next((run for run, _ in self.queue if match(run)), None)

    def submit(self, run, job, *, manual=True):
        """Run now when idle, otherwise queue: manual work goes ahead of scheduled checks."""
        run["manual"] = manual
        if not self.busy():
            return self.launch(run, job)
        if len(self.queue) >= QUEUE_LIMIT:
            raise ValueError("排队的任务已满，请等当前任务完成后再试")
        position = len(self.queue)
        if manual:
            position = next((i for i, (queued, _) in enumerate(self.queue) if not queued["manual"]), position)
        self.queue.insert(position, (run, job))
        return run

    def launch(self, run, job):
        run.update(state="running", started_at=now())
        self.run = run
        self.task = asyncio.create_task(self.execute(run, job))
        return run

    async def execute(self, run, job):
        try:
            await job(run)
        except asyncio.CancelledError:
            self.mark_cancelled(run)
        finally:
            if self.queue and not self.closing:
                self.launch(*self.queue.pop(0))

    def mark_cancelled(self, run):
        """For a job cancelled before its own handler ran (or before it started at all)."""
        if run["state"] in {"running", "queued"}:
            run.update(state="cancelled", finished_at=now())
            if run.get("follow_id"):
                self.store.update_follow(run["follow_id"], last_status="cancelled")

    def start_follow(self, key, manual=True):
        follow = next((f for f in self.store.follows() if f["id"] == key), None)
        if not follow or not follow["active"]:
            raise ValueError("请先启用这个话题的追踪")
        if not follow.get("intent_plan") or not follow.get("confirmed_at"):
            raise ValueError("请先描述需求并确认追踪方案")
        existing = self.pending(lambda run: run.get("follow_id") == key)
        if existing:
            if manual and existing["state"] == "queued" and not existing["manual"]:
                # Asked for now: move the scheduled check up with the other manual work.
                entry = next(e for e in self.queue if e[0] is existing)
                self.queue.remove(entry)
                self.submit(*entry)
            return existing

        async def job(run):
            self.store.update_follow(key, last_checked=now(), last_status="checking")
            await self.discover(follow["query"], run)
        run = self.submit(self.new_run("following", "discovering", follow_id=key, query=follow["query"],
                                       follow_name=follow["name"]), job, manual=manual)
        if run["state"] == "queued":
            self.store.update_follow(key, last_status="queued")
        return run

    def start_tracking(self):
        for follow in self.store.follows():
            if follow["active"] and not follow.get("intent_plan"):
                self.store.update_follow(follow["id"], active=False, last_status="needs_intent")
            elif follow.get("last_status") in {"queued", "checking"}:
                # The queue lives in memory: a check queued or running before a restart is gone.
                self.store.update_follow(follow["id"], last_status="cancelled")
        if not self.tracker or self.tracker.done():
            self.tracker = asyncio.create_task(self.tracking_loop())

    def track_due(self):
        clock = stamp(now())
        due = [f for f in self.store.follows() if f["active"] and f.get("intent_plan") and f.get("confirmed_at") and
               (not f.get("last_checked") or (clock - stamp(f["last_checked"])).total_seconds() >=
                f.get("intent_plan", {}).get("interval_minutes", 30) * 60)]
        for follow in sorted(due, key=lambda f: f.get("last_checked") or ""):
            if len(self.queue) >= QUEUE_LIMIT:
                break
            self.start_follow(follow["id"], manual=False)

    async def tracking_loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                self.track_due()
            except Exception as error:
                logging.getLogger(__name__).warning("Topic tracking check failed: %s", type(error).__name__)

    def start(self, request):
        existing = self.pending(lambda run: run["kind"] == "refresh")
        if existing:
            return existing
        return self.submit(self.new_run("refresh", "collecting"), lambda run: self.refresh(request, run))

    async def refresh(self, request, run):
        def progress(name, state):
            run["sources_done"] += 1
            run["current_source"] = name
        try:
            await collect(self.store, self.sources, request.limit_per_source, progress)
            run["stage"] = "reading"
            await enrich(self.store, limit=min(24, request.analyze_limit))
            run["stage"] = "understanding"
            candidates = await asyncio.to_thread(self.store.materials)
            candidates.sort(key=lambda m: m.published_at or m.captured_at, reverse=True)
            await self.analyze(candidates, run, request.analyze_limit)
            run["stage"] = "publishing"
            snapshot = await asyncio.to_thread(self.snapshot_view)
            run["state"] = "completed"
            run["finished_at"] = now()
            run["snapshot_id"] = self.store.snapshot(snapshot)
        except asyncio.CancelledError:
            run.update(state="cancelled", finished_at=now())
        except Exception as error:
            run.update(state="failed", finished_at=now())
            run["errors"].append(type(error).__name__)

    async def cancel(self, run_id=None):
        """Stop the running job (default) or drop a queued one; the queue then moves on."""
        if run_id and run_id != (self.run or {}).get("id"):
            for index, (run, _) in enumerate(self.queue):
                if run["id"] == run_id:
                    self.queue.pop(index)
                    self.mark_cancelled(run)
                    return run
            raise LookupError("这个任务已经结束或不存在")
        if self.busy():
            task, run = self.task, self.run
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # A task cancelled before its first step never ran execute(): settle it here.
            self.mark_cancelled(run)
            if self.queue and not self.closing and not self.busy():
                self.launch(*self.queue.pop(0))
            return run
        return self.run

    async def cancel_follow(self, key):
        """Drop queued checks of a topic and stop its running one; True when anything stopped."""
        stopped = False
        for run, _ in list(self.queue):
            if run.get("follow_id") == key:
                await self.cancel(run["id"])
                stopped = True
        if self.busy() and self.run.get("follow_id") == key:
            await self.cancel()
            stopped = True
        return stopped

    def queued(self):
        return [run for run, _ in self.queue]

    async def close(self):
        self.closing = True
        for run, _ in self.queue:
            run.update(state="cancelled", finished_at=now())
        self.queue.clear()
        if self.tracker and not self.tracker.done():
            self.tracker.cancel()
            try:
                await self.tracker
            except asyncio.CancelledError:
                pass
        await self.cancel()
