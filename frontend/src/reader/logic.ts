// Pure reader helpers: no React, DOM or network, so they run under node --test.
import type { Page, Run, Story, Topic, View } from "./types";

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
  kind === "benchmark_snapshot"
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

/** Split the projected view into the lists each page renders. */
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
  return {
    events,
    focus: events.filter((e) => view?.focus.includes(e.id)),
    radar: events.filter((e) => view?.radar.includes(e.id)),
    discover: events.filter((e) => e.qualified && !e.dismissed),
    /** Qualified news the briefing did not already show as focus or radar. Late finds and
     * undated reports stay out of the briefing; search still finds them. */
    more: events.filter(
      (e) =>
        e.qualified &&
        !e.dismissed &&
        e.timely !== false &&
        !view?.focus.includes(e.id) &&
        !view?.radar.includes(e.id),
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
