// Pure reader helpers: no React, DOM or network, so they run under node --test.
import type { Page, RepoRow, Run, Story, Topic, View } from "./types";

export const topics: Record<Topic, string> = {
  models: "模型与多模态",
  agents: "Agent 与开发",
  research: "研究与评测",
  engineering: "部署与成本",
  products: "产品与应用",
  industry: "产业与政策",
};

export function pageFromHash(hash: string): Page {
  const value = hash.replace(/^#/, "");
  if (storyFromHash(value)) return "story";
  if (value === "trends" || value.startsWith("trends/")) return "trends";
  return ["discover", "following", "saved", "library"].includes(value)
    ? (value as Page)
    : "briefing";
}

/** `#story/<id>` opens one story as its own reading page. */
export function storyFromHash(hash: string) {
  const match = /^#?story\/(.+)$/.exec(hash);
  return match ? decodeURIComponent(match[1]) : "";
}

/** Position of a story inside the list it was opened from. */
export function neighbours(ids: string[], id: string) {
  const index = ids.indexOf(id);
  return {
    index,
    prev: index > 0 ? ids[index - 1] : "",
    next: index >= 0 && index < ids.length - 1 ? ids[index + 1] : "",
  };
}

/** Timezone dates are shown in (IANA name); unset: the browser's own. Set from the view. */
let displayZone: string | undefined;
export function setDisplayZone(zone?: string | null) {
  displayZone = zone || undefined;
}

/** Calendar date and clock time of a moment in the display timezone. */
function zoned(date: Date | number) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: displayZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return { year: get("year"), month: get("month"), day: get("day"), hour: get("hour") % 24, minute: get("minute") };
}

/** "11月24日星期二" for the masthead, in the display timezone. */
export function todayLabel(now = new Date()) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: displayZone,
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(now);
}

/** Name of the site timezone (update schedule, daily quotas), e.g. "纽约时间". */
export function siteZoneLabel(view: View | null) {
  const zone = view?.timezone;
  if (!zone) return "";
  return zone.options.find((o) => o.id === zone.site)?.label || zone.site || "服务器时区";
}

export function when(value?: string | null, capturedAt?: string) {
  const published = Date.parse(value ?? "");
  const hasPublished = Number.isFinite(published);
  const date = hasPublished ? published : Date.parse(capturedAt ?? "");
  if (!Number.isFinite(date)) return "时间未确认";
  const label = new Intl.DateTimeFormat("zh-CN", {
    timeZone: displayZone,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  // Collection time is when we saw it, not when it happened (an old model card can be new to us).
  return hasPublished ? label : `发布时间未知，收录于 ${label}`;
}

type NewsDate = { published_at: string | null; captured_at?: string };

/** undatedLast: stories without a publication date follow the dated ones instead of passing
 * as "just published" by their collection time. Raw materials keep collection order. */
function newestFirst<T extends NewsDate>(rows: T[], undatedLast = false): T[] {
  const time = (row: NewsDate) => {
    const published = Date.parse(row.published_at ?? "");
    if (Number.isFinite(published)) return [1, published];
    const captured = Date.parse(row.captured_at ?? "");
    return [undatedLast ? 0 : 1, Number.isFinite(captured) ? captured : Number.MIN_SAFE_INTEGER];
  };
  return [...rows].sort((a, b) => {
    const [ra, ta] = time(a), [rb, tb] = time(b);
    return rb - ra || tb - ta;
  });
}
export const evidence = (value: string, role?: string, kind?: string) =>
  kind === "curated_summary"
    ? "AIHOT 摘要 · 未读到原文"
    : kind === "benchmark_snapshot"
    ? "公开榜单数据"
    : kind === "index_abstract"
    ? "索引摘要"
    : kind === "community_post"
      ? "社区发言"
      : role === "community" && kind === "publisher_excerpt"
        ? "社区线索原文"
        : kind === "publisher_excerpt" && value === "source_attributed"
          ? "原文陈述"
          : value === "reported_test"
            ? "文中报告测试"
            : value === "opinion"
              ? "作者观点"
              : value === "insufficient"
                ? "材料待补充"
                : role === "official" || role === "research"
                  ? "原文陈述"
                  : "报道转述";
export const actionLabel: Record<string, string> = {
  release: "发布",
  update: "实质更新",
  test: "测试",
  correction: "更正",
  withdrawal: "撤回",
  explain: "方法与解读",
  other: "进展",
};
export const statusLabel: Record<string, string> = {
  pending: "尚待整理",
  ai: "AI 相关",
  unrelated: "未纳入推荐",
  uncertain: "相关性待确认",
  time_uncertain: "日期待核对",
  retrying: "整理失败，稍后重试",
  failed: "整理失败",
};

export const matchesStory = (story: Story, topic: string, query: string) =>
  (!topic || story.topic === topic) &&
  (!query ||
    [story.title, story.summary, story.source, story.reason, story.topic_label, story.object]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()));

/** Briefing order: urgent corrections first, then the engine's score; newest first among equals.
 * `rows` must already be newest first (the sort is stable). */
function byImportance<T extends Pick<Story, "score" | "protected">>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) => Number(!!b.protected) - Number(!!a.protected) || (b.score ?? 0) - (a.score ?? 0),
  );
}

