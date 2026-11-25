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
  setDisplayZone,
  siteZoneLabel,
  sinceVisit,
  companyCards,
  companyLine,
  companyMentions,
  evidenceChecklist,
  evidenceStages,
  evidenceLanes,
  deckStories,
  drawerCompanies,
  editionLayout,
  editionStamp,
  recentMarks,
  lensStories,
  lineCounts,
  lineDays,
  pageFromHash as pageOf,
  shortProductName,
  trendFromHash,
  trendHash,
  repoMeta,
  statusLabel,
  storyFromHash,
  todayLabel,
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

test("briefing sections keep the engine's importance order; other lists are newest first", () => {
  const earlier = story("a", { published_at: "2026-11-02T10:00:00+08:00", captured_at: "2026-11-10T00:00:00Z" });
  const later = story("c", { published_at: "unconfirmed", captured_at: "2026-11-02T03:00:00Z" });
  const latest = story("b", { topic: "agents", published_at: "2026-11-02T04:00:00Z" });
  const undated = story("d", { captured_at: "unconfirmed" });
  const events = [earlier, undated, latest, later];
  const value = view(events, { focus: ["a", "c"], radar: ["d", "b"], saved_events: [earlier, later] });
  const all = sections(value, "", "", "");
  // Focus and radar keep the order the engine chose them in, whatever their dates.
  assert.deepEqual(all.focus.map((e) => e.id), ["a", "c"]);
  assert.deepEqual(all.radar.map((e) => e.id), ["d", "b"]);
  // Undated stories follow dated ones: collection time does not make them news (Kimi K3, 2026-11-23).
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

test("dates follow the reader's timezone: New York by default, Beijing when chosen", () => {
  const event = "2026-11-11T15:00:00Z"; // New York 10:00 on the 11th, Beijing 23:00 on the 11th
  const now = new Date("2026-11-11T17:00:00Z"); // New York noon; Beijing already 1:00 on the 12th
  setDisplayZone("America/New_York");
  assert.equal(clockLabel(event, now), "今天 10:00");
  assert.equal(todayLabel(now), "11月11日星期三");
  setDisplayZone("Asia/Shanghai");
  assert.equal(clockLabel(event, now), "昨天 23:00");
  assert.equal(todayLabel(now), "11月12日星期四");
  assert.match(when(event), /23:00/);
  setDisplayZone(null);
  const zone = { zone: "Asia/Shanghai", site: "America/New_York",
    options: [{ id: "America/New_York", label: "纽约时间" }, { id: "Asia/Shanghai", label: "北京时间" }] };
  assert.equal(siteZoneLabel(view([], { timezone: zone })), "纽约时间");
  assert.equal(siteZoneLabel(null), "");
});

test("since the last visit lists new and changed stories the reader has not read", () => {
  const entry = (captured_at: string, action = "release") => ({
    version: captured_at, title: "t", summary: "", source: "S", role: "media", url: "", published_at: null,
    captured_at, action, evidence: "source_attributed", claims: [], conditions: [], limitations: [],
  });
  const since = "2026-11-02T00:00:00Z";
  const list = [
    story("fresh", { first_captured_at: "2026-11-02T03:00:00Z" }),
    story("read", { first_captured_at: "2026-11-02T03:00:00Z", known: true }),
    story("tested", { first_captured_at: "2026-11-01T00:00:00Z",
      timeline: [entry("2026-11-01T00:00:00Z"), entry("2026-11-02T05:00:00Z", "test")] }),
    story("fixed", { first_captured_at: "2026-11-01T00:00:00Z",
      timeline: [entry("2026-11-01T00:00:00Z"), entry("2026-11-02T05:00:00Z", "correction")] }),
    story("echo", { first_captured_at: "2026-11-01T00:00:00Z",
      timeline: [entry("2026-11-01T00:00:00Z"), entry("2026-11-02T05:00:00Z"), entry("2026-11-02T06:00:00Z")] }),
    story("quiet", { first_captured_at: "2026-11-01T00:00:00Z", timeline: [entry("2026-11-01T00:00:00Z")] }),
  ];
  const changes = sinceVisit(list, since)!;
  assert.deepEqual(
    changes.map((c) => [c.story.id, c.kind, c.label]),
    [
      ["fresh", "new", "新"],
      ["tested", "updated", "新测试"],
      ["fixed", "correction", "更正"],
      ["echo", "updated", "新报道 2 篇"],
    ],
  );
  assert.equal(sinceVisit(list, null), null);
  assert.deepEqual(sinceVisit([list[5]], since), []);
});

const entry = (role: string, changes: Record<string, unknown> = {}) => ({
  version: role + Math.random(), title: "t", summary: "", source: role, role, url: "",
  published_at: "2026-11-20T00:00:00Z", captured_at: "2026-11-20T01:00:00Z", action: "release",
  evidence: "source_attributed", claims: [], conditions: [], limitations: [], content_kind: "feed_excerpt",
  ...changes,
});

test("trends keep their lens, company and product in the hash", () => {
  assert.equal(pageOf("#trends/company/openai/chatgpt"), "trends");
  assert.deepEqual(trendFromHash("#trends/company/openai/chatgpt"), { lens: "company", company: "openai", product: "chatgpt" });
  assert.deepEqual(trendFromHash("#trends"), { lens: "company", company: "", product: "" });
  assert.deepEqual(trendFromHash("#trends/bogus"), { lens: "company", company: "", product: "" });
  assert.equal(trendHash({ lens: "research", company: "", product: "" }), "trends/research");
});

test("a company line holds what it did; mentions and dismissed stories stay off it", () => {
  const own = (id: string, products: string[], changes: Partial<Story> = {}) =>
    story(id, { companies: [{ id: "openai", official: true, products }], lenses: ["company"], ...changes });
  const events = [
    own("launch", ["chatgpt", "api"], { published_at: "2026-11-24T00:00:00Z" }),
    own("api", ["api"], { published_at: "2026-11-23T00:00:00Z" }),
    own("gone", ["api"], { dismissed: true }),
    story("customer", { mentions: ["openai"], lenses: [] }),
    story("paper", { lenses: ["research"] }),
  ];
  assert.deepEqual(companyLine(events, "openai").map((s) => s.id), ["launch", "api"]);
  assert.deepEqual(companyLine(events, "openai", "chatgpt").map((s) => s.id), ["launch"]);
  assert.deepEqual(companyMentions(events, "openai").map((s) => s.id), ["customer"]);
  assert.deepEqual(lensStories(events, "research").map((s) => s.id), ["paper"]);
  const counts = lineCounts(events, "openai");
  assert.equal(counts.companies.openai, 2);
  assert.deepEqual(counts.products, { chatgpt: 1, api: 2 });
});

test("a company line is grouped newest day first; undated stories close it under one heading", () => {
  setDisplayZone("UTC");
  const own = (id: string, changes: Partial<Story>) =>
    story(id, { companies: [{ id: "openai", official: true, products: [] }], ...changes });
  const line = companyLine(
    [
      own("old", { published_at: "2026-11-23T08:00:00Z" }),
      // Collected on the 24th, published on an unknown day: it must not reopen "11月24日".
      own("undated", { published_at: null, captured_at: "2026-11-24T16:00:00Z" }),
      own("new", { published_at: "2026-11-24T14:00:00Z" }),
      own("same-day", { published_at: "2026-11-23T21:00:00Z" }),
    ],
    "openai",
  );
  assert.deepEqual(
    lineDays(line).map((d) => [d.day, d.stories.map((s) => s.id)]),
    [["11月24日", ["new"]], ["11月23日", ["same-day", "old"]], ["发布日期未知", ["undated"]]],
  );
});

test("company overview cards rank active companies, summarise explicit products and separate quiet ones", () => {
  assert.equal(shortProductName("ChatGPT（含 Codex）"), "ChatGPT");
  assert.equal(shortProductName("Sora"), "Sora");
  const catalog = [
    {
      id: "anthropic",
      name: "Anthropic",
      products: [
        { id: "claude", name: "Claude（应用与模型）" },
        { id: "claude-code", name: "Claude Code" },
        { id: "research", name: "研究与安全" },
        { id: "corporate", name: "公司与政策" },
      ],
    },
    {
      id: "openai",
      name: "OpenAI",
      products: [
        { id: "chatgpt", name: "ChatGPT（含 Codex）" },
        { id: "api", name: "API 与模型" },
        { id: "research", name: "研究与安全" },
        { id: "corporate", name: "公司与政策" },
      ],
    },
    {
      id: "apple",
      name: "Apple",
      products: [
        { id: "apple-intelligence", name: "Apple Intelligence 与 Siri" },
        { id: "research", name: "研究与安全" },
      ],
    },
  ];
  const since = "2026-11-22T00:00:00Z";
  const events = [
    story("o1", {
      published_at: "2026-11-24T00:00:00Z",
      first_captured_at: "2026-11-24T01:00:00Z",
      action: "release",
      companies: [{ id: "openai", official: true, products: ["chatgpt", "api"] }],
      lenses: ["company"],
    }),
    story("o2", {
      published_at: "2026-11-23T00:00:00Z",
      first_captured_at: "2026-11-21T01:00:00Z",
      action: "explain",
      companies: [{ id: "openai", official: false, products: ["api"] }],
      lenses: ["company"],
    }),
    story("a1", {
      published_at: "2026-11-24T02:00:00Z",
      first_captured_at: "2026-11-24T02:30:00Z",
      action: "release",
      companies: [{ id: "anthropic", official: true, products: ["claude-code"] }],
      lenses: ["company"],
    }),
    story("m1", { mentions: ["apple"], lenses: [] }),
  ];
  const { active, quiet } = companyCards(catalog, events, since);
  assert.deepEqual(active.map((c) => c.id), ["openai", "anthropic"]);
  assert.equal(active[0].total, 2);
  assert.equal(active[0].officialCount, 1);
  assert.equal(active[0].majorCount, 1);
  assert.equal(active[0].freshCount, 1);
  assert.equal(active[0].productSummary, "ChatGPT · API 与模型");
  assert.deepEqual(active[0].products.map((p) => [p.shortName, p.count]), [
    ["API 与模型", 2],
    ["ChatGPT", 1],
  ]);
  assert.deepEqual(active[0].latest.map((s) => s.id), ["o1", "o2"]);
  assert.deepEqual(quiet.map((c) => [c.id, c.mentionCount]), [["apple", 1]]);
});

test("the evidence timeline orders stages, counts days and names missing ones", () => {
  const launch = story("x", {
    action: "release",
    timeline: [
      entry("media", { published_at: "2026-11-21T00:00:00Z" }),
      entry("official"),
      entry("official", { published_at: "2026-11-22T00:00:00Z", evidence: "reported_test", action: "test" }),
    ],
  });
  const { nodes, gaps } = evidenceStages(launch);
  assert.deepEqual(nodes.map((n) => [n.stage, n.label, n.day]), [
    ["statement", "官方原文", 0],
    ["coverage", "报道转述", 1],
    ["test", "厂商自测", 2],
  ]);
  assert.deepEqual(gaps, ["尚未见他方测试"]);
  assert.deepEqual(
    evidenceChecklist(launch).map((i) => i.ok),
    [true, true, false, false],
  );
  const relayed = story("y", {
    action: "release",
    timeline: [
      entry("media", { evidence: "reported_test" }),
      entry("media", { published_at: "2026-11-23T00:00:00Z", action: "correction" }),
    ],
  });
  const second = evidenceStages(relayed);
  assert.deepEqual(second.nodes.map((n) => [n.stage, n.label]), [
    ["test", "媒体或作者报告的测试"],
    ["change", "更正"],
  ]);
  assert.deepEqual(second.gaps, ["未见官方或论文原文"]);
});

test("repository rows say stars, the period's gain or the creation day", () => {
  const repo = { name: "acme/kit", url: "", description: "", language: "Python", stars: 12345, forks: 10,
    gained: 1034, topics: [], flags: [] };
  assert.equal(repoMeta(repo, "github-trending-daily"), "Python · ★ 12,345 · +1,034 今日");
  assert.equal(repoMeta(repo, "github-trending-weekly"), "Python · ★ 12,345 · +1,034 本周");
  const created = repoMeta({ ...repo, language: "", gained: null, created_at: "2026-11-01T12:00:00Z" }, "github-new");
  assert.match(created, /^★ 12,345 · 创建于 11月\d+日$/);
});

test("the evidence chart puts sources on lanes and reports on days up to now", () => {
  setDisplayZone("UTC");
  const event = story("lanes", {
    timeline: [
      entry("media", { source: "Wire", published_at: "2026-11-20T06:00:00Z" }),
      entry("official", { source: "Lab", published_at: "2026-11-21T12:00:00Z" }),
      entry("media", { source: "Wire", published_at: "2026-11-22T00:00:00Z", evidence: "opinion" }),
      entry("media", { source: "Blog", published_at: null, captured_at: "" }),
    ],
  });
  const chart = evidenceLanes(event, new Date("2026-11-24T00:00:00Z"));
  assert.deepEqual(chart.lanes, ["Wire", "Lab"]);
  assert.equal(chart.undated, 1);
  assert.deepEqual(chart.points.map((p) => [p.lane, p.mark]), [[0, "coverage"], [1, "statement"], [0, "opinion"]]);
  // Four days from Nov 20 00:00 to Nov 24 00:00: the official report sits at 1.5 / 4.
  assert.equal(chart.official, 1.5 / 4);
  assert.equal(chart.now, 1);
  assert.deepEqual(chart.days.map((d) => d.label), ["11月20日", "11月21日", "11月22日", "11月23日"]);
  // One report this morning: the chart ends at now (no empty future days) and starts two days back.
  const fresh = evidenceLanes(
    story("fresh", { timeline: [entry("media", { source: "Wire", published_at: "2026-11-25T09:00:00Z" })] }),
    new Date("2026-11-25T13:00:00Z"),
  );
  assert.equal(fresh.now, 1);
  assert.deepEqual(fresh.days.map((d) => d.label), ["11月23日", "11月24日", "11月25日"]);
  assert.equal(fresh.points[0].x, (2 * 24 + 9) / (2 * 24 + 13));
  const crowded = story("many", {
    timeline: Array.from({ length: 10 }, (_, i) =>
      entry("media", { source: "S" + i, published_at: `2026-11-2${i % 4}T00:00:00Z` })),
  });
  const many = evidenceLanes(crowded, new Date("2026-11-24T00:00:00Z"));
  assert.equal(many.lanes.length, 8);
  assert.equal(many.lanes[7], "其他来源");
  assert.ok(many.points.every((p) => p.lane < 8));
  assert.deepEqual(evidenceLanes(story("none")).lanes, []);
  setDisplayZone(undefined);
});

test("quick reading deals unread briefing stories once, in briefing order", () => {
  const a = story("a"), b = story("b", { known: true }), c = story("c", { dismissed: true }), d = story("d");
  assert.deepEqual(deckStories([a, b, c, d, a]).map((s) => s.id), ["a", "d"]);
});

test("the sidebar shows the reader's companies in their order, or the four most active", () => {
  const card = (id: string, total: number) =>
    ({ id, name: id, total, productSummary: "", products: [], officialCount: 0, majorCount: 0,
       freshCount: 0, mentionCount: 0, latest: [] });
  const cards = {
    active: [card("openai", 9), card("google", 7), card("anthropic", 5), card("nvidia", 3), card("meta", 1)],
    quiet: [card("apple", 0)],
  };
  assert.deepEqual(drawerCompanies(cards).map((c) => c.id), ["openai", "google", "anthropic", "nvidia"]);
  assert.deepEqual(drawerCompanies(cards, ["apple", "gone", "nvidia"]).map((c) => c.id), ["apple", "nvidia"]);
  assert.deepEqual(drawerCompanies(cards, []), []);
});

test("更多进展 ranks by importance: corrections first, then score, newest among equals", () => {
  const events = [
    story("old-high", { score: 20, published_at: "2026-11-01T00:00:00Z" }),
    story("new-low", { score: 8, published_at: "2026-11-03T00:00:00Z" }),
    story("new-high", { score: 20, published_at: "2026-11-02T00:00:00Z" }),
    story("fix", { score: 5, protected: true, published_at: "2026-10-30T00:00:00Z" }),
  ];
  const more = sections(view(events), "", "", "").more.map((e) => e.id);
  assert.deepEqual(more, ["fix", "new-high", "old-high", "new-low"]);
});

test("the theme follows the reader's choice, or the system when they chose 跟随系统", async () => {
  const { resolveTheme } = await import("../src/theme.ts");
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("dark", false), "dark");
  assert.equal(resolveTheme("auto", true), "dark");
  assert.equal(resolveTheme("auto", false), "light");
});

test("AIHOT's summary of a post we could not read is labelled as such, never as the publisher's words", () => {
  assert.equal(evidence("source_attributed", "author", "curated_summary"), "AIHOT 摘要 · 未读到原文");
  assert.equal(evidence("source_attributed", "official", "publisher_excerpt"), "原文陈述");
});

test("the briefing is laid out as one edition in the engine's order, nothing added or dropped", () => {
  const at = (h: number) => `2026-11-25T${String(h).padStart(2, "0")}:00:00Z`;
  const s = (id: string, topic: string, changes: Partial<Story> = {}) =>
    story(id, { topic, topic_label: topic, first_captured_at: at(10), captured_at: at(10), ...changes });
  const focus = ["f1", "f2", "f3", "f4", "f5", "f6"].map((id, i) => s(id, i % 2 ? "agents" : "models"));
  const radar = ["r1", "r2", "r3", "r4", "r5", "r6", "r7"].map((id) => s(id, "research"));
  // Seen before the last visit, a new report since: older news, outside the edition.
  const older = s("old", "industry", {
    first_captured_at: "2026-11-20T00:00:00Z",
    timeline: [{ version: "v", title: "t", summary: "", source: "X", role: "media", url: "https://e.org", published_at: null,
      captured_at: at(9), action: "test", evidence: "reported_test", claims: [], conditions: [], limitations: [] }],
  });
  const quiet = s("quiet", "industry", { first_captured_at: "2026-11-20T00:00:00Z" });
  const v = view([...focus, ...radar, older, quiet], {
    focus: focus.map((e) => e.id), radar: radar.map((e) => e.id), previous_visit: "2026-11-25T00:00:00Z",
  });
  const ed = editionLayout(v, 5);
  assert.equal(ed.lead?.id, "f1");
  assert.deepEqual(ed.highlights.map((e) => e.id), ["f2", "f3", "f4"]);
  assert.deepEqual(ed.sections.map((x) => [x.topic, x.stories.map((e) => e.id)]),
    [["models", ["f5"]], ["agents", ["f6"]], ["research", ["r1", "r2", "r3", "r4", "r5"]]]);
  assert.deepEqual(ed.brief.map((e) => e.id), ["r6", "r7"]);
  assert.equal(ed.stories.length, 13);
  assert.equal(ed.changes.get("f1")?.label, "新");
  assert.deepEqual(ed.followups.map((c) => [c.story.id, c.label]), [["old", "新测试"]]);
  // Without focus, the first radar story leads.
  assert.equal(editionLayout(view(radar, { radar: radar.map((e) => e.id) })).lead?.id, "r1");
});

test("an edition is stamped with its local date, weekday and half of the day", () => {
  setDisplayZone("America/New_York");
  assert.deepEqual(editionStamp("2026-11-25T05:46:00Z"), { date: "11月25日", weekday: "星期三", edition: "上午版", time: "0:46" });
  assert.equal(editionStamp("2026-11-25T17:05:00Z")?.edition, "下午版");
  assert.equal(editionStamp(""), null);
});

test("the report strip places a story's last week of reports up to now", () => {
  const entry = (role: string, published_at: string, evidence = "source_attributed") => ({ version: role + published_at,
    title: "t", summary: "", source: role, role, url: "https://e.org", published_at, action: "release", evidence,
    claims: [], conditions: [], limitations: [] });
  const marks = recentMarks(story("s", { timeline: [entry("official", "2026-11-24T00:00:00Z"),
    entry("media", "2026-11-10T00:00:00Z"), entry("media", "2026-11-24T12:00:00Z", "opinion")] }),
    new Date("2026-11-25T00:00:00Z"), 4);
  // The month-old report is outside the window.
  assert.deepEqual(marks.map((m) => [m.mark, m.x]), [["statement", 0.75], ["opinion", 0.875]]);
});
