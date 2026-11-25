"""One bounded local worker, persistent content, and explicit refresh/cancel operations."""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from .collect import collect, enrich
from .discover import discover
from .engine import active_actions, frame_key, occurrences, project, stamp, text_key
from .events import assign, frame_of, resolve
from .github import KINDS as RANKINGS
from .github import LINE_BATCH, LINE_PROMPT, line_payload, line_validator, missing_lines, with_lines
from .intent import IntentEngine, recall_candidates
from .lenses import Lenses
from .models import (
    POLICY_EPOCH,
    TIMEZONES,
    Interaction,
    Preferences,
    RefreshRequest,
    assessment_of,
    day_start,
    digest,
    now,
)
from .publish import publish
from .relate import BATCH, MERGING, pair_id
from .relate import POLICY as RELATION_POLICY
from .relate import PROMPT as RELATION_PROMPT
from .relate import candidates as relation_candidates
from .relate import payload as relation_payload
from .relate import validate as relation_validator
from .report import report_range, weekly_report
from .search_sources import SEARCH_SOURCES, source_access
from .store import LOCAL_USER
from .tracking import matches, project_follows
from .triage import triage
from .understand import POLICY_HASH, Analyzer, has_material

PROJECTION_MAX_AGE = 600
BRIEFED_DAYS = 7  # earlier briefings that count for carried stories (engine.RETURN_SOURCES)
PROJECTION_CACHE = 64  # readers whose projection is kept in memory
# Past briefings are saved for readers seen within this window when an update completes.
SNAPSHOT_ACTIVE_DAYS, SNAPSHOT_READERS = 30, 200
# Fields of another reader's run that may be shown: the worker is busy, not what they asked for.
SHARED_RUN_FIELDS = ("id", "kind", "state", "stage", "queued_at", "started_at", "finished_at",
                     "sources_done", "current_source", "analyzed", "failed", "manual", "trigger", "total")
# Later batches would fail the same way: no budget, no model, or the provider is unreachable.
QUEUE_LIMIT = 8
STOP_ANALYSIS = {"daily_model_budget_reached", "model_not_configured", "model_request_failed"}
# Scheduled briefing updates, in the reader's timezone (user request, 2026-11-11).
REFRESH_HOURS = (0, 12)


def refresh_slots(clock, zone=None, hours=REFRESH_HOURS):
    """(latest scheduled time at or before clock, the next one after it), as aware datetimes."""
    local = clock.astimezone(zone)
    day = local.replace(minute=0, second=0, microsecond=0)
    times = sorted([day.replace(hour=h) - timedelta(days=1) for h in hours]
                   + [day.replace(hour=h) for h in hours] + [day.replace(hour=h) + timedelta(days=1) for h in hours])
    past = max(t for t in times if t <= local)
    return past, min(t for t in times if t > local)


