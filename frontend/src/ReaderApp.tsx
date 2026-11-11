import { useCallback, useEffect, useRef, useState } from "react";
import { searchSources, sourceName, type SearchSource } from "./searchSources";
import FollowIntentForm, { intervalLabel } from "./FollowIntentForm";
import StoryReader, { DetailActions, FeedbackChoices } from "./StoryDetail";
import { Glyph, Sheet, Toast } from "./ui";
import brandMark from "./assets/brand.svg?no-inline";

import {
  actionLabel,
  evidence,
  feedbackNotice,
  followSeed,
  neighbours,
  pageFromHash,
  queueLabel,
  sections,
  statusLabel,
  storyFromHash,
  topics,
  when,
} from "./reader/logic";
import type {
  Action,
  Archive,
  Follow,
  Page,
  Prefs,
  Run,
  Source,
  Story,
  Topic,
  View,
} from "./reader/types";

const currentPage = (): Page => pageFromHash(window.location.hash);

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/reader" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof value.detail === "string" ? value.detail : "暂时无法完成，请重试。",
    );
  return value;
}

const primaryNav: [Page, string, string][] = [
  ["briefing", "home", "简报"],
  ["discover", "search", "搜索"],
  ["following", "follow", "追踪"],
  ["saved", "bookmark", "收藏"],
];
const pageTitle: Record<Page, string> = {
  briefing: "今日简报",
  discover: "搜索与发现",
  following: "话题追踪",
  saved: "我的收藏",
  library: "资料库",
  story: "阅读",
};
const backLabel: Record<Page, string> = {
  briefing: "简报",
  discover: "搜索",
  following: "追踪",
  saved: "收藏",
  library: "资料库",
  story: "简报",
};
const dismissKinds = ["irrelevant", "thin", "duplicate"];

const today = () =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());

/** Sends a one-off "shown" interaction the first time a story is on screen. */
function useExposure(
  story: Story,
  send: (s: Story, kind: string) => Promise<unknown>,
) {
  const ref = useRef<HTMLElement>(null);
  const sent = useRef(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const check = () => {
      const box = node.getBoundingClientRect();
      if (
        !sent.current &&
        document.visibilityState === "visible" &&
        box.bottom > 0 &&
        box.top < innerHeight &&
        box.height > 0
      ) {
        sent.current = true;
        void send(story, "shown").catch(() => {
          sent.current = false;
        });
      }
    };
    const observer = new IntersectionObserver(check, { threshold: 0.25 });
    observer.observe(node);
    document.addEventListener("visibilitychange", check);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", check);
    };
  }, [story.id, story.version, send]);
  return ref;
}

function StoryRow({
  story,
  variant = "normal",
  index,
  reason,
  unread,
  readOnly,
  send,
  open,
  toggleSave,
  askFeedback,
}: {
  story: Story;
  variant?: "lead" | "normal" | "compact";
  index?: number;
  reason?: string;
  unread?: boolean;
  readOnly: boolean;
  send: (s: Story, kind: string) => Promise<unknown>;
  open: () => void;
  toggleSave: () => void;
  askFeedback: () => void;
}) {
  const ref = useExposure(story, send);
  const why = reason || story.reason;
  return (
    <article
      ref={ref}
      aria-label={story.title}
      className={
        "r-story r-story-" +
        variant +
        (story.protected ? " important" : "") +
        (story.known ? " known" : "")
      }
      onClick={(event) => {
        if (
          !(event.target as HTMLElement).closest("button, a, input, select") &&
          !window.getSelection()?.toString()
        )
          open();
      }}
    >
      {index !== undefined && (
        <span className="r-story-index" aria-hidden="true">
          {String(index + 1).padStart(2, "0")}
        </span>
      )}
      <div className="r-story-body">
        <div className="r-meta">
          <span className={"r-topic t-" + story.topic}>{story.topic_label}</span>
          {unread && <span className="r-badge accent">新进展</span>}
          {story.protected && (
            <span className="r-badge warn">重要{actionLabel[story.action]}</span>
          )}
          <span className="r-meta-text">
            {[
              story.source +
                (story.source_count > 1 ? ` +${story.source_count - 1}` : ""),
              when(story.published_at, story.captured_at),
              evidence(story.evidence, story.source_role, story.content_kind) +
                (story.policy_stale ? "（旧版规则）" : ""),
            ].join(" · ")}
          </span>
        </div>
        <h3>
          <button className="r-story-title" onClick={open}>
            {story.title}
          </button>
        </h3>
        <p className="r-story-summary">{story.summary}</p>
        {variant !== "compact" && why && (
          <p className="r-story-reason">
            <span>{reason ? "与你有关" : "值得读"}</span>
            {why}
          </p>
        )}
        {!readOnly && (
          <span className="r-story-actions">
            <button
              className={"r-icon" + (story.saved ? " on" : "")}
              aria-label={(story.saved ? "取消收藏：" : "收藏：") + story.title}
              aria-pressed={story.saved}
              title={story.saved ? "取消收藏" : "收藏"}
              onClick={toggleSave}
            >
              <Glyph name="bookmark" size={17} />
            </button>
            <button
              className="r-icon"
              aria-label={"不感兴趣：" + story.title}
              title="不感兴趣"
              onClick={askFeedback}
            >
              <Glyph name="more" size={17} />
            </button>
          </span>
        )}
      </div>
    </article>
  );
}

function TopicFilter({
  topic,
  setTopic,
  counts,
}: {
  topic: string;
  setTopic: (t: string) => void;
  counts?: Partial<Record<Topic, number>>;
}) {
  return (
    <div className="r-chips r-narrow-only" role="toolbar" aria-label="按方向筛选">
      <button
        className={!topic ? "active" : ""}
        aria-pressed={!topic}
        onClick={() => setTopic("")}
      >
        全部
      </button>
      {(Object.entries(topics) as [Topic, string][]).map(([id, label]) =>
        counts && !counts[id] && topic !== id ? null : (
          <button
            key={id}
            className={topic === id ? "active" : ""}
            aria-pressed={topic === id}
            onClick={() => setTopic(topic === id ? "" : id)}
          >
            <i className={"r-dot t-" + id} />
            {label}
            {counts?.[id] ? <small>{counts[id]}</small> : null}
          </button>
        ),
      )}
    </div>
  );
}

/** Wide-screen topic filter: every direction with its share of stories. */
function TopicCard({
  topic,
  setTopic,
  counts,
  title = "按方向",
}: {
  topic: string;
  setTopic: (t: string) => void;
  counts: Partial<Record<Topic, number>>;
  title?: string;
}) {
  const total = Object.values(counts).reduce((a, b) => a + (b || 0), 0);
  const max = Math.max(1, ...Object.values(counts).map((n) => n || 0));
  return (
    <section className="r-card">
      <h2 className="r-card-title">{title}</h2>
      <div className="r-topic-list" role="toolbar" aria-label="按方向筛选">
        <button
          className={!topic ? "active" : ""}
          aria-pressed={!topic}
          onClick={() => setTopic("")}
        >
          <span>全部</span>
          <small>{total}</small>
        </button>
        {(Object.entries(topics) as [Topic, string][]).map(([id, label]) => (
          <button
            key={id}
            className={topic === id ? "active" : ""}
            aria-pressed={topic === id}
            disabled={!counts[id] && topic !== id}
            onClick={() => setTopic(topic === id ? "" : id)}
          >
            <span>
              <i className={"r-dot t-" + id} />
              {label}
            </span>
            <small>{counts[id] || 0}</small>
            <em
              className={"t-" + id}
              style={{ width: `${((counts[id] || 0) / max) * 100}%` }}
            />
          </button>
        ))}
      </div>
    </section>
  );
}

function Empty({
  icon,
  title,
  children,
}: {
  icon: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="r-empty">
      <span className="r-empty-icon">
        <Glyph name={icon} size={26} />
      </span>
      <h2>{title}</h2>
      {children}
    </div>
  );
}

function topicCounts(stories: Story[]) {
  const counts: Partial<Record<Topic, number>> = {};
  for (const s of stories) counts[s.topic] = (counts[s.topic] || 0) + 1;
  return counts;
}

