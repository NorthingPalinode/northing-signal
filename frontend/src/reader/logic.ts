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

export function when(value?: string | null, capturedAt?: string) {
  const published = Date.parse(value ?? "");
  const hasPublished = Number.isFinite(published);
  const date = hasPublished ? published : Date.parse(capturedAt ?? "");
  if (!Number.isFinite(date)) return "时间未确认";
  const label = new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  return hasPublished ? label : `收录于 ${label}`;
}

type NewsDate = { published_at: string | null; captured_at?: string };

function newestFirst<T extends NewsDate>(rows: T[]): T[] {
  const time = (row: NewsDate) => {
    const published = Date.parse(row.published_at ?? "");
    if (Number.isFinite(published)) return published;
    const captured = Date.parse(row.captured_at ?? "");
    return Number.isFinite(captured) ? captured : Number.MIN_SAFE_INTEGER;
  };
  return [...rows].sort((a, b) => time(b) - time(a));
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
  const events = newestFirst(view?.events.filter(matches) || []);
  const saved = view?.saved_events || view?.events.filter((e) => e.saved) || [];
  const follows = view?.follows || [];
  const followed = follows.find((f) => f.id === selectedFollow) || follows[0];
  return {
    events,
    focus: events.filter((e) => view?.focus.includes(e.id)),
    radar: events.filter((e) => view?.radar.includes(e.id)),
    discover: events.filter((e) => e.qualified && !e.dismissed),
    /** Qualified stories the briefing did not already show as focus or radar. */
    more: events.filter(
      (e) =>
        e.qualified &&
        !e.dismissed &&
        !view?.focus.includes(e.id) &&
        !view?.radar.includes(e.id),
    ),
    follows,
    followed,
    saved: newestFirst(saved.filter(matches)),
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

export function feedbackNotice(kind: string, wasSaved: boolean) {
  return kind === "known"
    ? "已标记了解；有实质更新时仍会出现。"
    : kind === "saved"
      ? wasSaved
        ? "已取消收藏。"
        : "已收藏，可在「收藏」中找到。"
      : kind === "useful"
        ? "已记录，下次整理会参考你的反馈。"
        : "已记录，这条内容将减少推荐。";
}

/** Short label for one waiting job in the task queue. */
export function queueLabel(run: Run) {
  return run.kind === "following"
    ? `追踪「${run.follow_name}」`
    : run.kind === "discovery"
      ? `搜索「${run.query}」`
      : "更新情报";
}

/** Events a reader may fold this one into: same topic, newest first. */
export function mergeCandidates(view: View | null, story: Story, limit = 30) {
  return newestFirst(
    (view?.events || []).filter((e) => e.id !== story.id && e.topic === story.topic),
  ).slice(0, limit);
}