class ContentService:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.sources = json.loads((settings.root / "data/briefing_sources.json").read_text("utf-8"))["sources"]
        # Sources whose reports arrive late by nature (curated paper lists) get a longer window.
        self.late_hours = {s["id"]: s["late_hours"] for s in self.sources if "late_hours" in s}
        # Company lines and the other lenses: the owner's editable table of companies and products.
        table = settings.root / "data/companies.json"
        self.lenses = Lenses(json.loads(table.read_text("utf-8"))["companies"] if table.exists() else [],
                             self.sources)
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
        self._projection = {}  # reader -> (revision, monotonic time, value)
        self._assigned = None  # content revision whose materials all have events

    def projection(self, user=LOCAL_USER):
        """One reader's events, saved events and follows: recomputed only after stored data changes.

        Revisions cover every table the projection reads; the age limit keeps time-based
        ranking (recency decay, the 30-day window) from going stale on an idle database.
        """
        self.assign_events()
        revision = self.store.revision()
        cached_revision, cached_at, cached = self._projection.get(user, (None, 0, None))
        if cached_revision == revision and time.monotonic() - cached_at < PROJECTION_MAX_AGE:
            return cached
        materials, judgments = self.store.materials(), self.store.judgments()
        preferences = self.store.preferences(user)
        membership = self.membership()
        interactions = self.attribute(self.store.interactions(user=user), membership)
        latest = self.store.last_refresh(completed=True)
        bounds = dict(briefing_at=latest["finished_at"], new_since=latest["started_at"]) if latest else {}
        bounds.update(refreshed=self.store.refresh_times(), late_hours=self.late_hours,
                      thresholds=self.thresholds(), briefed=self.briefed(latest, membership, user))
        value = project(materials, judgments, preferences, interactions, membership=membership, **bounds)
        saved_versions = {a["version"] for a in active_actions(interactions) if a["kind"] == "saved"}
        saved_view = project(self.store.materials_by_versions(saved_versions), judgments, preferences,
                             interactions, membership=membership, **bounds)
        value["last_refresh"] = latest
        value["saved_events"] = [e for e in saved_view["events"] if e["saved"]]
        for event in [*value["events"], *value["saved_events"]]:
            self.lenses.tag(event)
        value["companies"] = self.lenses.catalog()
        follows = self.store.follows(user)
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
        self._projection.pop(user, None)
        while len(self._projection) >= PROJECTION_CACHE:
            self._projection.pop(next(iter(self._projection)))  # oldest reader first
        self._projection[user] = (revision, time.monotonic(), value)
        return value

    def visible_run(self, run, user):
        """A run as `user` may see it: their own in full; someone else's only as "busy"."""
        if run is None or run.get("user_id", user) == user:
            return run
        if run["kind"] == "refresh":  # shared content: everyone may follow its progress
            return {k: v for k, v in run.items() if k != "user_id"}
        return {**{k: run.get(k) for k in SHARED_RUN_FIELDS}, "kind": "other", "errors": [],
                "snapshot_id": None}

    def view(self, user=LOCAL_USER):
        value = dict(self.projection(user))
        value["search_sources"] = [{"id": key, **meta, "access": source_access(key, self.settings)} for key, meta in SEARCH_SOURCES.items()]
        value["usage"] = self.model_usage()
        value.update(sources=self.source_list(),
                     model_configured=self.analyzer.configured, run=self.visible_run(self.run, user),
                     queue=[self.visible_run(r, user) for r in self.queued()],
                     policy=POLICY_HASH,
                     last_visit=self.store.last_visit(user),
                     previous_visit=self.store.previous_visit(user),
                     rankings=self.rankings())
        _, upcoming = refresh_slots(datetime.now(timezone.utc), self.zone())
        value["schedule"] = {"enabled": value["preferences"]["auto_refresh"], "hours": list(REFRESH_HOURS),
                             "next": upcoming.astimezone(timezone.utc).isoformat()}
        site = getattr(self.settings, "reader_timezone", "")
        value["timezone"] = {"zone": self.reader_zone_name(user), "site": site,
                             "options": [{"id": key, "label": label} for key, label in TIMEZONES.items()]}
        return value

    def thresholds(self):
        return {"official": getattr(self.settings, "reader_threshold_official", 9),
                "other": getattr(self.settings, "reader_threshold_other", 9)}

    def zone(self):
        """The site timezone: update schedule, budgets, quotas and public digest dates."""
        name = getattr(self.settings, "reader_timezone", "")
        return ZoneInfo(name) if name else None

    def publish_zone(self):
        """The public digest's timezone (Beijing by default); empty follows the site."""
        name = getattr(self.settings, "reader_publish_timezone", "")
        return ZoneInfo(name) if name else self.zone()

    def reader_zone_name(self, user=LOCAL_USER):
        """The reader's own timezone for what they see; empty means the system timezone."""
        return self.store.preferences(user).timezone or getattr(self.settings, "reader_timezone", "")

    def reader_zone(self, user=LOCAL_USER):
        name = self.reader_zone_name(user)
        return ZoneInfo(name) if name else None

    def refresh_due(self, clock=None):
        """Start the scheduled update when the latest 00:00/12:00 slot has no update yet.

        A slot missed while the service was off runs once at the next check after start.
        Any update counts, manual ones included, so a fresh manual update is not repeated.
        """
        if not self.store.preferences().auto_refresh:
            return None
        slot, _ = refresh_slots(clock or datetime.now(timezone.utc), self.zone())
        last = self.store.last_refresh()
        if (last and stamp(last["started_at"]) and stamp(last["started_at"]) >= slot) \
                or self.pending(lambda run: run["kind"] == "refresh"):
            return None
        return self.start(RefreshRequest(), manual=False)

    def weekly_report(self, kind="recent", user=LOCAL_USER):
        zone = self.reader_zone(user)
        clock = datetime.now(timezone.utc)
        start, end = report_range(kind, clock, zone)
        value = self.projection(user)
        events = {e["id"]: e for e in value["events"]}
        for event in value.get("saved_events", []):
            events.setdefault(event["id"], event)
        return weekly_report(list(events.values()), value["follows"], start, end, generated_at=clock, zone=zone)

    def publish_digest(self, out_dir=None, clock=None):
        """Write the public digest. Neutral projection: no preferences, actions or follows."""
        target = self.settings.publish_path(out_dir)
        if target is None:
            raise ValueError("未设置公开日报目录（READER_PUBLISH_DIR 或 --out）")
        events = self.neutral_events()
        return publish(events, target, clock=clock, zone=self.publish_zone(),
                       base_url=getattr(self.settings, "reader_public_url", ""))

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

    def briefed(self, latest, membership, user=LOCAL_USER):
        """Events that briefings before the latest update put in focus or radar, within BRIEFED_DAYS.

        Snapshots are written during an update, before it records its end, which moves the reader
        revision: the projection cache sees new ones without triggers of their own."""
        if not latest or not latest.get("started_at"):
            return frozenset()
        start = stamp(latest["started_at"])
        if not start:
            return frozenset()
        versions = self.store.briefed_versions(
            (start - timedelta(days=BRIEFED_DAYS)).isoformat(), latest["started_at"], user)
        version_ids = self.store.version_ids()
        return frozenset(e for v in versions if (e := membership.get(version_ids.get(v))))

    def attribute(self, interactions, membership):
        """Credit each action to the event its version's material belongs to now (splits, merges)."""
        version_ids = self.store.version_ids()
        return [{**a, "event_id": membership.get(version_ids.get(a["version"]), a["event_id"])}
                for a in interactions]

    def record_interaction(self, body, user=LOCAL_USER):
        if body.kind != "retract":
            revision = self.assign_events()  # read once: this runs for every card shown
            if self.event_of(body.version, revision) != self.resolve(body.event_id, revision):
                raise LookupError("内容版本不存在，请重新读取")
        created = self.store.interact(body, user)
        if created and body.kind == "opened":
            self.know_on_open(body, user)
            self.see_in_follows(body.event_id, user)
        return created

    def see_in_follows(self, event_id, user=LOCAL_USER):
        """Reading a story clears it from every topic's "new" count (user request, 2026-11-12).

        All of the event's current versions count as seen; a later report or correction
        makes it new again, as with "mark all as read". Uses the projection the page was
        built from when there is one: opening a story should not recompute the briefing.
        """
        cached = self._projection.get(user)
        value = cached[2] if cached else self.projection(user)
        event_id = self.resolve(event_id)
        event = next((e for e in value["events"] if e["id"] == event_id), None)
        if not event:
            return
        versions = {row["version"] for row in event["timeline"]}
        stored = {f["id"]: f for f in self.store.follows(user)}
        for follow in value["follows"]:
            if event_id in follow["unread_ids"] and follow["id"] in stored:
                seen = set(stored[follow["id"]].get("seen_versions", [])) | versions
                self.store.update_follow(follow["id"], user=user, seen_versions=sorted(seen))

    def know_on_open(self, opened, user=LOCAL_USER):
        """Opening a story marks this version known, once (user request, 2026-11-11).

        Any earlier "known" for the version, even one the reader took back, stops it: after
        "mark as not known", reopening the story leaves that choice alone.
        """
        if any(a["version"] == opened.version for a in self.store.interactions(["known"], user=user)):
            return
        self.store.interact(Interaction(request_id="auto-known-" + digest(opened.request_id)[:24],
                                        event_id=opened.event_id, version=opened.version, kind="known"), user)

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

    def neutral_events(self):
        """Events under default preferences and no reader actions: shared, not personal."""
        self.assign_events()
        return project(self.store.materials(), self.store.judgments(), Preferences(),
                       membership=self.membership(), refreshed=self.store.refresh_times(),
                       late_hours=self.late_hours, thresholds=self.thresholds())["events"]

    async def relate_events(self, run, limit=None):
        """Ask the model how similar recent events relate; merge same occurrences and follow-ups.

        Candidates come from relate.candidates (free); each answer is stored, so a pair is never
        asked twice. A model failure stops this step only; the update itself carries on.
        """
        limit = getattr(self.settings, "reader_relation_pairs", 24) if limit is None else limit
        if not limit or not self.analyzer.configured:
            return
        events = await asyncio.to_thread(self.neutral_events)
        # A ROUNDUP answer from an older prompt may be stale: a roundup no longer leads an event.
        checked_pairs = self.store.relation_pairs(
            recheck=lambda relation, data: relation == "ROUNDUP" and data.get("policy") != RELATION_POLICY)
        pairs = relation_candidates(events, checked_pairs, clock=datetime.now(timezone.utc), limit=limit)
        checked = merged = 0
        for start in range(0, len(pairs), BATCH):
            batch = pairs[start:start + BATCH]
            ids = [pair_id(older, newer) for _, older, newer in batch]
            try:
                answers = await self.analyzer.request_json(
                    RELATION_PROMPT, relation_payload(batch), relation_validator(ids),
                    purpose="event_relation", maximum=1800)
            except ValueError as error:
                run["errors"].append("relation_" + str(error).removeprefix("intent_"))
                break
            rows = []
            for score, older, newer in batch:
                answer = answers[pair_id(older, newer)]
                outcome = None
                if answer.relation in MERGING:
                    outcome = await asyncio.to_thread(self.merge_by_model, older["id"], newer["id"], answer)
                    merged += outcome == "merged"
                rows.append((older["id"], newer["id"], answer.relation,
                             {"reason": answer.reason, "recall": score, "outcome": outcome,
                              "model": getattr(self.settings, "llm_model", ""), "policy": RELATION_POLICY}))
                checked += 1
            self.store.record_relations(rows)
        run["relations"] = {"checked": checked, "merged": merged}

    async def describe_rankings(self, run, limit=60):
        """One Chinese line for each ranked project that has none yet (github.py). A model failure
        stops this step only; the lists keep their English descriptions."""
        if not limit or not self.analyzer.configured:
            return
        ids = [s["id"] for s in self.sources if s["kind"] in RANKINGS]
        states = self.store.source_states()
        rows = missing_lines(states[i] for i in ids if i in states)[:limit]
        lines = {}
        for start in range(0, len(rows), LINE_BATCH):
            batch = rows[start:start + LINE_BATCH]
            try:
                answers = await self.analyzer.request_json(
                    LINE_PROMPT, line_payload(batch), line_validator([r["name"] for r in batch]),
                    purpose="repo_line", maximum=1800)
            except ValueError as error:
                run["errors"].append("repo_line_" + str(error).removeprefix("intent_"))
                break
            lines.update({(r["name"], r["description"]): answers[r["name"]] for r in batch if r["name"] in answers})
        if not lines:
            return
        states = self.store.source_states()  # re-read: only the rows change
        for source_id in ids:
            state = states.get(source_id)
            if state and state.get("ranking"):
                self.store.source_state(source_id, {**state, "ranking": with_lines(state["ranking"], lines)})
        run["repo_lines"] = len(lines)

    def merge_by_model(self, target, source, answer):
        """Fold the newer event into the older one, unless a reader split either of them."""
        self.assign_events()
        target, source = self.resolve(target), self.resolve(source)
        _, live, _ = self.store.event_state()
        if target == source or target not in live or source not in live:
            return "already_together"
        membership = self.membership()
        involved = {m for m, e in membership.items() if e in {target, source}}
        if involved & self.store.split_materials():
            return "kept_reader_split"
        moving = [m for m, e in membership.items() if e == source]
        self.store.regroup({"kind": "model_merge", "event": source, "into": target, "materials": moving,
                            "relation": answer.relation, "reason": answer.reason},
                           moving, target, alias=source, method="model")
        return "merged"

    def snapshot_view(self, run=None, user=LOCAL_USER):
        """What a past briefing needs to be re-read: its ranked events, not the whole library."""
        value = self.view(user)
        shown = set(value["focus"]) | set(value["radar"])
        titles = {e["id"]: e["title"] for e in value["events"]}
        return {**value, "events": [e for e in value["events"] if e["id"] in shown],
                "archive": [], "saved_events": [], "follows": [], "run": None, "queue": [],
                "snapshot_kind": (run or {}).get("kind"), "snapshot_trigger": (run or {}).get("trigger"),
                "headlines": [titles[i] for i in value["focus"][:3] if i in titles]}

    def github_token(self):
        token = getattr(self.settings, "reader_github_token", None)
        return token.get_secret_value() if token else ""

    def rankings(self):
        """Open source rankings from the latest update: each list with its time and status."""
        states = self.store.source_states()
        result = []
        for source in self.sources:
            if source["kind"] not in RANKINGS:
                continue
            state = states.get(source["id"], {"status": "not_checked"})
            result.append({"id": source["id"], "name": source["name"], "kind": source["kind"],
                           "url": source.get("original_url", source["url"]),
                           "description": source.get("description", ""),
                           "status": state.get("status"), "error": state.get("error"),
                           "at": state.get("ranking_at"), "rows": state.get("ranking", [])})
        return result

    def source_list(self):
        states = self.store.source_states()
        # Ranking rows are shown on the trends page, not repeated in every source status.
        states = {k: {f: v for f, v in s.items() if f != "ranking"} for k, s in states.items()}
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

    def start_discovery(self, request, user=LOCAL_USER):
        run = self.new_run("discovery", "discovering", query=request.query, channels=request.channels,
                           user_id=user)
        return self.submit(run, lambda run: self.discover(request.query, run))

    async def discover(self, query, run):
        user = run.get("user_id", LOCAL_USER)
        try:
            related = []
            intent_follow = None
            if run.get("follow_id"):
                follow = next(f for f in self.store.follows(user) if f["id"] == run["follow_id"])
                plan = follow.get("intent_plan")
                intent_follow = follow if plan else None
                if plan and not follow.get("confirmed_at"):
                    raise ValueError("追踪方案尚未确认")
                if (not plan or plan["include_feeds"]) and (self.last_topic_collection is None or time.monotonic() - self.last_topic_collection >= 1800):
                    # Topic follows need articles; the rankings wait for the next update.
                    await collect(self.store, [s for s in self.sources if s["kind"] not in RANKINGS], limit=3)
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
                self.store.update_follow(intent_follow["id"], user=user, search_cursor=cursor + len(selected),
                                         last_searches=selected)
            else:
                found = await discover(self.store, query, limit=4, channels=run.get("channels"), settings=self.settings)
            found = list({m.version: m for m in related + found}.values())
            run.update(found=len(found), result_versions=[m.version for m in found])
            if run.get("follow_id"):
                follow = next(f for f in self.store.follows(user) if f["id"] == run["follow_id"])
                ids = list(dict.fromkeys([m.id for m in found] + follow.get("material_ids", [])))[:200]
                self.store.update_follow(follow["id"], user=user, material_ids=ids)
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
                self.store.update_follow(intent_follow["id"], user=user, material_ids=ids)
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
            snapshot = await asyncio.to_thread(self.snapshot_view, run, user)
            run.update(state="completed", finished_at=now())
            run["snapshot_id"] = self.store.snapshot(snapshot, user)
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
                self.store.update_follow(run["follow_id"], user=user, last_checked=now(), last_status=status,
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

    def triaged(self, materials=None):
        """Materials in the order the model should read them (triage.py): news reported by
        several outlets first, catalogs and paper listings after articles, old finds last."""
        materials = self.store.materials() if materials is None else materials
        current = {v for v, j in self.store.judgments().items() if j.get("epoch", 0) >= POLICY_EPOCH}
        return triage(materials, datetime.now(timezone.utc), self.store.refresh_times(), done=current)

    async def analyze(self, materials, run, limit, again=False):
        """Judge up to limit pending materials; again: judge exactly these, even if judged before
        (a new prompt's judgment is stored beside the old one and wins as the newest)."""
        pending = [m for m in materials if has_material(m)][:limit] if again \
            else self.pending_judgments(materials, limit)
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
                try:
                    self.store.update_follow(run["follow_id"], user=run.get("user_id", LOCAL_USER),
                                             last_status="cancelled")
                except ValueError:
                    pass  # the topic was removed meanwhile

    def start_follow(self, key, manual=True, user=LOCAL_USER):
        follow = next((f for f in self.store.follows(user) if f["id"] == key), None)
        if not follow or not follow["active"]:
            raise ValueError("请先启用这个话题的追踪")
        if not follow.get("intent_plan") or not follow.get("confirmed_at"):
            raise ValueError("请先描述需求并确认追踪方案")
        existing = self.pending(lambda run: run.get("follow_id") == key and run.get("user_id") == user)
        if existing:
            if manual and existing["state"] == "queued" and not existing["manual"]:
                # Asked for now: move the scheduled check up with the other manual work.
                entry = next(e for e in self.queue if e[0] is existing)
                self.queue.remove(entry)
                self.submit(*entry)
            return existing

        async def job(run):
            self.store.update_follow(key, user=user, last_checked=now(), last_status="checking")
            await self.discover(follow["query"], run)
        run = self.submit(self.new_run("following", "discovering", follow_id=key, query=follow["query"],
                                       follow_name=follow["name"], user_id=user), job, manual=manual)
        if run["state"] == "queued":
            self.store.update_follow(key, user=user, last_status="queued")
        return run

    def start_tracking(self):
        for follow in self.store.all_follows():
            owner = follow["user_id"]
            if follow["active"] and not follow.get("intent_plan"):
                self.store.update_follow(follow["id"], user=owner, active=False, last_status="needs_intent")
            elif follow.get("last_status") in {"queued", "checking"}:
                # The queue lives in memory: a check queued or running before a restart is gone.
                self.store.update_follow(follow["id"], user=owner, last_status="cancelled")
        if not self.tracker or self.tracker.done():
            self.tracker = asyncio.create_task(self.tracking_loop())

    def track_due(self):
        clock = stamp(now())
        due = [f for f in self.store.all_follows() if f["active"] and f.get("intent_plan") and f.get("confirmed_at") and
               (not f.get("last_checked") or (clock - stamp(f["last_checked"])).total_seconds() >=
                f.get("intent_plan", {}).get("interval_minutes", 30) * 60)]
        for follow in sorted(due, key=lambda f: f.get("last_checked") or ""):
            if len(self.queue) >= QUEUE_LIMIT:
                break
            self.start_follow(follow["id"], manual=False, user=follow["user_id"])

    async def tracking_loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                self.refresh_due()
            except Exception as error:
                logging.getLogger(__name__).warning("Scheduled update check failed: %s", type(error).__name__)
            try:
                self.track_due()
            except Exception as error:
                logging.getLogger(__name__).warning("Topic tracking check failed: %s", type(error).__name__)

    def start(self, request, manual=True, user=None):
        existing = self.pending(lambda run: run["kind"] == "refresh")
        if existing:
            return existing
        run = self.new_run("refresh", "collecting", trigger="manual" if manual else "scheduled",
                           **({"user_id": user} if user else {}))
        return self.submit(run, lambda run: self.refresh(request, run), manual=manual)

    async def refresh(self, request, run):
        def progress(name, state):
            run["sources_done"] += 1
            run["current_source"] = name
        self.store.record_refresh(run)
        try:
            await collect(self.store, self.sources, request.limit_per_source, progress,
                          github_token=self.github_token())
            run["stage"] = "reading"
            await enrich(self.store, limit=min(24, request.analyze_limit))
            run["stage"] = "understanding"
            candidates = await asyncio.to_thread(self.triaged)
            await self.analyze(candidates, run, request.analyze_limit)
            run["stage"] = "grouping"
            await self.relate_events(run)
            await self.describe_rankings(run)
            run["stage"] = "publishing"
            # Shared content, personal briefings: save one for each recently active reader.
            since = (datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_ACTIVE_DAYS)).isoformat()
            starter = run.get("user_id") or LOCAL_USER
            readers = list(dict.fromkeys([starter, *self.store.active_users(since)]))[:SNAPSHOT_READERS]
            snapshots = {}
            for reader in readers:
                snapshots[reader] = await asyncio.to_thread(self.snapshot_view, run, reader)
            run["state"] = "completed"
            run["finished_at"] = now()
            for reader, snapshot in snapshots.items():
                key = self.store.snapshot(snapshot, reader)
                if reader == starter:
                    run["snapshot_id"] = key
            if self.settings.publish_path():
                # A failed public write never fails the reader's own update.
                try:
                    result = await asyncio.to_thread(self.publish_digest)
                    run["published_edition"] = result["edition"]
                except Exception as error:  # noqa: BLE001 - reported on the run, update stays completed
                    logging.getLogger(__name__).warning("public digest failed: %r", error)
                    run["errors"].append("publish_failed")
        except asyncio.CancelledError:
            run.update(state="cancelled", finished_at=now())
        except Exception as error:
            run.update(state="failed", finished_at=now())
            run["errors"].append(type(error).__name__)
        finally:
            self.store.record_refresh(run)

    @staticmethod
    def may_cancel(run, owner):
        """owner None: any run (admin, internal). Otherwise only runs that reader started."""
        return owner is None or run.get("user_id") == owner

    async def cancel(self, run_id=None, owner=None):
        """Stop the running job (default) or drop a queued one; the queue then moves on."""
        if run_id and run_id != (self.run or {}).get("id"):
            for index, (run, _) in enumerate(self.queue):
                if run["id"] == run_id:
                    if not self.may_cancel(run, owner):
                        raise PermissionError("只能取消自己发起的任务")
                    self.queue.pop(index)
                    self.mark_cancelled(run)
                    return run
            raise LookupError("这个任务已经结束或不存在")
        if self.busy():
            task, run = self.task, self.run
            if not self.may_cancel(run, owner):
                raise PermissionError("只能取消自己发起的任务")
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

    async def cancel_follow(self, key, user=LOCAL_USER):
        """Drop queued checks of a topic and stop its running one; True when anything stopped."""
        def mine(run):
            return run.get("follow_id") == key and run.get("user_id", LOCAL_USER) == user
        stopped = False
        for run, _ in list(self.queue):
            if mine(run):
                await self.cancel(run["id"])
                stopped = True
        if self.busy() and mine(self.run):
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