const sourceKind: Record<string, string> = {
  releases: "开源版本",
  publisher_index: "官网更新",
  changelog: "更新日志",
  document: "官方文档更新",
  markdown: "更新记录",
  hub_models: "模型目录与模型卡",
  modelscope_models: "模型目录",
  arxiv: "论文摘要",
  daily_papers: "论文发现",
  arena: "文本偏好榜单",
  swebench: "编程评测结果",
};
const sourceRole: Record<string, string> = {
  official: "官方发布",
  research: "研究机构",
  media: "专业媒体",
  author: "技术作者",
  community: "开发者社区",
};
const sourceState: Record<string, string> = {
  ok: "正常",
  error: "暂不可用",
  empty: "本次无结果",
};

export default function ReaderApp() {
  const [view, setView] = useState<View | null>(null);
  const [page, setPage] = useState<Page>(currentPage);
  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<{
    text: string;
    action?: { label: string; run: () => void };
  } | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [queue, setQueue] = useState<Run[]>([]);
  const [storyId, setStoryId] = useState(() =>
    storyFromHash(window.location.hash),
  );
  /** Where the open story came from: its list (for prev/next) and page (for back). */
  const [origin, setOrigin] = useState<{ page: Page; ids: string[] } | null>(
    null,
  );
  const [feedback, setFeedback] = useState<Story | null>(null);
  const [settings, setSettings] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [selectedFollow, setSelectedFollow] = useState("");
  const [followForm, setFollowForm] = useState<{
    description: string;
    follow_id?: string;
  } | null>(null);
  const [followBusy, setFollowBusy] = useState(false);
  const [channels, setChannels] = useState<SearchSource[]>([
    "web",
    "arxiv",
    "github",
  ]);
  const [channelsOpen, setChannelsOpen] = useState(false);
  const [libraryFilter, setLibraryFilter] = useState<
    "all" | "pending" | "failed"
  >("all");
  const [showAllMore, setShowAllMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<
    { id: string; created_at: string }[] | null
  >(null);
  const [historical, setHistorical] = useState<string | null>(null);
  const visited = useRef(false);
  const scrollMemo = useRef<{ page: Page; y: number } | null>(null);
  const restoreY = useRef<number | null>(null);
  const opened = useRef("");
  const keys = useRef<(e: KeyboardEvent) => void>(() => {});
  const baseline = useRef<string | null | undefined>(undefined);
  const say = useCallback(
    (text: string, action?: { label: string; run: () => void }) =>
      setNotice({ text, action }),
    [],
  );
  const fail = useCallback((e: unknown) => setError((e as Error).message), []);

  const load = useCallback(async () => {
    const result = await request<View>("");
    if (baseline.current === undefined)
      baseline.current = result.last_visit || null;
    setView(result);
    setHistorical(null);
    setRun(result.run);
    setQueue(result.queue || []);
    setError("");
    return result;
  }, []);
  useEffect(() => {
    void load().catch(fail);
  }, [load, fail]);
  useEffect(() => {
    const sync = () => {
      const next = currentPage();
      setPage(next);
      setStoryId(storyFromHash(window.location.hash));
      // Coming back from a story: return to the same place in the list.
      if (next !== "story" && scrollMemo.current?.page === next)
        restoreY.current = scrollMemo.current.y;
      // Only search and library show a search box; never filter other pages invisibly.
      if (next !== "discover" && next !== "library" && next !== "story")
        setQuery("");
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => {
    window.scrollTo(0, restoreY.current ?? 0);
    restoreY.current = null;
  }, [page, storyId]);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    if (page !== "following" || historical) return;
    const timer = setInterval(() => void load().catch(fail), 30000);
    return () => clearInterval(timer);
  }, [page, historical, load, fail]);
  useEffect(() => {
    if (!view || page !== "briefing") return;
    const mark = () => {
      if (!visited.current && document.visibilityState === "visible") {
        visited.current = true;
        void request("/visits", {
          method: "POST",
          body: JSON.stringify({ request_id: crypto.randomUUID() }),
        }).catch(() => {
          visited.current = false;
        });
      }
    };
    mark();
    document.addEventListener("visibilitychange", mark);
    return () => document.removeEventListener("visibilitychange", mark);
  }, [!!view, page]);
  useEffect(() => {
    if (run?.state !== "running" && !queue.length) return;
    let stopped = false;
    const watched = run?.id;
    const timer = setInterval(() => {
      void request<{ run: Run | null; queue: Run[]; sources: Source[] }>(
        "/status",
      )
        .then((result) => {
          if (stopped) return;
          setRun(result.run);
          setQueue(result.queue || []);
          // A finished job, or the next queued one taking over, has new content to show.
          if (result.run?.state !== "running" || result.run?.id !== watched)
            void load().catch(fail);
        })
        .catch((e) => {
          if (!stopped) fail(e);
        });
    }, 1500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [run?.state, run?.id, queue.length, load, fail]);

  async function syncStatus() {
    const result = await request<{ run: Run | null; queue: Run[] }>("/status");
    setRun(result.run);
    setQueue(result.queue || []);
  }
  /** Show a started job's progress, or say where a queued one waits. */
  function accept(next: Run, startedNotice = "") {
    if (next.state === "queued") {
      say("已加入队列，当前任务完成后自动开始。");
      void syncStatus().catch(fail);
    } else {
      setRun(next);
      if (startedNotice) say(startedNotice);
    }
  }
  async function cancel(id: string) {
    try {
      await request("/cancel", { method: "POST", body: JSON.stringify({ id }) });
      await load();
    } catch (e) {
      fail(e);
    }
  }
  async function retry(version: string) {
    try {
      setView(
        await request<View>(`/materials/${version}/retry`, { method: "POST" }),
      );
      say("已清除失败记录，下次更新时会重新整理。");
    } catch (e) {
      fail(e);
    }
  }
  const send = useCallback(
    async (story: Story, kind: string, retracts?: string) => {
      const requestId = crypto.randomUUID();
      await request("/interactions", {
        method: "POST",
        body: JSON.stringify({
          request_id: requestId,
          event_id: story.id,
          version: story.version,
          kind,
          retracts: retracts || null,
        }),
      });
      return requestId;
    },
    [],
  );
  const noSend = useCallback(async () => {}, []);
  async function act(story: Story, kind: string) {
    try {
      let requestId = "";
      if (kind === "saved" && story.saved) {
        for (const action of story.actions.filter((a) => a.kind === "saved"))
          await send(
            { ...story, version: action.version },
            "retract",
            action.request_id,
          );
      } else requestId = await send(story, kind);
      const dismissed = dismissKinds.includes(kind);
      say(
        feedbackNotice(kind, story.saved),
        kind === "saved" && !story.saved && page !== "saved"
          ? { label: "查看收藏", run: () => navigate("saved") }
          : dismissed && requestId
            ? {
                label: "撤销",
                run: () =>
                  void send(story, "retract", requestId)
                    .then(load)
                    .then(() => say("已撤销，这条内容会照常出现。"))
                    .catch(fail),
              }
            : undefined,
      );
      setFeedback(null);
      // Not interested in what you are reading: move straight on to the next story.
      if (dismissed && page === "story" && storyId === story.id) {
        if (position.next) goStory(position.next);
        else closeStory();
      }
      await load();
    } catch (e) {
      fail(e);
    }
  }
  async function undo(story: Story, action: Action) {
    try {
      await send(
        { ...story, version: action.version },
        "retract",
        action.request_id,
      );
      say("已撤回这条反馈。");
      await load();
    } catch (e) {
      fail(e);
    }
  }
  /** Split one report out of an event, or fold the event into another. */
  async function regroup(story: Story, path: string, body: object, done: string) {
    try {
      setView(
        await request<View>(`/events/${story.id}/${path}`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      );
      // A merged story lives on under the event it was folded into.
      if (path === "merge" && "into" in body) goStory(String(body.into));
      say(done);
    } catch (e) {
      fail(e);
    }
  }
  /** Open a story as its own page; `list` is what prev/next walk through. */
  function open(story: Story, list: Story[] = [story]) {
    setOrigin({ page, ids: list.map((s) => s.id) });
    scrollMemo.current = { page, y: window.scrollY };
    window.location.hash = "story/" + encodeURIComponent(story.id);
  }
  /** Prev/next replace the history entry so Back always returns to the list. */
  function goStory(id: string) {
    window.location.replace("#story/" + encodeURIComponent(id));
  }
  function closeStory() {
    if (origin) window.history.back();
    else navigate("briefing");
  }
  async function discover() {
    const q = query.trim();
    if (q.length < 2 || !channels.length) return;
    try {
      accept(
        await request<Run>("/discover", {
          method: "POST",
          body: JSON.stringify({ query: q, channels }),
        }),
        `正在从 ${channels.length} 个来源搜索「${q}」，结果会保存在本机。`,
      );
    } catch (e) {
      fail(e);
    }
  }
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      accept(
        await request<Run>("/refresh", {
          method: "POST",
          body: JSON.stringify({ limit_per_source: 10, analyze_limit: 24 }),
        }),
      );
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function savePrefs() {
    if (!prefs || !prefs.topics.length) return;
    try {
      setView(
        await request<View>("/preferences", {
          method: "PUT",
          body: JSON.stringify(prefs),
        }),
      );
      setHistorical(null);
      setSettings(false);
      say("阅读偏好已更新。");
    } catch (e) {
      fail(e);
    }
  }
  function openPrefs() {
    setMenuOpen(false);
    setPrefs(view?.preferences || null);
    setSettings(true);
  }
  function openHistory() {
    setMenuOpen(false);
    void request<{ id: string; created_at: string }[]>("/snapshots")
      .then(setHistory)
      .catch(fail);
  }
  function navigate(next: Page) {
    setMenuOpen(false);
    scrollMemo.current = null;
    setPage(next);
    window.location.hash = next;
    setTopic("");
    if (next !== "discover") setQuery("");
    setShowAllMore(false);
    if (historical) void load().catch(fail);
  }
  function beginFollow(description = "", context = "", followId?: string) {
    setFollowForm({
      description: followSeed(description, context),
      follow_id: followId,
    });
  }
  function confirmedFollow(updated: View) {
    setView(updated);
    setRun(updated.run);
    setQueue(updated.queue || []);
    setSelectedFollow(updated.confirmed_follow_id || "");
    setFollowForm(null);
    navigate("following");
    say("追踪方案已确认，后续按这份意图执行。");
  }
  async function updateFollow(
    follow: Follow,
    action: "pause" | "remove" | "seen" | "refresh",
  ) {
    if (
      action === "remove" &&
      !window.confirm(`取消追踪「${follow.name}」？已收集的内容仍保留在资料库。`)
    )
      return;
    setFollowBusy(true);
    try {
      if (action === "refresh") {
        accept(
          await request<Run>(`/follows/${follow.id}/refresh`, {
            method: "POST",
          }),
        );
      } else {
        const suffix = action === "seen" ? "/seen" : "";
        const updated = await request<View>(`/follows/${follow.id}${suffix}`, {
          method:
            action === "pause"
              ? "PATCH"
              : action === "remove"
                ? "DELETE"
                : "POST",
          ...(action === "pause"
            ? { body: JSON.stringify({ active: !follow.active }) }
            : {}),
        });
        setView(updated);
        setRun(updated.run);
        setQueue(updated.queue || []);
        if (action === "remove") say(`已取消追踪「${follow.name}」。`);
      }
    } catch (e) {
      fail(e);
    } finally {
      setFollowBusy(false);
    }
  }

  const running = run?.state === "running";
  const refreshRunning = running && run?.kind === "refresh";
  const refreshQueued = queue.some((r) => r.kind === "refresh");
  const followPending = (id?: string) =>
    !!id &&
    ((running && run?.follow_id === id) ||
      queue.some((r) => r.follow_id === id));
  const {
    focus,
    radar,
    more,
    discover: browse,
    follows,
    followed,
    saved,
    followingEvents,
    archive,
    okSources,
  } = sections(view, topic, query, selectedFollow);
  const fixedSources =
    view?.sources.filter((s) => s.kind !== "search").length || 0;
  const unreadFollows = follows.reduce((n, f) => n + f.unread_ids.length, 0);
  const savedCount =
    view?.saved_events?.length ?? view?.events.filter((e) => e.saved).length ?? 0;
  const newSince =
    baseline.current && view
      ? view.events.filter(
          (e) =>
            e.qualified &&
            !e.known &&
            new Date(e.captured_at) > new Date(baseline.current!),
        ).length
      : 0;
  const all = view?.events || [];
  const briefingList = [...focus, ...radar, ...more];
  const storyPool = view ? [...all, ...(view.saved_events || [])] : [];
  const byId = (id: string) => storyPool.find((e) => e.id === id);
  const current = page === "story" ? byId(storyId) : undefined;
  const trail = origin?.ids.includes(storyId)
    ? origin.ids
    : briefingList.map((s) => s.id);
  const position = neighbours(trail, storyId);
  const from = origin?.page || "briefing";
  const navPage = page === "story" ? from : page;

  useEffect(() => {
    if (page !== "story") {
      opened.current = "";
      return;
    }
    if (!current || historical || opened.current === current.id) return;
    opened.current = current.id;
    void send(current, "opened").catch(fail);
  }, [page, current?.id, historical, send, fail]);

  keys.current = (e) => {
    if (page !== "story" || e.metaKey || e.ctrlKey || e.altKey) return;
    const target = e.target as HTMLElement;
    if (
      target.closest("input, textarea, select, [contenteditable]") ||
      document.querySelector("dialog[open]")
    )
      return;
    const key = e.key.toLowerCase();
    if (key === "escape") closeStory();
    else if ((key === "j" || key === "arrowright") && position.next)
      goStory(position.next);
    else if ((key === "k" || key === "arrowleft") && position.prev)
      goStory(position.prev);
    else return;
    e.preventDefault();
  };

  function row(
    story: Story,
    variant: "lead" | "normal" | "compact" = "normal",
    extra: {
      index?: number;
      reason?: string;
      unread?: boolean;
      list?: Story[];
    } = {},
  ) {
    const { list, ...rest } = extra;
    return (
      <StoryRow
        key={story.id + story.version}
        story={story}
        variant={variant}
        {...rest}
        readOnly={!!historical}
        send={historical ? noSend : send}
        open={() => open(story, list)}
        toggleSave={() => void act(story, "saved")}
        askFeedback={() => setFeedback(story)}
      />
    );
  }

  const updateButton = (
    <button
      className="r-button primary r-update"
      disabled={refreshRunning || refreshQueued || busy || !!historical}
      onClick={() => void refresh()}
    >
      <span className={refreshRunning ? "r-spin" : ""}>
        <Glyph name="refresh" size={16} />
      </span>
      <span>
        {refreshRunning ? "更新中…" : refreshQueued ? "已排队" : "更新"}
      </span>
    </button>
  );

  const secondaryNav = (
    <>
      <button
        className={navPage === "library" ? "selected" : ""}
        aria-current={navPage === "library" ? "page" : undefined}
        onClick={() => navigate("library")}
      >
        <Glyph name="book" size={18} />
        <span>资料库</span>
        <small>{view?.counts.materials || ""}</small>
      </button>
      <button onClick={openHistory}>
        <Glyph name="clock" size={18} />
        <span>过去的简报</span>
      </button>
      <button
        onClick={() => {
          setMenuOpen(false);
          setSourcesOpen(true);
        }}
      >
        <Glyph name="signal" size={18} />
        <span>来源状态</span>
        <small>
          {okSources}/{fixedSources}
        </small>
      </button>
      <button onClick={openPrefs}>
        <Glyph name="settings" size={18} />
        <span>阅读偏好</span>
      </button>
    </>
  );

  /* ---------- pages ---------- */

  function briefingPage() {
    if (!view) return null;
    const visibleMore = showAllMore ? more : more.slice(0, 6);
    const nothing = !focus.length && !radar.length && !more.length;
    return (
      <>
        <TopicFilter
          topic={topic}
          setTopic={setTopic}
          counts={topicCounts(all.filter((e) => e.qualified && !e.dismissed))}
        />
        {nothing ? (
          <Empty
            icon="compass"
            title={
              topic
                ? "这个方向暂时没有内容"
                : view.counts.materials
                  ? "还没有整理好的进展"
                  : "从第一次更新开始"
            }
          >
            <p>
              {topic
                ? "换个方向看看，或到资料库查找原始材料。"
                : view.counts.pending
                  ? `已收取 ${view.counts.materials} 条材料，还有 ${view.counts.pending} 条等待整理。${view.model_configured ? "" : "当前未配置模型，材料会保留但不会被整理。"}`
                  : "检查官方发布、研究与专业作者，把有依据的变化整理给你。"}
            </p>
            <div className="r-empty-actions">
              {!topic && !running && !historical && (
                <button className="r-button primary" onClick={() => void refresh()}>
                  立即更新
                </button>
              )}
              <button className="r-button" onClick={() => navigate("library")}>
                查看资料库
              </button>
            </div>
          </Empty>
        ) : (
          <>
            {focus.length > 0 && (
              <section className="r-section">
                <header className="r-section-head">
                  <h2>重点</h2>
                  <button className="r-link" onClick={openPrefs}>
                    约 {Math.max(1, Math.ceil(view.estimated_seconds / 60))} 分钟 ·
                    预算 {view.preferences.budget_minutes} 分钟
                  </button>
                </header>
                <div className="r-list-stories r-grid">
                  {focus.map((s, i) =>
                    row(s, i === 0 ? "lead" : "normal", { list: briefingList }),
                  )}
                </div>
              </section>
            )}
            {radar.length > 0 && (
              <section className="r-section">
                <header className="r-section-head">
                  <h2>前沿速览</h2>
                  <small>值得留意的新方向</small>
                </header>
                <div className="r-list-stories compact">
                  {radar.map((s, i) =>
                    row(s, "compact", { index: i, list: briefingList }),
                  )}
                </div>
              </section>
            )}
            {more.length > 0 && (
              <section className="r-section">
                <header className="r-section-head">
                  <h2>更多进展</h2>
                  <small>{more.length} 项 · 最新在前</small>
                </header>
                <div className="r-list-stories compact">
                  {visibleMore.map((s) =>
                    row(s, "compact", { list: briefingList }),
                  )}
                </div>
                {more.length > visibleMore.length && (
                  <button
                    className="r-button block"
                    onClick={() => setShowAllMore(true)}
                  >
                    再显示 {more.length - visibleMore.length} 项
                  </button>
                )}
              </section>
            )}
          </>
        )}
      </>
    );
  }

  function discoverPage() {
    if (!view) return null;
    const q = query.trim();
    const libraryHits = q
      ? archive.filter((row) =>
          (row.title + (row.summary || "") + row.source)
            .toLowerCase()
            .includes(q.toLowerCase()),
        ).length
      : 0;
    const lastDiscovery =
      run?.kind === "discovery" && run.state !== "running" ? run : null;
    return (
      <>
        <form
          className="r-searchbox"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            void discover();
          }}
        >
          <Glyph name="search" size={20} />
          <input
            aria-label="搜索"
            placeholder="搜索已有进展，或在外部来源中查找…"
            value={query}
            maxLength={80}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button
              type="button"
              className="r-icon"
              aria-label="清除"
              onClick={() => setQuery("")}
            >
              <Glyph name="close" size={16} />
            </button>
          )}
        </form>

        {q.length >= 2 && !historical && (
          <div className="r-external">
            <div className="r-external-main">
              <div>
                <strong>在外部来源中查找「{q}」</strong>
                <small>
                  将检索 {channels.map((c) => searchSources[c]).join("、") || "—"}
                  <button
                    type="button"
                    className="r-link small r-narrow-only"
                    onClick={() => setChannelsOpen(!channelsOpen)}
                  >
                    {channelsOpen ? "收起" : "更改来源"}
                  </button>
                </small>
              </div>
              <div className="r-external-buttons">
                <button
                  className="r-button primary"
                  disabled={!channels.length || (running && run?.kind === "discovery")}
                  onClick={() => void discover()}
                >
                  搜索
                </button>
                <button
                  className="r-button"
                  onClick={() => beginFollow(q)}
                  title="让 AI 理解需求后定期追踪"
                >
                  持续追踪
                </button>
              </div>
            </div>
            {channelsOpen && (
              <fieldset className="r-channel-grid r-narrow-only">
                <legend>检索来源</legend>
                {(Object.entries(searchSources) as [SearchSource, string][]).map(
                  ([id, label]) => (
                    <label key={id} className={channels.includes(id) ? "on" : ""}>
                      <input
                        type="checkbox"
                        checked={channels.includes(id)}
                        onChange={(e) =>
                          setChannels(
                            e.target.checked
                              ? [...channels, id]
                              : channels.filter((key) => key !== id),
                          )
                        }
                      />
                      {label}
                    </label>
                  ),
                )}
                <p>
                  关键词只发送给勾选的来源；搜索摘要先作为线索，取得原文后再整理。X、抖音、小红书仅支持公开网页索引，覆盖有限。
                </p>
              </fieldset>
            )}
          </div>
        )}

        {lastDiscovery && (
          <section className="r-section r-results" aria-label="本次外部搜索结果">
            <header className="r-section-head">
              <h2>外部搜索「{lastDiscovery.query}」</h2>
              <small>
                {lastDiscovery.found || 0} 条线索 · {lastDiscovery.analyzed} 条已整理
              </small>
            </header>
            {(lastDiscovery.errors.includes("source_unavailable") ||
              lastDiscovery.found === 0) && (
              <p className="r-muted">
                {lastDiscovery.errors.includes("source_unavailable")
                  ? "部分检索来源暂时不可用。"
                  : ""}
                {lastDiscovery.found === 0
                  ? "没有找到线索，可换用更具体的英文检索词再试。"
                  : ""}
              </p>
            )}
            <ul className="r-plain-list">
              {archive
                .filter((row) => lastDiscovery.result_versions?.includes(row.version))
                .map((row) => {
                  const story = all.find((event) =>
                    event.timeline.some((item) => item.version === row.version),
                  );
                  return (
                    <li key={row.version}>
                      {story ? (
                        <button onClick={() => open(story)}>{row.title}</button>
                      ) : (
                        <a href={row.url} target="_blank" rel="noreferrer">
                          {row.title} <Glyph name="external" size={13} />
                        </a>
                      )}
                      <small>
                        {row.content_kind === "search_excerpt"
                          ? "搜索线索 · 正文待获取"
                          : statusLabel[row.status] || row.status}
                      </small>
                    </li>
                  );
                })}
            </ul>
          </section>
        )}

        <section className="r-section">
          <header className="r-section-head">
            <h2>{q ? "已有内容中的结果" : "浏览全部进展"}</h2>
            <small>
              {browse.length} 项
              {q && libraryHits > 0 && (
                <>
                  {" · "}
                  <button
                    className="r-link"
                    onClick={() => {
                      setPage("library");
                      window.location.hash = "library";
                    }}
                  >
                    资料库中 {libraryHits} 条原始材料
                  </button>
                </>
              )}
            </small>
          </header>
          {!q && (
            <TopicFilter
              topic={topic}
              setTopic={setTopic}
              counts={topicCounts(all.filter((e) => e.qualified && !e.dismissed))}
            />
          )}
          {browse.length ? (
            <div className="r-list-stories compact">
              {browse.map((s) => row(s, "normal", { list: browse }))}
            </div>
          ) : (
            <Empty icon="search" title={q ? "已有内容中没有匹配" : "暂时没有内容"}>
              <p>
                {q
                  ? q.length >= 2
                    ? "可以用上方的「搜索」到外部来源查找。"
                    : "再多输入一个字。"
                  : "更新一次简报后，这里会出现可浏览的进展。"}
              </p>
            </Empty>
          )}
        </section>
      </>
    );
  }

  function followingPage() {
    if (!view) return null;
    if (!follows.length || !followed)
      return (
        <Empty icon="follow" title="描述想了解的事，让 AI 帮你追踪">
          <p>
            用一句话说清目标和偏好，先核对 AI 的理解与检索方案，确认后才开始定期检查。
          </p>
          <div className="r-empty-actions">
            <button className="r-button primary" onClick={() => beginFollow()}>
              <Glyph name="plus" size={16} /> 新增追踪
            </button>
          </div>
          <div className="r-suggest">
            <small>或从这些方向开始</small>
            {[
              ["Agent 与开发", "AI agents, 智能体"],
              ["具身智能", "embodied AI, robotics"],
              ["大模型推理", "LLM inference, 推理优化"],
            ].map(([name, q]) => (
              <button key={name} onClick={() => beginFollow(name, q)}>
                {name}
              </button>
            ))}
          </div>
        </Empty>
      );
    const plan = followed.intent_plan;
    return (
      <div className="r-follow">
        <nav className="r-follow-list" aria-label="追踪的话题">
          {follows.map((follow) => (
            <button
              key={follow.id}
              className={follow.id === followed.id ? "active" : ""}
              aria-current={follow.id === followed.id ? "true" : undefined}
              onClick={() => {
                setSelectedFollow(follow.id);
                setQuery("");
                setTopic("");
              }}
            >
              <span>
                <strong>{follow.name}</strong>
                <small>{follow.active ? "追踪中" : "已暂停"}</small>
              </span>
              {follow.unread_ids.length > 0 && (
                <b aria-label={follow.unread_ids.length + " 条新进展"}>
                  {follow.unread_ids.length}
                </b>
              )}
            </button>
          ))}
          <button className="r-follow-add" onClick={() => beginFollow()}>
            <Glyph name="plus" size={16} /> 新增追踪
          </button>
        </nav>
        <section className="r-follow-feed">
          <header className="r-follow-head">
            <div>
              <h2>{followed.name}</h2>
              <p>
                {plan?.intent_summary ||
                  `旧版关键词话题：${followed.query}。重新描述需求即可升级为意图追踪。`}
              </p>
              <small>
                <span className={"r-status-dot" + (followed.active ? " on" : "")} />
                {followed.active
                  ? `${intervalLabel(plan?.interval_minutes || 30)}检查（服务运行期间）`
                  : "已暂停，已有内容仍保留"}
                {" · "}
                {followed.last_status === "queued"
                  ? "排队中"
                  : followed.last_checked
                    ? `最近检查 ${when(followed.last_checked)}`
                    : "尚未检查"}
              </small>
            </div>
            <div className="r-follow-actions">
              <button
                className="r-button primary"
                disabled={
                  followPending(followed.id) ||
                  followBusy ||
                  !followed.active ||
                  !plan
                }
                onClick={() => void updateFollow(followed, "refresh")}
              >
                <Glyph name="refresh" size={15} />
                {followPending(followed.id) ? "检查中…" : "立即检查"}
              </button>
              <button
                className="r-button"
                disabled={followBusy}
                onClick={() =>
                  beginFollow(
                    followed.description ||
                      `我想持续了解「${followed.name}」的进展，请帮我制定追踪方案。`,
                    "",
                    followed.id,
                  )
                }
              >
                <Glyph name="edit" size={15} /> 编辑需求
              </button>
              {plan && (
                <button
                  className="r-button"
                  disabled={followBusy}
                  onClick={() => void updateFollow(followed, "pause")}
                >
                  <Glyph name={followed.active ? "pause" : "play"} size={15} />
                  {followed.active ? "暂停" : "恢复"}
                </button>
              )}
              <button
                className="r-button quiet danger"
                disabled={followBusy}
                onClick={() => void updateFollow(followed, "remove")}
              >
                取消追踪
              </button>
            </div>
          </header>
          {plan && (
            <details className="r-fold">
              <summary>已确认的追踪方案</summary>
              <div className="r-plan">
                <div>
                  <h4>重点关注</h4>
                  <ul>
                    {plan.focus.map((v, i) => (
                      <li key={i}>{v}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4>排除内容</h4>
                  {plan.exclude.length ? (
                    <ul>
                      {plan.exclude.map((v, i) => (
                        <li key={i}>{v}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="r-muted">无</p>
                  )}
                </div>
                <div className="wide">
                  <h4>筛选标准</h4>
                  <p>{plan.relevance_criteria}</p>
                </div>
                <div className="wide">
                  <h4>检索方向</h4>
                  {plan.searches.map((v, i) => (
                    <p key={i}>
                      <strong>{sourceName(v.source)}</strong> {v.purpose}
                      <code>{v.query}</code>
                    </p>
                  ))}
                </div>
              </div>
            </details>
          )}
          {followed.last_status === "partial" && (
            <p className="r-banner soft">
              已保留取得的线索，部分内容尚未整理。
              {followed.last_errors?.includes("daily_model_budget_reached")
                ? "今天的模型处理额度已用完。"
                : "稍后会继续检查。"}
            </p>
          )}
          {["failed", "cancelled"].includes(followed.last_status) && (
            <p className="r-banner soft">
              {followed.last_status === "cancelled"
                ? "本次检查已停止。"
                : "上次检查未完成。"}
              已有内容仍可阅读。
            </p>
          )}
          <header className="r-section-head">
            <h2>相关进展 · {followed.event_ids.length}</h2>
            {followed.unread_ids.length > 0 && (
              <button
                className="r-link"
                disabled={followBusy}
                onClick={() => void updateFollow(followed, "seen")}
              >
                全部标为已读
              </button>
            )}
          </header>
          {followingEvents.length ? (
            <div className="r-list-stories r-grid">
              {followingEvents.map((s) =>
                row(s, "normal", {
                  reason: followed.reasons?.[s.id],
                  unread: followed.unread_ids.includes(s.id),
                  list: followingEvents,
                }),
              )}
            </div>
          ) : (
            <Empty icon="clock" title="正在等待相关进展">
              <p>
                {plan
                  ? "候选内容需要符合你确认的关注重点与排除条件，整理判断后才会出现在这里。"
                  : "这是旧版关键词话题，点「编辑需求」升级为意图追踪。"}
              </p>
            </Empty>
          )}
          {followed.material_versions.length > 0 && (
            <details className="r-fold">
              <summary>
                已收集、待评估的线索 · {followed.material_versions.length}
              </summary>
              <ul className="r-plain-list">
                {archive
                  .filter((row) => followed.material_versions.includes(row.version))
                  .map((row) => (
                    <li key={row.version}>
                      <a href={row.url} target="_blank" rel="noreferrer">
                        {row.title} <Glyph name="external" size={13} />
                      </a>
                      <small>{statusLabel[row.status] || row.status}</small>
                    </li>
                  ))}
              </ul>
            </details>
          )}
        </section>
      </div>
    );
  }

  function savedPage() {
    if (!view) return null;
    const allSaved = view.saved_events || all.filter((e) => e.saved);
    return (
      <>
        {allSaved.length > 0 && (
          <TopicFilter topic={topic} setTopic={setTopic} counts={topicCounts(allSaved)} />
        )}
        {saved.length ? (
          <div className="r-list-stories r-grid">
            {saved.map((s) => row(s, "normal", { list: saved }))}
          </div>
        ) : (
          <Empty
            icon="bookmark"
            title={topic ? "这个方向没有收藏" : "把值得重读的内容留在这里"}
          >
            <p>点卡片上的书签图标收藏。收藏会保留当时的内容版本。</p>
            <div className="r-empty-actions">
              <button className="r-button" onClick={() => navigate("briefing")}>
                回到简报
              </button>
            </div>
          </Empty>
        )}
      </>
    );
  }

  function libraryPage() {
    if (!view) return null;
    const pendingStates = ["pending", "retrying"];
    const rows = archive.filter(
      (row: Archive) =>
        (libraryFilter === "all" ||
          (libraryFilter === "pending" && pendingStates.includes(row.status)) ||
          (libraryFilter === "failed" && row.status === "failed")) &&
        (!query ||
          (row.title + (row.summary || "") + row.source)
            .toLowerCase()
            .includes(query.toLowerCase())) &&
        (!topic ||
          all.some(
            (e) =>
              e.topic === topic &&
              e.timeline.some((t) => t.version === row.version),
          )),
    );
    const count = (f: (r: Archive) => boolean) => archive.filter(f).length;
    return (
      <>
        <div className="r-library-tools">
          <label className="r-inline-search">
            <Glyph name="search" size={16} />
            <input
              aria-label="筛选资料"
              placeholder="筛选标题、来源…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="r-segment" role="tablist" aria-label="整理状态">
            {(
              [
                ["all", "全部", archive.length],
                ["pending", "待整理", count((r) => pendingStates.includes(r.status))],
                ["failed", "失败", count((r) => r.status === "failed")],
              ] as const
            ).map(([id, label, n]) => (
              <button
                key={id}
                role="tab"
                aria-selected={libraryFilter === id}
                className={libraryFilter === id ? "active" : ""}
                onClick={() => setLibraryFilter(id)}
              >
                {label} <small>{n}</small>
              </button>
            ))}
          </div>
        </div>
        {rows.length ? (
          <ul className="r-library">
            {rows.map((row) => (
              <li key={row.version}>
                <div>
                  <a href={row.url} target="_blank" rel="noreferrer">
                    {row.title}
                    <Glyph name="external" size={13} />
                  </a>
                  {row.summary && <p>{row.summary}</p>}
                  <small>
                    {row.source} · {when(row.published_at, row.captured_at)}
                  </small>
                </div>
                <div className="r-library-side">
                  <span
                    className={"r-pill s-" + row.status}
                    title={
                      row.failure
                        ? `已尝试 ${row.failure.attempts} 次（${row.failure.code}）`
                        : undefined
                    }
                  >
                    {row.content_kind === "search_excerpt" && row.status === "pending"
                      ? "线索 · 正文待获取"
                      : statusLabel[row.status] || row.status}
                  </span>
                  {row.status === "failed" && !historical && (
                    <button className="r-link small" onClick={() => void retry(row.version)}>
                      重新整理
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Empty icon="book" title="没有符合条件的资料" />
        )}
      </>
    );
  }

  function storyPage() {
    if (!current)
      return (
        <Empty icon="compass" title="这条内容已不在当前列表中">
          <p>它可能已被合并到其他事件，或属于另一期简报。</p>
          <div className="r-empty-actions">
            <button className="r-button primary" onClick={closeStory}>
              返回{backLabel[from]}
            </button>
          </div>
        </Empty>
      );
    const story = current;
    return (
      <StoryReader
        key={story.id}
        story={story}
        view={view}
        historical={!!historical}
        prev={position.prev ? byId(position.prev) : undefined}
        next={position.next ? byId(position.next) : undefined}
        go={goStory}
        act={(kind) => void act(story, kind)}
        follow={() => followStory(story)}
        askFeedback={() => setFeedback(story)}
        undo={(a) => void undo(story, a)}
        regroup={(path, body, done) => void regroup(story, path, body, done)}
        loadRaw={() =>
          request<{
            title: string;
            text: string;
            url: string;
            captured_at: string;
          }>("/materials/" + story.version).catch((e) => {
            fail(e);
            throw e;
          })
        }
      />
    );
  }
  const followStory = (story: Story) =>
    beginFollow(story.object || story.title, story.object || "");

  /* ---------- right rail (wide screens) ---------- */

  const briefingCounts = topicCounts(all.filter((e) => e.qualified && !e.dismissed));
  const lastChecked = (view?.sources || [])
    .filter((s) => s.kind !== "search" && s.state.at)
    .map((s) => s.state.at!)
    .sort()
    .pop();

  const followCard = (
    <section className="r-card">
      <header className="r-card-head">
        <h2 className="r-card-title">追踪</h2>
        <button className="r-link small" onClick={() => beginFollow()}>
          <Glyph name="plus" size={14} /> 新增
        </button>
      </header>
      {follows.length ? (
        <div className="r-rail-list">
          {follows.slice(0, 6).map((f) => (
            <button
              key={f.id}
              onClick={() => {
                setSelectedFollow(f.id);
                navigate("following");
              }}
            >
              <span>
                <strong>{f.name}</strong>
                <small>
                  {!f.active
                    ? "已暂停"
                    : f.last_checked
                      ? `检查于 ${when(f.last_checked)}`
                      : "尚未检查"}
                </small>
              </span>
              {f.unread_ids.length > 0 && (
                <b aria-label={f.unread_ids.length + " 条新进展"}>
                  {f.unread_ids.length}
                </b>
              )}
            </button>
          ))}
        </div>
      ) : (
        <p className="r-card-text">
          用一句话描述想了解的事，确认方案后会定期帮你检查。
        </p>
      )}
    </section>
  );

  const recentSaved = saved.slice(0, 4);
  const savedCard = (
    <section className="r-card">
      <header className="r-card-head">
        <h2 className="r-card-title">最近收藏</h2>
        {savedCount > 0 && (
          <button className="r-link small" onClick={() => navigate("saved")}>
            全部 {savedCount}
          </button>
        )}
      </header>
      {recentSaved.length ? (
        <div className="r-rail-list">
          {recentSaved.map((s) => (
            <button key={s.id} onClick={() => open(s, recentSaved)}>
              <span>
                <strong className="r-clamp">{s.title}</strong>
                <small>
                  {s.source} · {when(s.published_at, s.captured_at)}
                </small>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="r-card-text">点卡片上的书签收藏，方便之后重读。</p>
      )}
    </section>
  );

  function rail() {
    if (!view) return null;
    if (page === "briefing")
      return (
        <>
          <section className="r-card">
            <h2 className="r-card-title">{historical ? "过去的简报" : today()}</h2>
            <div className="r-kpis">
              <div>
                <strong>{view.counts.eligible}</strong>
                <small>项进展</small>
              </div>
              <div>
                <strong>{!historical && baseline.current ? newSince : "–"}</strong>
                <small>上次后新增</small>
              </div>
              <div>
                <strong>{Math.max(1, Math.ceil(view.estimated_seconds / 60))}</strong>
                <small>分钟读完重点</small>
              </div>
            </div>
            <div className="r-card-foot">
              <span>{lastChecked ? `最近检查 ${when(lastChecked)}` : "尚未检查来源"}</span>
              <button className="r-link small" onClick={() => setSourcesOpen(true)}>
                来源 {okSources}/{fixedSources} 正常
              </button>
            </div>
          </section>
          <TopicCard topic={topic} setTopic={setTopic} counts={briefingCounts} />
          {followCard}
          {savedCard}
        </>
      );
    if (page === "discover")
      return (
        <>
          {!query.trim() && (
            <TopicCard topic={topic} setTopic={setTopic} counts={briefingCounts} />
          )}
          <section className="r-card">
            <h2 className="r-card-title">外部检索来源</h2>
            <div className="r-check-list">
              {(Object.entries(searchSources) as [SearchSource, string][]).map(
                ([id, label]) => (
                  <label key={id}>
                    <input
                      type="checkbox"
                      checked={channels.includes(id)}
                      onChange={(e) =>
                        setChannels(
                          e.target.checked
                            ? [...channels, id]
                            : channels.filter((key) => key !== id),
                        )
                      }
                    />
                    {label}
                  </label>
                ),
              )}
            </div>
            <p className="r-card-text">
              关键词只发给勾选的来源。搜索摘要先作为线索，取得原文后再整理。
            </p>
          </section>
          {followCard}
        </>
      );
    if (page === "saved") {
      const allSaved = view.saved_events || all.filter((e) => e.saved);
      return (
        <>
          {allSaved.length > 0 && (
            <TopicCard
              topic={topic}
              setTopic={setTopic}
              counts={topicCounts(allSaved)}
              title="收藏的方向"
            />
          )}
          {followCard}
        </>
      );
    }
    if (page === "library") {
      const fixed = view.sources.filter((s) => s.kind !== "search");
      const bad = fixed.filter((s) => s.state.status === "error").length;
      return (
        <>
          <section className="r-card">
            <h2 className="r-card-title">资料来源</h2>
            <div className="r-kpis">
              <div>
                <strong>{okSources}</strong>
                <small>正常</small>
              </div>
              <div>
                <strong>{bad}</strong>
                <small>暂不可用</small>
              </div>
              <div>
                <strong>{view.counts.pending}</strong>
                <small>待整理</small>
              </div>
            </div>
            <button className="r-button block" onClick={() => setSourcesOpen(true)}>
              查看来源状态
            </button>
          </section>
          <section className="r-card">
            <h2 className="r-card-title">资料库里有什么</h2>
            <p className="r-card-text">
              这里保存每次收取的原始材料，包括尚未整理、判断为与 AI
              无关或整理失败的条目。简报只展示整理后有依据的进展。
            </p>
          </section>
        </>
      );
    }
    return null;
  }

  /* ---------- shell ---------- */

  const subtitle =
    page === "briefing"
      ? [
          today(),
          view ? `${view.counts.eligible} 项进展` : "",
          !historical && baseline.current
            ? `上次打开后新增 ${newSince} 项`
            : "",
        ]
          .filter(Boolean)
          .join(" · ")
      : page === "following"
        ? `${follows.length} 个话题${unreadFollows ? ` · ${unreadFollows} 条新进展` : ""}`
        : page === "saved"
          ? `${savedCount} 条收藏`
          : page === "library"
            ? `${view?.counts.materials || 0} 条原始材料，含尚未整理的线索`
            : "先在已有内容中查找，没有再去外部来源";

  const railContent = rail();

  return (
    <div className="r-app">
      <aside className="r-nav">
        <a
          className="r-brand"
          aria-label="CFAW News · AI 事件简报"
          href="#briefing"
          onClick={(e) => {
            e.preventDefault();
            navigate("briefing");
          }}
        >
          <img className="r-brand-mark" src={brandMark} width={32} height={32} alt="" />
          <span>
            CFAW News<small>AI 事件简报</small>
          </span>
        </a>
        <nav aria-label="主要导航" className="r-nav-primary">
          {primaryNav.map(([id, icon, label]) => (
            <button
              key={id}
              className={navPage === id ? "selected" : ""}
              aria-current={navPage === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              <Glyph name={icon} size={19} />
              <span>{label}</span>
              {id === "following" && unreadFollows > 0 && <b>{unreadFollows}</b>}
              {id === "saved" && savedCount > 0 && <small>{savedCount}</small>}
            </button>
          ))}
        </nav>
        <div className="r-nav-secondary">{secondaryNav}</div>
        <small className="r-nav-foot">本机个人阅读空间 · 无站外通知</small>
      </aside>

      <div className={"r-main" + (page === "story" ? " is-reading" : "")}>
        {page === "story" ? (
          <header className="r-top r-top-reader">
            <button className="r-back" onClick={closeStory}>
              <Glyph name="back" size={18} />
              <span>返回{backLabel[from]}</span>
            </button>
            {position.index >= 0 && trail.length > 1 && (
              <div className="r-stepper">
                <span>
                  {position.index + 1} / {trail.length}
                </span>
                <button
                  className="r-icon"
                  aria-label="上一条"
                  title="上一条（K）"
                  disabled={!position.prev}
                  onClick={() => goStory(position.prev)}
                >
                  <Glyph name="back" size={17} />
                </button>
                <button
                  className="r-icon"
                  aria-label="下一条"
                  title="下一条（J）"
                  disabled={!position.next}
                  onClick={() => goStory(position.next)}
                >
                  <Glyph name="arrow" size={17} />
                </button>
              </div>
            )}
          </header>
        ) : (
          <header className="r-top">
            <div className="r-top-title">
              <h1>{pageTitle[page]}</h1>
              <p>{subtitle}</p>
            </div>
            <div className="r-top-actions">
              {page === "following" && follows.length > 0 && (
                <button className="r-button" onClick={() => beginFollow()}>
                  <Glyph name="plus" size={16} />
                  <span className="r-hide-sm">新增追踪</span>
                </button>
              )}
              {updateButton}
              <button
                className="r-icon r-menu-button"
                aria-label="更多"
                onClick={() => setMenuOpen(true)}
              >
                <Glyph name="menu" size={20} />
              </button>
            </div>
          </header>
        )}

        <div className="r-status-area">
          {error && (
            <div className="r-banner error" role="alert">
              <span>{error}</span>
              <button className="r-link" onClick={() => void load().catch(fail)}>
                重试
              </button>
              <button className="r-icon" aria-label="关闭" onClick={() => setError("")}>
                <Glyph name="close" size={15} />
              </button>
            </div>
          )}
          {historical && (
            <div className="r-banner info">
              <span>正在查看过去的简报，内容保持当时版本。</span>
              <button className="r-link" onClick={() => void load().catch(fail)}>
                回到当前
              </button>
            </div>
          )}
          {running && run && (
            <div className="r-progress" role="status">
              <span className="r-pulse" />
              <span>
                {run.kind === "following"
                  ? `正在追踪「${run.follow_name}」…`
                  : run.stage === "collecting"
                    ? `正在检查订阅来源 ${run.sources_done}/${fixedSources || "…"}`
                    : run.stage === "discovering"
                      ? `正在外部来源中查找「${run.query}」…`
                      : run.stage === "reading"
                        ? "正在补读原文…"
                        : run.stage === "publishing"
                          ? "正在生成简报…"
                          : `正在整理材料 ${run.analyzed + run.failed}/${run.total || "…"}`}
              </span>
              {run.stage === "understanding" && run.total ? (
                <span className="r-bar">
                  <i
                    style={{
                      width: `${Math.round(((run.analyzed + run.failed) / run.total) * 100)}%`,
                    }}
                  />
                </span>
              ) : null}
              <button className="r-link" onClick={() => void cancel(run.id)}>
                停止
              </button>
            </div>
          )}
          {queue.length > 0 && (
            <div className="r-queue" role="status" aria-label="排队中的任务">
              <small>排队</small>
              {queue.map((item) => (
                <span key={item.id}>
                  {queueLabel(item)}
                  <button
                    className="r-icon"
                    aria-label={"取消排队：" + queueLabel(item)}
                    onClick={() =>
                      void request("/cancel", {
                        method: "POST",
                        body: JSON.stringify({ id: item.id }),
                      })
                        .then(() => syncStatus())
                        .catch(fail)
                    }
                  >
                    <Glyph name="close" size={13} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {run &&
            run.state !== "running" &&
            run.kind === "refresh" &&
            (run.failed > 0 || run.errors.length > 0) && (
              <div className="r-banner soft">
                部分材料尚未整理完成，已有内容仍可阅读。
                {run.errors.includes("daily_model_budget_reached")
                  ? "今天的处理额度已用完。"
                  : "可稍后再次更新。"}
              </div>
            )}
        </div>

        <div className={"r-body" + (railContent ? " has-rail" : "")}>
          <main className="r-page">
            {!view ? (
              <div className="r-loading" aria-busy="true">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="r-skeleton" />
                ))}
              </div>
            ) : page === "briefing" ? (
              briefingPage()
            ) : page === "discover" ? (
              discoverPage()
            ) : page === "following" ? (
              followingPage()
            ) : page === "saved" ? (
              savedPage()
            ) : page === "story" ? (
              storyPage()
            ) : (
              libraryPage()
            )}
            {page !== "story" && (
              <footer className="r-footer">
                CFAW News · 关注变化，保留判断 ·{" "}
                <button className="r-link" onClick={() => setSourcesOpen(true)}>
                  来源与缺口
                </button>
              </footer>
            )}
          </main>
          {railContent && (
            <aside className="r-rail" aria-label="概览">
              {railContent}
            </aside>
          )}
        </div>
        {current && !historical && (
          <div className="r-reader-bar">
            <DetailActions
              story={current}
              act={(kind) => void act(current, kind)}
              follow={() => followStory(current)}
              askFeedback={() => setFeedback(current)}
            />
          </div>
        )}
      </div>

      <nav className="r-tabbar" aria-label="主要导航">
        {primaryNav.map(([id, icon, label]) => (
          <button
            key={id}
            className={navPage === id ? "selected" : ""}
            aria-current={navPage === id ? "page" : undefined}
            onClick={() => navigate(id)}
          >
            <span>
              <Glyph name={icon} size={21} />
              {id === "following" && unreadFollows > 0 && <b />}
            </span>
            {label}
          </button>
        ))}
      </nav>

      {notice && (
        <Toast
          message={notice.text}
          action={notice.action}
          dismiss={() => setNotice(null)}
        />
      )}

      {menuOpen && (
        <Sheet title="更多" close={() => setMenuOpen(false)}>
          <div className="r-menu">{secondaryNav}</div>
        </Sheet>
      )}

      {followForm && (
        <Sheet
          title={followForm.follow_id ? "编辑追踪需求" : "新增追踪"}
          close={() => setFollowForm(null)}
          variant="wide"
        >
          <FollowIntentForm
            initialDescription={followForm.description}
            followId={followForm.follow_id}
            onConfirmed={confirmedFollow}
          />
        </Sheet>
      )}

      {feedback && (
        <Sheet title="减少这类内容" close={() => setFeedback(null)}>
          <p className="r-sheet-lead">「{feedback.title}」哪里不合适？</p>
          <FeedbackChoices pick={(kind) => void act(feedback, kind)} />
        </Sheet>
      )}

      {history && (
        <Sheet title="过去的简报" close={() => setHistory(null)}>
          {history.length ? (
            <div className="r-choices">
              {history.map((row) => (
                <button
                  key={row.id}
                  onClick={() =>
                    void request<View>("/snapshots/" + row.id)
                      .then((value) => {
                        setView(value);
                        setHistorical(row.id);
                        setPage("briefing");
                        window.location.hash = "briefing";
                        setHistory(null);
                      })
                      .catch(fail)
                  }
                >
                  {when(row.created_at)}
                  <Glyph name="arrow" size={15} />
                </button>
              ))}
            </div>
          ) : (
            <p className="r-sheet-lead">完成一次更新后，这里会保留当时的简报。</p>
          )}
        </Sheet>
      )}

      {settings && (
        <Sheet
          title="阅读偏好"
          close={() => setSettings(false)}
          footer={
            prefs ? (
              <button
                className="r-button primary block"
                disabled={!prefs.topics.length}
                onClick={() => void savePrefs()}
              >
                保存
              </button>
            ) : undefined
          }
        >
          {prefs ? (
            <form
              className="r-prefs"
              onSubmit={(e) => {
                e.preventDefault();
                void savePrefs();
              }}
            >
              <fieldset>
                <legend>想多看哪些方向</legend>
                <div className="r-toggle-grid">
                  {(Object.entries(topics) as [Topic, string][]).map(([id, label]) => (
                    <label key={id} className={prefs.topics.includes(id) ? "on" : ""}>
                      <input
                        type="checkbox"
                        checked={prefs.topics.includes(id)}
                        onChange={(e) =>
                          setPrefs({
                            ...prefs,
                            topics: e.target.checked
                              ? [...prefs.topics, id]
                              : prefs.topics.filter((t) => t !== id),
                          })
                        }
                      />
                      <i className={"r-dot t-" + id} />
                      {label}
                    </label>
                  ))}
                </div>
                {!prefs.topics.length ? (
                  <p role="alert" className="r-error-text">至少选择一个方向。</p>
                ) : (
                  <p className="r-muted">未选的方向仍可在「搜索」中浏览。</p>
                )}
              </fieldset>
              <fieldset>
                <legend>内容深度</legend>
                <div className="r-segment">
                  {(
                    [
                      ["overview", "快速了解"],
                      ["balanced", "均衡"],
                      ["technical", "技术细节"],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      type="button"
                      key={id}
                      className={prefs.depth === id ? "active" : ""}
                      aria-pressed={prefs.depth === id}
                      onClick={() => setPrefs({ ...prefs, depth: id })}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend>每次想读多久</legend>
                <div className="r-segment">
                  {([3, 7, 15] as const).map((value) => (
                    <button
                      type="button"
                      key={value}
                      className={prefs.budget_minutes === value ? "active" : ""}
                      aria-pressed={prefs.budget_minutes === value}
                      onClick={() => setPrefs({ ...prefs, budget_minutes: value })}
                    >
                      {value} 分钟
                    </button>
                  ))}
                </div>
                <p className="r-muted">用于决定「重点」放几条，不代表实际阅读速度。</p>
              </fieldset>
              <label className="r-switch">
                <input
                  type="checkbox"
                  checked={prefs.exploration}
                  onChange={(e) => setPrefs({ ...prefs, exploration: e.target.checked })}
                />
                <span>
                  <strong>留一点空间给意外发现</strong>
                  <small>在「前沿速览」里放入偏好之外的新方向</small>
                </span>
              </label>
            </form>
          ) : (
            <p className="r-sheet-lead">正在读取偏好，请稍后重试。</p>
          )}
        </Sheet>
      )}

      {sourcesOpen && (
        <Sheet title="来源状态" close={() => setSourcesOpen(false)} variant="wide">
          <SourcesPanel view={view} />
        </Sheet>
      )}
    </div>
  );
}

function SourcesPanel({ view }: { view: View | null }) {
  const [filter, setFilter] = useState<"all" | "error" | "search">("all");
  const sources = view?.sources || [];
  const fixed = sources.filter((s) => s.kind !== "search");
  const rows = sources.filter((s) =>
    filter === "search"
      ? s.kind === "search"
      : filter === "error"
        ? s.kind !== "search" && s.state.status === "error"
        : s.kind !== "search",
  );
  const ok = fixed.filter((s) => s.state.status === "ok").length;
  const bad = fixed.filter((s) => s.state.status === "error").length;
  return (
    <div className="r-sources">
      <div className="r-stats">
        <div>
          <strong>{ok}</strong>
          <small>正常</small>
        </div>
        <div>
          <strong>{bad}</strong>
          <small>暂不可用</small>
        </div>
        <div>
          <strong>{fixed.length - ok - bad}</strong>
          <small>无结果 / 未检查</small>
        </div>
        {view?.usage && (
          <div>
            <strong>{view.usage.requests_today}</strong>
            <small>今日模型调用 · {view.usage.tokens_today.toLocaleString()} Token</small>
          </div>
        )}
      </div>
      <p className="r-muted">
        显示本机最近一次检查的结果；来源配置不代表持续覆盖，单个来源失败时保留已有资料。
        {view?.usage &&
          (view.usage.request_limit === null && view.usage.token_limit === null
            ? "AI 处理未设每日上限。"
            : "AI 处理使用本机配置的每日额度。")}
      </p>
      <div className="r-segment">
        {(
          [
            ["all", `订阅来源 ${fixed.length}`],
            ["error", `不可用 ${bad}`],
            ["search", `主动检索 ${sources.length - fixed.length}`],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className={filter === id ? "active" : ""}
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <ul className="r-source-list">
        {rows.map((s) => (
          <li key={s.id}>
            <span className={"r-status-dot s-" + s.state.status} />
            <div>
              <a href={s.url} target="_blank" rel="noreferrer">
                {s.name}
              </a>
              <small>
                {s.kind === "search"
                  ? s.description || "主动检索"
                  : `${sourceRole[s.role] || "公开来源"} · ${sourceKind[s.kind] || "订阅来源"}${s.priority === 0 ? " · 核心" : ""}`}
              </small>
            </div>
            <div className="r-source-state">
              <span>{sourceState[s.state.status] || "尚未检查"}</span>
              <small>
                {s.state.last_success
                  ? "成功于 " + when(s.state.last_success)
                  : "尚无成功记录"}
                {s.state.count !== undefined && s.state.status !== "error"
                  ? ` · ${s.state.count} 条`
                  : ""}
                {s.state.http_status ? ` · HTTP ${s.state.http_status}` : ""}
              </small>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