/** Split the projected view into the lists each page renders. The briefing's sections keep the
 * engine's importance order (focus and radar exactly as it chose them, 更多进展 by score); search,
 * saved stories, follows and the archive are newest first. */
export function sections(
  view: View | null,
  topic: string,
  query: string,
  selectedFollow: string,
) {
  const matches = (e: Story) => matchesStory(e, topic, query);
  const events = newestFirst(view?.events.filter(matches) || [], true);
  const saved = view?.saved_events || view?.events.filter((e) => e.saved) || [];
  const follows = view?.follows || [];
  const followed = follows.find((f) => f.id === selectedFollow) || follows[0];
  const byId = new Map(events.map((e) => [e.id, e]));
  const picked = (ids: string[] = []) => ids.map((id) => byId.get(id)).filter((e): e is Story => !!e);
  return {
    events,
    focus: picked(view?.focus),
    radar: picked(view?.radar),
    discover: events.filter((e) => e.qualified && !e.dismissed),
    /** Qualified news the briefing did not already show as focus or radar. Late finds and
     * undated reports stay out of the briefing; search still finds them. */
    more: byImportance(
      events.filter(
        (e) =>
          e.qualified &&
          !e.dismissed &&
          e.timely !== false &&
          !view?.focus.includes(e.id) &&
          !view?.radar.includes(e.id),
      ),
    ),
    follows,
    followed,
    saved: newestFirst(saved.filter(matches), true),
    followingEvents: events.filter((e) => followed?.event_ids.includes(e.id)),
    archive: newestFirst(view?.archive || []),
    okSources: view?.sources.filter((s) => s.state.status === "ok").length || 0,
  };
}

/** Short descriptions become a full sentence the intent model can work with. */
export function followSeed(description = "", context = "") {
  const seed = description || context;
  return seed.length >= 10
    ? seed
    : seed
      ? `我想持续了解「${seed}」的新进展，请帮我明确值得追踪的方向。`
      : "";
}

/** Toast after a reader action; `wasOn` is the state before a toggle (saved, known, useful). */
export function feedbackNotice(kind: string, wasOn: boolean, topicLabel = "") {
  if (kind === "known")
    return wasOn
      ? "已改回未了解，下次更新仍可能进入重点。"
      : "已标为了解，下次更新起不再进入重点；有实质更新时仍会出现。";
  if (kind === "saved") return wasOn ? "已取消收藏。" : "已收藏，可在「收藏」中找到。";
  if (kind === "useful")
    return wasOn
      ? "已撤回「有帮助」。"
      : `已记录，之后会多推荐${topicLabel ? `「${topicLabel}」方向的` : "类似"}内容。`;
  return "已记录，类似内容会减少推荐。";
}

/** Whether the reader's own action of this kind is active on the story. */
export const hasAction = (story: Story, kind: string) =>
  story.actions.some((a) => a.kind === kind);

/** The briefing's three most important stories, in the engine's ranking order (not by date). */
export function topThree(view: View | null) {
  if (!view) return [];
  const byId = new Map(view.events.map((e) => [e.id, e]));
  return view.focus
    .map((id) => byId.get(id))
    .filter((e): e is Story => !!e && !e.dismissed)
    .slice(0, 3);
}

export type Change = { story: Story; kind: "new" | "updated" | "correction"; label: string };

