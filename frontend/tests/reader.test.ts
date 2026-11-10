// Reader page logic. Node 24's built-in TS transform; no added dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  evidence,
  feedbackNotice,
  followSeed,
  mergeCandidates,
  pageFromHash,
  queueLabel,
  sections,
  statusLabel,
  when,
} from "../src/reader/logic.ts";
import type { Run, Story, View } from "../src/reader/types.ts";

const story = (id: string, changes: Partial<Story> = {}): Story => ({
  id, version: id + "-v1", title: "Atlas " + id, summary: "summary", reason: "", topic: "models",
  topic_label: "模型与多模态", action: "release", evidence: "source_attributed", conditions: [],
  limitations: [], source: "Fixture", source_role: "official", url: "https://example.org/" + id,
  published_at: null, captured_at: "2026-11-01T00:00:00Z", source_count: 1, report_count: 1,
  qualified: true, protected: false, known: false, dismissed: false, saved: false, relevant: true,
  claims: [], timeline: [], reading_seconds: 30, actions: [], ...changes,
});

const view = (events: Story[], changes: Partial<View> = {}): View => ({
  as_of: "2026-11-02T00:00:00Z", events, focus: [], radar: [], archive: [], budget_seconds: 420,
  estimated_seconds: 0, counts: { materials: 0, events: 0, eligible: 0, pending: 0, unrelated: 0 },
  preferences: { topics: ["models"], depth: "balanced", budget_minutes: 7, exploration: false },
  sources: [], model_configured: true, run: null, ...changes,
});

test("unknown or empty hashes open the briefing page", () => {
  assert.equal(pageFromHash("#following"), "following");
  assert.equal(pageFromHash("library"), "library");
  assert.equal(pageFromHash(""), "briefing");
  assert.equal(pageFromHash("#settings"), "briefing");
});

test("focus and radar keep the server's ranking and respect filters", () => {
  const events = [story("a"), story("b", { topic: "agents" }), story("c")];
  const value = view(events, { focus: ["c", "a"], radar: ["b"] });
  const all = sections(value, "", "", "");
  assert.deepEqual(all.focus.map((e) => e.id), ["a", "c"]);
  assert.deepEqual(all.radar.map((e) => e.id), ["b"]);
  assert.deepEqual(sections(value, "agents", "", "").focus, []);
  assert.deepEqual(sections(value, "", "ATLAS C", "").focus.map((e) => e.id), ["c"]);
});

test("discover hides unqualified and dismissed stories", () => {
  const events = [story("a"), story("b", { qualified: false }), story("c", { dismissed: true })];
  assert.deepEqual(sections(view(events), "", "", "").discover.map((e) => e.id), ["a"]);
});

test("saved stories come from saved_events, falling back to saved flags", () => {
  const kept = story("old", { saved: true });
  assert.deepEqual(sections(view([story("a")], { saved_events: [kept] }), "", "", "").saved, [kept]);
  const flagged = story("b", { saved: true });
  assert.deepEqual(sections(view([story("a"), flagged]), "", "", "").saved, [flagged]);
});

test("following shows the selected topic, defaulting to the first", () => {
  const follow = (id: string, event_ids: string[]) => ({
    id, name: id, query: id, active: true, last_checked: null, last_status: "ok",
    event_ids, unread_ids: [], material_versions: [],
  });
  const value = view([story("a"), story("b")], { follows: [follow("f1", ["a"]), follow("f2", ["b"])] });
  assert.deepEqual(sections(value, "", "", "").followingEvents.map((e) => e.id), ["a"]);
  assert.deepEqual(sections(value, "", "", "f2").followingEvents.map((e) => e.id), ["b"]);
  assert.equal(sections(view([]), "", "", "").followed, undefined);
});

test("evidence labels never present excerpts or posts as verified fact", () => {
  assert.equal(evidence("source_attributed", "official", "benchmark_snapshot"), "公开榜单数据");
  assert.equal(evidence("source_attributed", "research", "index_abstract"), "索引摘要");
  assert.equal(evidence("source_attributed", "community", "community_post"), "社区发言");
  assert.equal(evidence("reported_test", "media", "feed_excerpt"), "文中报告测试");
  assert.equal(evidence("insufficient", "official", "feed_excerpt"), "材料待补充");
  assert.equal(evidence("source_attributed", "media", "feed_excerpt"), "报道转述");
});

test("short follow descriptions are expanded, long ones kept", () => {
  assert.equal(followSeed("", ""), "");
  assert.match(followSeed("", "vLLM"), /「vLLM」/);
  const long = "我想跟踪开源推理框架的性能更新";
  assert.equal(followSeed(long, "vLLM"), long);
});

test("feedback notices distinguish saving from unsaving", () => {
  assert.match(feedbackNotice("saved", false), /已收藏/);
  assert.equal(feedbackNotice("saved", true), "已取消收藏。");
  assert.match(feedbackNotice("known", false), /实质更新/);
});

test("invalid dates are labelled instead of rendered", () => {
  assert.equal(when(null), "时间未确认");
  assert.equal(when("not a date"), "时间未确认");
  assert.notEqual(when("2026-11-01T08:00:00Z"), "时间未确认");
});

test("queued jobs and failed materials have readable labels", () => {
  const run = (changes: Partial<Run>): Run => ({
    id: "r", state: "queued", stage: "discovering", sources_done: 0, analyzed: 0, failed: 0,
    errors: [], ...changes,
  });
  assert.equal(queueLabel(run({ kind: "refresh" })), "更新情报");
  assert.equal(queueLabel(run({ kind: "discovery", query: "vLLM" })), "搜索「vLLM」");
  assert.equal(queueLabel(run({ kind: "following", follow_name: "本地智能体" })), "追踪「本地智能体」");
  assert.equal(statusLabel.failed, "整理失败");
  assert.match(statusLabel.retrying, /稍后重试/);
});

test("merge candidates are other events of the same topic, newest first", () => {
  const events = [
    story("old", { published_at: "2026-10-01T00:00:00Z" }),
    story("self"),
    story("new", { published_at: "2026-11-01T00:00:00Z" }),
    story("other-topic", { topic: "agents" }),
  ];
  const value = view(events);
  assert.deepEqual(mergeCandidates(value, events[1]).map((e) => e.id), ["new", "old"]);
  assert.deepEqual(mergeCandidates(value, events[1], 1).map((e) => e.id), ["new"]);
  assert.deepEqual(mergeCandidates(null, events[1]), []);
});
