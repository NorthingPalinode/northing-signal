// Reader page logic. Node 24's built-in TS transform; no added dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  evidence,
  clockLabel,
  feedbackNotice,
  followSeed,
  mergeCandidates,
  neighbours,
  pageFromHash,
  queueLabel,
  sections,
  statusLabel,
  storyFromHash,
  topThree,
  updateLine,
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
  preferences: { topics: ["models"], depth: "balanced", budget_minutes: 7, exploration: false, auto_refresh: true },
  sources: [], model_configured: true, run: null, ...changes,
});

test("unknown or empty hashes open the briefing page", () => {
  assert.equal(pageFromHash("#following"), "following");
  assert.equal(pageFromHash("library"), "library");
  assert.equal(pageFromHash("#saved"), "saved");
  assert.equal(pageFromHash(""), "briefing");
  assert.equal(pageFromHash("#settings"), "briefing");
});

test("story hashes open a reading page with its neighbours", () => {
  assert.equal(pageFromHash("#story/evt-1"), "story");
  assert.equal(storyFromHash("#story/evt%2F1"), "evt/1");
  assert.equal(storyFromHash("#story/"), "");
  assert.equal(pageFromHash("#story/"), "briefing");
  assert.deepEqual(neighbours(["a", "b", "c"], "b"), { index: 1, prev: "a", next: "c" });
  assert.deepEqual(neighbours(["a", "b"], "a"), { index: 0, prev: "", next: "b" });
  assert.deepEqual(neighbours(["a"], "x"), { index: -1, prev: "", next: "" });
});

test("news is newest first within each section and respects filters", () => {
  const earlier = story("a", { published_at: "2026-11-02T10:00:00+08:00", captured_at: "2026-11-10T00:00:00Z" });
  const later = story("c", { published_at: "unconfirmed", captured_at: "2026-11-02T03:00:00Z" });
  const latest = story("b", { topic: "agents", published_at: "2026-11-02T04:00:00Z" });
  const undated = story("d", { captured_at: "unconfirmed" });
  const events = [earlier, undated, latest, later];
  const value = view(events, { focus: ["a", "c"], radar: ["d", "b"], saved_events: [earlier, later] });
  const all = sections(value, "", "", "");
  // Undated stories follow dated ones: collection time does not make them news (Kimi K3, 2026-11-23).
  assert.deepEqual(all.focus.map((e) => e.id), ["a", "c"]);
  assert.deepEqual(all.radar.map((e) => e.id), ["b", "d"]);
  assert.deepEqual(all.discover.map((e) => e.id), ["b", "a", "c", "d"]);
  assert.deepEqual(all.saved.map((e) => e.id), ["a", "c"]);
  assert.deepEqual(value.events.map((e) => e.id), ["a", "d", "b", "c"]);
  assert.deepEqual(sections(value, "agents", "", "").focus, []);
  assert.deepEqual(sections(value, "", "ATLAS C", "").focus.map((e) => e.id), ["c"]);
});

test("more lists qualified stories outside focus and radar", () => {
  const events = [story("a"), story("b"), story("c"), story("d", { qualified: false }), story("e", { dismissed: true }),
    story("f", { timely: false, stale_reason: "late" })];
  const value = view(events, { focus: ["a"], radar: ["b"] });
  assert.deepEqual(sections(value, "", "", "").more.map((e) => e.id), ["c"]);
  // A late find stays searchable (Kimi K3, 2026-11-24).
  assert.ok(sections(value, "", "", "").discover.some((e) => e.id === "f"));
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
  assert.match(feedbackNotice("known", true), /未了解/);
  assert.match(feedbackNotice("useful", false, "Agent 与开发"), /「Agent 与开发」/);
  assert.match(feedbackNotice("useful", true), /撤回/);
});

test("top three follows the engine's focus order and skips dismissed stories", () => {
  const events = ["a", "b", "c", "d", "e"].map((id) => story(id, { dismissed: id === "b" }));
  const value = view(events, { focus: ["d", "b", "a", "c", "e"] });
  assert.deepEqual(topThree(value).map((e) => e.id), ["d", "a", "c"]);
  assert.deepEqual(topThree(null), []);
});

test("update line names the latest and the next update relative to today", () => {
  const now = new Date(2026, 10, 11, 15, 0);
  const at = (h: number, d = 11) => new Date(2026, 10, d, h, 0).toISOString();
  assert.equal(clockLabel(at(12), now), "今天 12:00");
  assert.equal(clockLabel(at(0, 12), now), "明天 0:00");
  assert.equal(clockLabel(at(9, 9), now), "11月9日 9:00");
  const value = view([], {
    last_refresh: { id: "r", trigger: "scheduled", state: "completed", started_at: at(12), finished_at: at(12) },
    schedule: { enabled: true, hours: [0, 12], next: at(0, 12) },
  });
  assert.equal(updateLine(value, now), "更新于 今天 12:00（自动） · 下次自动 明天 0:00");
  assert.equal(updateLine(view([]), now), "尚未完成更新");
});

test("invalid dates are labelled instead of rendered", () => {
  assert.equal(when(null), "时间未确认");
  assert.equal(when("not a date"), "时间未确认");
  assert.notEqual(when("2026-11-01T08:00:00Z"), "时间未确认");
  const captured = "2026-11-01T08:00:00Z";
  assert.equal(when(null, captured), `发布时间未知，收录于 ${when(captured)}`);
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