/** What changed since the reader was last here, in the order of `list` (the briefing).
 *
 * New: first seen after `since`. Updated: an older story with a report captured after it,
 * labelled by what that report did (a correction, a test, an update, or more reports).
 * Stories already known or dismissed are left out: they were read. Null without a previous
 * visit, so a first visit shows nothing rather than "everything changed". */
export function sinceVisit(list: Story[], since?: string | null): Change[] | null {
  const from = Date.parse(since ?? "");
  if (Number.isNaN(from)) return null;
  const after = (value?: string | null) => {
    const at = Date.parse(value ?? "");
    return !Number.isNaN(at) && at > from;
  };
  const corrects = (actions: Set<string>) => actions.has("correction") || actions.has("withdrawal");
  const changes: Change[] = [];
  for (const story of list) {
    if (story.known || story.dismissed) continue;
    if (after(story.first_captured_at ?? story.captured_at)) {
      const correction = corrects(new Set([story.action]));
      changes.push({
        story,
        kind: correction ? "correction" : "new",
        label: correction ? "更正" : "新",
      });
      continue;
    }
    const fresh = story.timeline.filter((t) => after(t.captured_at));
    if (!fresh.length) continue;
    const actions = new Set(fresh.map((t) => t.action));
    const label = corrects(actions)
      ? "更正"
      : actions.has("test")
        ? "新测试"
        : actions.has("update")
          ? "有更新"
          : `新报道 ${fresh.length} 篇`;
    changes.push({ story, kind: label === "更正" ? "correction" : "updated", label });
  }
  return changes;
}

/** "今天 12:00" / "昨天 0:00" / "11月9日 12:00" relative to `now`. */
export function clockLabel(value?: string | null, now = new Date()) {
  const date = new Date(value ?? "");
  if (Number.isNaN(date.getTime())) return "";
  const at = zoned(date);
  const day = (d: ReturnType<typeof zoned>) => Date.UTC(d.year, d.month - 1, d.day);
  const diff = Math.round((day(at) - day(zoned(now))) / 86400000);
  const time = `${at.hour}:${String(at.minute).padStart(2, "0")}`;
  const prefix =
    diff === 0
      ? "今天"
      : diff === -1
        ? "昨天"
        : diff === 1
          ? "明天"
          : `${at.month}月${at.day}日`;
  return `${prefix} ${time}`;
}

/** One line about the latest and the next update. */
export function updateLine(view: View | null, now = new Date()) {
  if (!view) return "";
  const last = view.last_refresh;
  const parts = [
    last?.finished_at
      ? `更新于 ${clockLabel(last.finished_at, now)}${last.trigger === "scheduled" ? "（自动）" : ""}`
      : "尚未完成更新",
  ];
  if (view.schedule?.enabled) parts.push(`下次自动 ${clockLabel(view.schedule.next, now)}`);
  return parts.join(" · ");
}

export const snapshotLabel: Record<string, string> = {
  refresh: "更新",
  discovery: "外部搜索",
  following: "话题追踪",
};

/** Short label for one waiting job in the task queue. */
export function queueLabel(run: Run) {
  return run.kind === "following"
    ? `追踪「${run.follow_name}」`
    : run.kind === "discovery"
      ? `搜索「${run.query}」`
      : run.kind === "other"
        ? "其他读者的任务"
        : "更新情报";
}

/** Events a reader may fold this one into: same topic, newest first. */
export function mergeCandidates(view: View | null, story: Story, limit = 30) {
  return newestFirst(
    (view?.events || []).filter((e) => e.id !== story.id && e.topic === story.topic),
  ).slice(0, limit);
}

/* ---------- lenses: company moves, open source and community, research, policy ---------- */

export type Lens = "company" | "community" | "research" | "policy";
export const lensLabel: Record<Lens, string> = {
  company: "公司动向",
  community: "开源与社区",
  research: "研究",
  policy: "政策与产业",
};
export type Trend = { lens: Lens; company: string; product: string };

/** `#trends/<lens>/<company>/<product>`; missing parts are empty (the page picks defaults). */
export function trendFromHash(hash: string): Trend {
  const parts = hash.replace(/^#/, "").split("/").map((p) => decodeURIComponent(p));
  const lens = (Object.keys(lensLabel) as Lens[]).includes(parts[1] as Lens)
    ? (parts[1] as Lens)
    : "company";
  return { lens, company: parts[2] || "", product: parts[3] || "" };
}

export function trendHash({ lens, company, product }: Trend) {
  return ["trends", lens, company, product]
    .filter(Boolean)
    .map((p) => encodeURIComponent(p))
    .join("/");
}

const readable = (s: Story) => s.qualified && !s.dismissed;

/** A release, correction or withdrawal, or anything urgent: a large node on a line. */
export const isMajor = (s: Story) =>
  !!s.protected || ["release", "correction", "withdrawal"].includes(s.action);

/** What one company did (it is the actor), optionally one product group, newest first. */
export function companyLine(events: Story[], company: string, product = "") {
  return newestFirst(
    events.filter(
      (s) =>
        readable(s) &&
        s.companies?.some((c) => c.id === company && (!product || c.products.includes(product))),
    ),
    true,
  );
}

/** Reports that only mention the company (a customer, a lawsuit, someone else's test). */
export function companyMentions(events: Story[], company: string) {
  return newestFirst(
    events.filter((s) => readable(s) && s.mentions?.includes(company)),
    true,
  );
}

/** Stories under one lens, newest first. */
export function lensStories(events: Story[], lens: Lens) {
  return newestFirst(
    events.filter((s) => readable(s) && s.lenses?.includes(lens)),
    true,
  );
}

/** How many moves each company and each of its product groups has. */
export function lineCounts(events: Story[], company = "") {
  const companies: Record<string, number> = {};
  const products: Record<string, number> = {};
  for (const s of events) {
    if (!readable(s)) continue;
    for (const c of s.companies || []) {
      companies[c.id] = (companies[c.id] || 0) + 1;
      if (c.id === company) for (const p of c.products) products[p] = (products[p] || 0) + 1;
    }
  }
  return { companies, products };
}

/** "11月24日" in the display timezone; lines group their nodes by this day. */
export function dayLabel(value?: string | null, capturedAt?: string) {
  const at = Date.parse(value ?? "") || Date.parse(capturedAt ?? "");
  if (!Number.isFinite(at)) return "日期未确认";
  const d = zoned(at);
  return `${d.month}月${d.day}日`;
}

/** A newest-first line grouped by publication day. Stories without a publication date come
 * last under one "发布日期未知" heading: their collection day is not when they happened, and
 * labelling them by it would repeat a day heading further down the line. */
export function lineDays<T extends NewsDate>(rows: T[]): { day: string; stories: T[] }[] {
  const days: { day: string; stories: T[] }[] = [];
  for (const row of rows) {
    const day = Number.isFinite(Date.parse(row.published_at ?? "")) ? dayLabel(row.published_at) : "发布日期未知";
    const same = days.find((d) => d.day === day);
    if (same) same.stories.push(row);
    else days.push({ day, stories: [row] });
  }
  return days;
}

const IMPLIED_PRODUCTS = new Set(["research", "corporate"]);

/** Strip trailing full-width parentheticals ("ChatGPT（含 Codex）" -> "ChatGPT") for compact badges. */
export function shortProductName(name: string) {
  return name.replace(/（[^）]*）\s*$/, "").trim() || name;
}

export type CompanyCatalogEntry = NonNullable<View["companies"]>[number];

export type CompanyCard = {
  id: string;
  name: string;
  productSummary: string;
  products: { id: string; name: string; shortName: string; count: number }[];
  total: number;
  officialCount: number;
  majorCount: number;
  freshCount: number;
  mentionCount: number;
  latest: Story[];
};

/** Overview cards for every company in the catalog: active ones ranked by move count, quiet ones after. */
export function companyCards(
  catalog: CompanyCatalogEntry[],
  events: Story[],
  previousVisit?: string | null,
): { active: CompanyCard[]; quiet: CompanyCard[] } {
  const counts = lineCounts(events);
  const active: CompanyCard[] = [];
  const quiet: CompanyCard[] = [];
  for (const entry of catalog) {
    const line = companyLine(events, entry.id);
    const mentions = companyMentions(events, entry.id);
    const { products: prodCounts } = lineCounts(events, entry.id);
    const explicit = entry.products.filter((p) => !IMPLIED_PRODUCTS.has(p.id));
    const productSummary = explicit.map((p) => shortProductName(p.name)).join(" · ");
    const products = entry.products
      .filter((p) => prodCounts[p.id] > 0)
      .map((p) => ({
        id: p.id,
        name: p.name,
        shortName: shortProductName(p.name),
        count: prodCounts[p.id],
      }))
      .sort((a, b) => b.count - a.count);
    const officialCount = line.filter(
      (s) => s.companies?.find((c) => c.id === entry.id)?.official,
    ).length;
    const majorCount = line.filter(isMajor).length;
    const freshCount = (sinceVisit(line, previousVisit) || []).length;
    const card: CompanyCard = {
      id: entry.id,
      name: entry.name,
      productSummary,
      products,
      total: counts.companies[entry.id] || 0,
      officialCount,
      majorCount,
      freshCount,
      mentionCount: mentions.length,
      latest: line.slice(0, 2),
    };
    if (card.total > 0) active.push(card);
    else quiet.push(card);
  }
  active.sort((a, b) => b.total - a.total);
  return { active, quiet };
}

/* ---------- one story's evidence, stage by stage ---------- */

export type Stage = "statement" | "test" | "change" | "coverage";
export const stageLabel: Record<Stage, string> = {
  statement: "发布方陈述",
  test: "测试",
  change: "更正与更新",
  coverage: "其他报道",
};

const party = (role?: string) => role === "official" || role === "research";

/** Who reported a test, never called independent (an article may relay the vendor's numbers). */
function tester(entry: Story["timeline"][number]) {
  if (entry.content_kind === "benchmark_snapshot") return "公开榜单数据";
  return entry.role === "official"
    ? "厂商自测"
    : entry.role === "research"
      ? "论文自报结果"
      : entry.role === "community"
        ? "社区报告的测试"
        : "媒体或作者报告的测试";
}

/** Each report as a node: its stage, a label for who/what it is and its day since the first
 * report (D0, D1 …), oldest first. Gaps name missing key stages ("尚未见他方测试"); they speak
 * only of the reports collected here. */
export function evidenceStages(story: Story) {
  const at = (t: Story["timeline"][number]) =>
    Date.parse(t.published_at ?? "") || Date.parse(t.captured_at ?? "") || NaN;
  const entries = [...story.timeline].sort((a, b) => (at(a) || 0) - (at(b) || 0));
  const start = entries.map(at).find(Number.isFinite);
  const nodes = entries.map((entry, index) => {
    const stage: Stage =
      entry.action === "correction" || entry.action === "withdrawal" || (entry.action === "update" && index > 0)
        ? "change"
        : entry.evidence === "reported_test" || entry.action === "test" || entry.content_kind === "benchmark_snapshot"
          ? "test"
          : party(entry.role)
            ? "statement"
            : "coverage";
    const label =
      stage === "statement"
        ? entry.role === "research"
          ? "论文原文"
          : "官方原文"
        : stage === "test"
          ? tester(entry)
          : stage === "change"
            ? actionLabel[entry.action] || "更新"
            : evidence(entry.evidence, entry.role, entry.content_kind);
    const time = at(entry);
    const day =
      start !== undefined && Number.isFinite(time) ? Math.floor((time - start) / 86400000) : null;
    return { entry, stage, label, day };
  });
  const gaps: string[] = [];
  if (!nodes.some((n) => party(n.entry.role)) && story.content_kind !== "benchmark_snapshot")
    gaps.push("未见官方或论文原文");
  if (
    ["release", "update", "test"].includes(story.action) &&
    !nodes.some((n) => n.stage === "test" && !party(n.entry.role))
  )
    gaps.push("尚未见他方测试");
  return { nodes, gaps };
}

/** Itemised evidence instead of a single strength score: each item is present or not. */
export function evidenceChecklist(story: Story) {
  const { nodes } = evidenceStages(story);
  const tests = nodes.filter((n) => n.stage === "test");
  return [
    { label: "官方或论文原文", ok: nodes.some((n) => party(n.entry.role)) },
    { label: "发布方自测", ok: tests.some((n) => party(n.entry.role)) },
    { label: "他方报告的测试", ok: tests.some((n) => !party(n.entry.role)) },
    {
      label: "更正或撤回",
      ok: nodes.some((n) => ["correction", "withdrawal"].includes(n.entry.action)),
    },
  ];
}

/* ---------- open source rankings ---------- */

export const rankingLabel: Record<string, string> = {
  "github-trending-daily": "今日增速",
  "github-trending-weekly": "本周增速",
  "github-new": "近 30 天新项目",
  "github-top": "star 总量",
};
export const repoFlagLabel: Record<string, string> = {
  collection: "列表或教程合集",
  few_forks: "fork 很少，热度存疑",
};

const count = (n: number) => n.toLocaleString("en-US");

/** "Python · ★ 12,345 · +1,034 今日" or "· 创建于 11月1日" for search lists. */
export function repoMeta(row: RepoRow, rankingId: string) {
  const period = rankingId.endsWith("weekly") ? "本周" : "今日";
  return [
    row.language,
    `★ ${count(row.stars)}`,
    row.gained != null ? `+${count(row.gained)} ${period}` : "",
    row.created_at ? `创建于 ${dayLabel(row.created_at)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Companies in the sidebar: the reader's own list in their order (companies no longer in the
 * catalog drop out), or, when they have not chosen, the four most active. */
export const DRAWER_AUTO = 4;
export const DRAWER_MAX = 8;
export function drawerCompanies(
  cards: { active: CompanyCard[]; quiet: CompanyCard[] },
  chosen?: string[] | null,
): CompanyCard[] {
  if (!chosen) return cards.active.slice(0, DRAWER_AUTO);
  const all = new Map([...cards.active, ...cards.quiet].map((c) => [c.id, c]));
  return chosen.map((id) => all.get(id)).filter((c): c is CompanyCard => !!c);
}

/* ---------- evidence chart: one lane per source, one column per day ---------- */

export type Mark = Stage | "opinion";

/** Layout for the story's evidence chart. x runs 0..1 from the first report's day to `now`, so
 * "现在" is always the right edge and no empty future days are drawn; the chart starts at least two
 * days before today so a fresh story still has room. Lanes are sources in order of first
 * appearance, the ninth and later grouped as "其他来源". Undated reports are left out and counted. */
export function evidenceLanes(story: Story, now = new Date(), maxLanes = 8) {
  const { nodes } = evidenceStages(story);
  const time = (n: (typeof nodes)[number]) =>
    Date.parse(n.entry.published_at ?? "") || Date.parse(n.entry.captured_at ?? "") || NaN;
  const dated = nodes.filter((n) => Number.isFinite(time(n)));
  const undated = nodes.length - dated.length;
  if (!dated.length) return { lanes: [], points: [], days: [], official: null, now: 1, undated };
  const dayStart = (t: number) => {
    const d = zoned(t);
    return t - (d.hour * 3600 + d.minute * 60) * 1000 - (t % 60000);
  };
  const times = dated.map(time);
  const first = Math.min(...times);
  const start = Math.min(dayStart(first), dayStart(now.getTime()) - 2 * 86400000);
  // A report dated after "now" (clock skew) still fits instead of falling off the edge.
  const end = Math.max(now.getTime(), ...times);
  const span = end - start;
  const x = (t: number) => Math.min(1, Math.max(0, (t - start) / span));
  const sources = [...new Set(dated.map((n) => n.entry.source))];
  const lanes =
    sources.length > maxLanes ? [...sources.slice(0, maxLanes - 1), "其他来源"] : sources;
  const lane = (source: string) => {
    const i = lanes.indexOf(source);
    return i >= 0 ? i : lanes.length - 1;
  };
  const points = dated.map((n) => ({
    x: x(time(n)),
    lane: lane(n.entry.source),
    mark: (n.stage === "coverage" && n.entry.evidence === "opinion" ? "opinion" : n.stage) as Mark,
    label: n.label,
    entry: n.entry,
  }));
  const days: { x: number; label: string }[] = [];
  for (let t = start; t < end; t += 86400000) days.push({ x: x(t), label: dayLabel(new Date(t).toISOString()) });
  const official = points.find((p) => p.mark === "statement");
  return { lanes, points, days, official: official ? official.x : null, now: x(now.getTime()), undated };
}

/** 快速翻阅: briefing stories not yet known, dismissed or seen twice, in briefing order. */
export function deckStories(list: Story[]) {
  const seen = new Set<string>();
  return list.filter((s) => {
    if (seen.has(s.id) || s.known || s.dismissed) return false;
    seen.add(s.id);
    return true;
  });
}

/* ---------- 今日简报 as one edition (2026-11-25) ---------- */

/** How many radar stories join the topic sections; the rest are one-line 快讯. */
export const EDITION_BODY_RADAR = 5;

/** "11月25日" · "星期三" · "上午版" · "0:46" in the display timezone. */
export function editionStamp(value?: string | null) {
  const at = Date.parse(value ?? "");
  if (!Number.isFinite(at)) return null;
  const d = zoned(at);
  const weekday = "日一二三四五六"[new Date(Date.UTC(d.year, d.month - 1, d.day)).getUTCDay()];
  return {
    date: `${d.month}月${d.day}日`,
    weekday: `星期${weekday}`,
    edition: d.hour < 12 ? "上午版" : "下午版",
    time: `${d.hour}:${String(d.minute).padStart(2, "0")}`,
  };
}

/** The briefing laid out as one edition: a lead, three highlights, the rest of focus and the
 * first radar stories by topic, the remaining radar as 快讯, and older stories with news since the
 * last visit. Order inside each part is the engine's importance order; nothing is added or
 * dropped from the engine's focus and radar. Change labels are sinceVisit's. */
export function editionLayout(view: View, bodyRadar = EDITION_BODY_RADAR) {
  const byId = new Map(view.events.map((e) => [e.id, e]));
  const pick = (ids: string[]) =>
    ids.map((id) => byId.get(id)).filter((e): e is Story => !!e && !e.dismissed);
  const focus = pick(view.focus);
  let radar = pick(view.radar);
  let lead: Story | null = focus[0] ?? null;
  if (!lead && radar.length) [lead, ...radar] = radar;
  const highlights = focus.slice(1, 4);
  const body = [...focus.slice(4), ...radar.slice(0, bodyRadar)];
  const brief = radar.slice(bodyRadar);
  const stories = [...(lead ? [lead] : []), ...highlights, ...body, ...brief];
  const sections: { topic: string; label: string; stories: Story[] }[] = [];
  for (const story of body) {
    const section = sections.find((s) => s.topic === story.topic);
    if (section) section.stories.push(story);
    else sections.push({ topic: story.topic, label: story.topic_label, stories: [story] });
  }
  const changes = new Map((sinceVisit(stories, view.previous_visit) || []).map((c) => [c.story.id, c]));
  // Older news: first seen before the last visit, a report collected since, not in this edition.
  const since = Date.parse(view.previous_visit ?? "");
  const shown = new Set(stories.map((s) => s.id));
  const older = Number.isFinite(since)
    ? view.events.filter(
        (e) =>
          e.qualified &&
          !e.dismissed &&
          !shown.has(e.id) &&
          e.timely !== false &&
          Date.parse(e.first_captured_at ?? e.captured_at ?? "") <= since,
      )
    : [];
  const followups = (sinceVisit(older, view.previous_visit) || []).slice(0, 4);
  return {
    lead,
    highlights,
    sections,
    brief,
    followups,
    stories,
    changes,
    read: stories.filter((s) => s.known).length,
  };
}

/** One story's reports over the last `days` days on a 0..1 line ending at now, in the marks of
 * the evidence chart (official/paper text, test, coverage, opinion, correction). */
export function recentMarks(story: Story, now = new Date(), days = 7) {
  const end = now.getTime();
  const start = end - days * 86400000;
  const points = evidenceStages(story)
    .nodes.map((n) => {
      const at = Date.parse(n.entry.published_at ?? "") || Date.parse(n.entry.captured_at ?? "");
      return {
        x: (at - start) / (end - start),
        mark: (n.stage === "coverage" && n.entry.evidence === "opinion" ? "opinion" : n.stage) as Mark,
        label: n.label,
        entry: n.entry,
      };
    })
    .filter((p) => Number.isFinite(p.x) && p.x >= 0)
    .map((p) => ({ ...p, x: Math.min(1, p.x) }));
  // Hollow reports first, so statements, tests and corrections draw on top.
  return points.sort((a, b) => Number(b.mark === "coverage") - Number(a.mark === "coverage"));
}
