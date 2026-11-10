import { useCallback, useEffect, useRef, useState } from "react";
import { searchSources, sourceName, type SearchSource } from "./searchSources";
import FollowIntentForm, {
  intervalLabel,
  type TrackingPlan,
} from "./FollowIntentForm";

import {
  actionLabel,
  evidence,
  feedbackNotice,
  followSeed,
  pageFromHash,
  queueLabel,
  sections,
  statusLabel,
  topics,
  when,
} from "./reader/logic";
import type {
  Action,
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
      typeof value.detail === "string"
        ? value.detail
        : "暂时无法完成，请重试。",
    );
  return value;
}

function Glyph({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    follow: "M12 21s-9-5.5-9-12a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6.5-9 12-9 12Z",
    home: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
    compass: "m16 8-3 5-5 3 3-5Z M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    book: "M12 6c-3-3-7-3-10-2v15c4-1 7-1 10 2 3-3 6-3 10-2V4c-3-1-7-1-10 2v15",
    refresh: "M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 14 6 M18 18A8 8 0 0 1 4 12",
    search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    arrow: "M5 12h14 m-6-6 6 6-6 6",
    close: "m6 6 12 12 M6 18 18 6",
    settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
    bookmark: "M6 3h12v18l-6-4-6 4Z",
    check: "m5 12 4 4 10-10",
    external: "M14 3h7v7 m0-7-11 11 M10 3H3v18h18v-7",
    clock: "M12 7v5l4 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.compass} />
    </svg>
  );
}

function Dialog({
  title,
  close,
  children,
  wide = false,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className={"reader-dialog" + (wide ? " wide" : "")}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <header>
        <span>{title}</span>
        <button className="r-icon" aria-label="关闭" onClick={close}>
          <Glyph name="close" />
        </button>
      </header>
      {children}
    </dialog>
  );
}

function Exposure({
  story,
  send,
  children,
  onOpen,
}: {
  story: Story;
  send: (s: Story, kind: string) => Promise<void>;
  children: React.ReactNode;
  onOpen?: () => void;
}) {
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
  return (
    <article
      ref={ref}
      aria-label={story.title}
      onClick={(event) => {
        if (
          !(event.target as HTMLElement).closest(
            "button, a, input, select, textarea",
          ) &&
          !window.getSelection()?.toString()
        )
          onOpen?.();
      }}
      className={"r-card" + (story.protected ? " important" : "")}
    >
      {children}
    </article>
  );
}

export default function ReaderApp() {
  const [view, setView] = useState<View | null>(null);
  const [page, setPage] = useState<Page>(currentPage);
  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [queue, setQueue] = useState<Run[]>([]);
  const [detail, setDetail] = useState<Story | null>(null);
  const [settings, setSettings] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [feedback, setFeedback] = useState<Story | null>(null);
  const [followingTab, setFollowingTab] = useState<"topics" | "saved">(
    "topics",
  );
  const [selectedFollow, setSelectedFollow] = useState("");
  const [followForm, setFollowForm] = useState<{
    description: string;
    follow_id?: string;
  } | null>(null);
  const [followBusy, setFollowBusy] = useState(false);
  const [discoveryQuery, setDiscoveryQuery] = useState("");
  const [discoveryChannels, setDiscoveryChannels] = useState<SearchSource[]>([
    "web",
    "arxiv",
    "github",
  ]);
  const [raw, setRaw] = useState<{
    title: string;
    text: string;
    url: string;
    captured_at: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<
    { id: string; created_at: string }[] | null
  >(null);
  const [historical, setHistorical] = useState<string | null>(null);
  const visited = useRef(false);
  const baseline = useRef<string | null | undefined>(undefined);
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
    void load().catch((e) => setError(e.message));
  }, [load]);
  useEffect(() => {
    const sync = () => setPage(currentPage());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);
  useEffect(() => {
    if (page !== "following" || historical) return;
    const timer = setInterval(
      () => void load().catch((e) => setError(e.message)),
      30000,
    );
    return () => clearInterval(timer);
  }, [page, historical, load]);
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
          if (
            result.run?.state !== "running" ||
            result.run?.id !== watched
          )
            void load().catch((e) => setError(e.message));
        })
        .catch((e) => {
          if (!stopped) setError(e.message);
        });
    }, 1500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [run?.state, run?.id, queue.length, load]);
  async function syncStatus() {
    const result = await request<{ run: Run | null; queue: Run[] }>(
      "/status",
    );
    setRun(result.run);
    setQueue(result.queue || []);
  }
  /** Show a started job's progress, or say where a queued one waits. */
  function accept(next: Run, startedNotice = "") {
    if (next.state === "queued") {
      setNotice("已加入队列，当前任务完成后自动开始。");
      void syncStatus().catch((e) => setError(e.message));
    } else {
      setRun(next);
      if (startedNotice) setNotice(startedNotice);
    }
  }
  async function retry(version: string) {
    try {
      setView(
        await request<View>(`/materials/${version}/retry`, { method: "POST" }),
      );
      setNotice("已清除失败记录，下次更新时会重新整理。");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const send = useCallback(
    async (story: Story, kind: string, retracts?: string) => {
      await request("/interactions", {
        method: "POST",
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          event_id: story.id,
          version: story.version,
          kind,
          retracts: retracts || null,
        }),
      });
    },
    [],
  );
  async function act(story: Story, kind: string) {
    try {
      if (kind === "saved" && story.saved) {
        for (const action of story.actions.filter((a) => a.kind === "saved"))
          await send(
            { ...story, version: action.version },
            "retract",
            action.request_id,
          );
      } else await send(story, kind);
      setNotice(feedbackNotice(kind, story.saved));
      setFeedback(null);
      const updated = await load();
      setDetail((d) =>
        d?.id === story.id
          ? [...updated.events, ...(updated.saved_events || [])].find(
              (e) => e.id === story.id,
            ) || d
          : d,
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function undo(story: Story, action: Action) {
    try {
      await send(
        { ...story, version: action.version },
        "retract",
        action.request_id,
      );
      setNotice("已撤回这条反馈。");
      await load();
      setDetail(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function open(story: Story) {
    setDetail(story);
    setRaw(null);
    if (!historical)
      void send(story, "opened").catch((e) => setError(e.message));
  }
  async function supplement() {
    if (discoveryQuery.trim().length < 2 || !discoveryChannels.length) return;
    try {
      accept(
        await request<Run>("/discover", {
          method: "POST",
          body: JSON.stringify({
            query: discoveryQuery.trim(),
            channels: discoveryChannels,
          }),
        }),
        `正在从所选来源搜索「${discoveryQuery.trim()}」，结果会保存在本机。`,
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function refresh() {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      accept(
        await request<Run>("/refresh", {
          method: "POST",
          body: JSON.stringify({ limit_per_source: 10, analyze_limit: 24 }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
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
      setNotice("阅读偏好已更新。");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function navigate(next: Page, tab?: "topics" | "saved") {
    setPage(next);
    window.location.hash = next;
    setTopic("");
    setQuery("");
    if (tab) setFollowingTab(tab);
    if (historical) void load().catch((e) => setError(e.message));
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
    setDetail(null);
    navigate("following", "topics");
    setNotice("追踪方案已确认，后续按这份意图执行。");
  }
  async function updateFollow(
    follow: Follow,
    action: "pause" | "remove" | "seen" | "refresh",
  ) {
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
      }
    } catch (error) {
      setError((error as Error).message);
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
    events,
    focus,
    radar,
    discover,
    follows,
    followed,
    saved,
    followingEvents,
    okSources,
  } = sections(view, topic, query, selectedFollow);

  function card(story: Story, index = 0) {
    const intentReason =
      page === "following" && followingTab === "topics"
        ? followed?.reasons?.[story.id]
        : undefined;
    return (
      <Exposure
        key={story.id + story.version}
        story={story}
        send={historical ? async () => {} : send}
        onOpen={() => open(story)}
      >
        <div className="r-card-meta">
          <span className={"r-topic topic-" + story.topic}>
            {story.topic_label}
          </span>
          {story.protected && (
            <span className="r-correction">
              重要{actionLabel[story.action]}
            </span>
          )}
          {story.policy_stale && (
            <span className="r-stale" title="整理规则已更新，这条会按新规则重新整理">
              按旧版规则整理
            </span>
          )}
          <span className="r-card-time">{when(story.published_at)}</span>
          {page === "following" &&
            followingTab === "topics" &&
            followed?.unread_ids.includes(story.id) && (
              <span className="r-unread">新进展</span>
            )}
        </div>
        <button className="r-card-title" onClick={() => open(story)}>
          <h3>{story.title}</h3>
        </button>
        <p className="r-summary">{story.summary}</p>
        {(story.reason || intentReason) && (
          <div className="r-reason">
            <span>{intentReason ? "为什么与你有关" : "阅读价值"}</span>
            {intentReason || story.reason}
          </div>
        )}
        <div className="r-card-footer">
          <span>
            {story.source}
            {story.source_count > 1 && (
              <small> 等 {story.source_count} 个来源</small>
            )}
          </span>
          <span className="r-evidence">
            {evidence(story.evidence, story.source_role, story.content_kind)}
          </span>
        </div>
        <div className="r-card-actions">
          <button onClick={() => open(story)}>
            展开依据 <Glyph name="arrow" size={15} />
          </button>
          {!historical && (
            <div>
              <button
                className={"r-save-button " + (story.saved ? "active" : "")}
                aria-label={
                  (story.saved ? "取消收藏：" : "收藏：") + story.title
                }
                aria-pressed={story.saved}
                onClick={() => void act(story, "saved")}
              >
                <Glyph name="bookmark" size={16} />
                <span>{story.saved ? "已收藏" : "收藏"}</span>
              </button>
              <button
                aria-label={"反馈：" + story.title}
                onClick={() => setFeedback(story)}
              >
                ···
              </button>
            </div>
          )}
        </div>
        {index === 0 && (
          <span className="r-card-corner" aria-hidden="true">
            ↗
          </span>
        )}
      </Exposure>
    );
  }

  return (
    <div className="reader-shell">
      <aside className="r-sidebar">
        <a
          className="r-brand"
          href="#briefing"
          onClick={() => {
            navigate("briefing");
          }}
        >
          <span className="r-brand-mark">
            c<span>·</span>
          </span>
          <span>
            CFAW<span>AI INTELLIGENCE</span>
          </span>
        </a>
        <div className="r-sidebar-label">你的信息空间</div>
        <nav aria-label="主要导航">
          {(
            [
              ["briefing", "home", "我的简报"],
              ["discover", "compass", "发现"],
              ["following", "follow", "关注"],
              ["library", "book", "资料库"],
            ] as [Page, string, string][]
          ).map(([id, icon, label]) => (
            <button
              key={id}
              className={page === id ? "selected" : ""}
              aria-current={page === id ? "page" : undefined}
              onClick={() => {
                navigate(id);
              }}
            >
              <Glyph name={icon} />
              <span>{label}</span>
              {page === id && <i />}
            </button>
          ))}
        </nav>
        <div className="r-sidebar-note">
          <span className="r-note-line" />
          <p>
            少一些噪声，
            <br />
            多一些值得知道的变化。
          </p>
        </div>
        <div className="r-sidebar-bottom">
          <button onClick={() => setSourcesOpen(true)}>
            <span className={"r-dot " + (okSources ? "ok" : "")} />
            <span>来源与覆盖</span>
            <small>
              {okSources}/{view?.sources.length || 12}
            </small>
          </button>
          <button
            onClick={() => {
              setPrefs(view?.preferences || null);
              setSettings(true);
            }}
          >
            <Glyph name="settings" size={17} />
            <span>阅读偏好</span>
          </button>
          <small className="r-local">本机个人阅读空间</small>
        </div>
      </aside>

      <main className="r-main">
        <header className="r-topbar">
          <span>
            AI BRIEFING <i>/</i>{" "}
            {page === "briefing"
              ? "我的简报"
              : page === "discover"
                ? "发现"
                : page === "following"
                  ? "关注"
                  : "资料库"}
          </span>
          <div>
            <span className="r-today">
              {new Intl.DateTimeFormat("zh-CN", {
                month: "long",
                day: "numeric",
                weekday: "long",
              }).format(new Date())}
            </span>
            <button
              className="r-icon"
              aria-label="过去的简报"
              onClick={() =>
                void request<{ id: string; created_at: string }[]>("/snapshots")
                  .then(setHistory)
                  .catch((e) => setError(e.message))
              }
            >
              <Glyph name="clock" size={16} />
            </button>
            <button
              className="r-icon"
              aria-label="阅读偏好"
              onClick={() => {
                setPrefs(view?.preferences || null);
                setSettings(true);
              }}
            >
              <Glyph name="settings" size={16} />
            </button>
            <button
              className="r-refresh"
              disabled={refreshRunning || refreshQueued || busy}
              onClick={() => void refresh()}
            >
              <Glyph name="refresh" size={16} />
              {refreshRunning ? "整理中…" : refreshQueued ? "已排队" : "更新情报"}
            </button>
          </div>
        </header>
        <div className="r-content">
          <section className="r-intro">
            <div>
              <div className="r-eyebrow">
                A LITTLE LESS NOISE. A LITTLE MORE SIGNAL.
              </div>
              <h1>
                {page === "briefing" ? (
                  <>
                    AI，值得知道的<span>变化。</span>
                  </>
                ) : page === "discover" ? (
                  <>
                    沿着好奇心，<span>发现。</span>
                  </>
                ) : page === "following" ? (
                  <>
                    感兴趣的事，<span>持续关注。</span>
                  </>
                ) : (
                  <>
                    原始材料，<span>有迹可循。</span>
                  </>
                )}
              </h1>
              <p>
                {page === "briefing"
                  ? "把发布、实测与观点分开，留下有依据、有增量的进展。"
                  : page === "discover"
                    ? "从模型到应用，从研究到实践，留一点空间给意外的发现。"
                    : page === "following"
                      ? "追踪想深入了解的话题，也把值得重读的内容留在这里。"
                      : "回到原始出处，检索背景与历史。"}
              </p>
            </div>
            <div className="r-issue">
              <span>PERSONAL EDITION</span>
              <strong>
                {String(
                  page === "following"
                    ? follows.length
                    : view?.counts.eligible || 0,
                ).padStart(2, "0")}
              </strong>
              <span>
                {page === "following" ? "个关注话题" : "项可阅读进展"}
              </span>
            </div>
          </section>
          {error && (
            <div className="r-alert" role="alert">
              {error}
              <button
                onClick={() => void load().catch((e) => setError(e.message))}
              >
                重新读取
              </button>
            </div>
          )}
          {notice && (
            <div className="r-notice" role="status">
              {notice}
              {notice.includes("已收藏") && (
                <button
                  className="r-text-button"
                  onClick={() => navigate("following", "saved")}
                >
                  查看收藏
                </button>
              )}
              <button aria-label="关闭提示" onClick={() => setNotice("")}>
                ×
              </button>
            </div>
          )}
          {historical && (
            <div className="r-notice">
              正在阅读保存的简报，内容保持当时版本。
              <button
                onClick={() => {
                  setHistorical(null);
                  void load().catch((e) => setError(e.message));
                }}
              >
                返回当前简报
              </button>
            </div>
          )}
          {!historical && baseline.current && page === "briefing" && (
            <p className="r-return-note">
              上次打开：{when(baseline.current)} ·{" "}
              {view?.events.filter(
                (e) =>
                  e.qualified &&
                  !e.known &&
                  new Date(e.captured_at) > new Date(baseline.current!),
              ).length || 0}{" "}
              项本次新发现
            </p>
          )}
          {running && (
            <div className="r-progress" role="status">
              <span className="r-pulse" />
              <span>
                {run.kind === "following"
                  ? `正在追踪「${run.follow_name}」…`
                  : run.stage === "collecting"
                    ? `正在检查订阅来源 ${run.sources_done}/12`
                    : run.stage === "discovering"
                      ? "正在查找所选来源的公开线索…"
                      : run.stage === "reading"
                        ? "正在补充原始材料…"
                        : `正在阅读原始材料 ${run.analyzed + run.failed}/${run.total || "…"}`}
              </span>
              <button
                onClick={() =>
                  void request("/cancel", {
                    method: "POST",
                    body: JSON.stringify({ id: run.id }),
                  })
                    .then(() => load())
                    .catch((e) => setError(e.message))
                }
              >
                停止本次更新
              </button>
            </div>
          )}
          {queue.length > 0 && (
            <div className="r-queue" role="status" aria-label="排队中的任务">
              <span>排队中</span>
              {queue.map((item) => (
                <span key={item.id}>
                  {queueLabel(item)}
                  <button
                    aria-label={"取消排队：" + queueLabel(item)}
                    onClick={() =>
                      void request("/cancel", {
                        method: "POST",
                        body: JSON.stringify({ id: item.id }),
                      })
                        .then(() => syncStatus())
                        .catch((e) => setError(e.message))
                    }
                  >
                    取消
                  </button>
                </span>
              ))}
            </div>
          )}
          {run &&
            run.state !== "running" &&
            (run.failed > 0 || run.errors.length > 0) && (
              <div className="r-soft-warning">
                部分材料尚未整理完成，已有内容仍可阅读。
                {run.errors.includes("daily_model_budget_reached")
                  ? "今天的处理额度已用完。"
                  : "可稍后再次更新。"}
              </div>
            )}
          {page === "discover" && !historical && (
            <form
              className="r-discovery-cta"
              onSubmit={(event) => {
                event.preventDefault();
                void supplement();
              }}
            >
              <div>
                <h2>从更多公开来源发现新进展</h2>
                <p>查找官方发布、文档、模型卡、研究与开发者实践。</p>
              </div>
              <fieldset className="r-search-sources">
                <legend>选择检索来源</legend>
                {Object.entries(searchSources).map(([id, label]) => (
                  <label key={id}>
                    <input
                      type="checkbox"
                      checked={discoveryChannels.includes(id as SearchSource)}
                      onChange={(e) =>
                        setDiscoveryChannels(
                          e.target.checked
                            ? [...discoveryChannels, id as SearchSource]
                            : discoveryChannels.filter((key) => key !== id),
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </fieldset>
              <label className="r-discovery-input">
                <span>外部检索关键词</span>
                <input
                  aria-label="外部检索关键词"
                  placeholder="例如：LLM evaluation、robot learning"
                  value={discoveryQuery}
                  onChange={(event) => setDiscoveryQuery(event.target.value)}
                  minLength={2}
                  maxLength={80}
                  required
                />
              </label>
              <button
                className="r-primary"
                type="submit"
                disabled={
                  discoveryQuery.trim().length < 2 ||
                  !discoveryChannels.length
                }
              >
                搜索所选来源 <Glyph name="search" size={16} />
              </button>
              <button
                type="button"
                className="r-text-button"
                onClick={() => beginFollow(discoveryQuery)}
              >
                让 AI 帮我追踪这个方向
              </button>
              <small>
                关键词只发送给勾选的来源。搜索摘要先作为线索，取得原文后再整理；下方搜索框只筛选已有内容。
                X、抖音、小红书当前支持公开网页索引，覆盖可能有限，尚未接入视频字幕。
              </small>
            </form>
          )}
          {page === "discover" &&
            run?.kind === "discovery" &&
            run.state !== "running" && (
              <section
                className="r-discovery-results"
                aria-label="本次外部搜索结果"
              >
                <h3>「{run.query}」的搜索结果</h3>
                <p>
                  {run.found || 0} 条资料线索，{run.analyzed} 条本次完成整理。
                  {run.errors.includes("source_unavailable")
                    ? "部分检索来源暂时不可用。"
                    : ""}
                  {run.found === 0
                    ? "可换用更具体的英文检索词再试。"
                    : "已有判断直接沿用，材料不足或未完成的条目保留为原始线索。"}
                </p>
                <ul>
                  {view?.archive
                    .filter((row) => run.result_versions?.includes(row.version))
                    .map((row) => {
                      const story = view.events.find((event) =>
                        event.timeline.some(
                          (item) => item.version === row.version,
                        ),
                      );
                      return (
                        <li key={row.version}>
                          {story ? (
                            <button onClick={() => open(story)}>
                              {row.title}
                            </button>
                          ) : (
                            <a href={row.url} target="_blank" rel="noreferrer">
                              {row.title} ↗
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
          {(page !== "following" ||
            followingTab === "saved" ||
            follows.length > 0) && (
            <div className="r-toolbar">
              <div className="r-topic-tabs" aria-label="AI 方向">
                <button
                  className={!topic ? "active" : ""}
                  onClick={() => setTopic("")}
                >
                  全部方向
                </button>
                {Object.entries(topics).map(([id, label]) => (
                  <button
                    key={id}
                    className={topic === id ? "active" : ""}
                    onClick={() => setTopic(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label className="r-search">
                <Glyph name="search" size={17} />
                <input
                  aria-label="搜索内容"
                  placeholder="筛选已有内容"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
            </div>
          )}

          {!view ? (
            <div className="r-empty">
              <span className="r-pulse" />
              <h2>正在打开你的阅读空间</h2>
            </div>
          ) : page === "briefing" ? (
            <>
              <div className="r-section-heading">
                <h2>
                  <span>01</span>重点情报
                </h2>
                <div>
                  <Glyph name="clock" size={15} />
                  <button
                    onClick={() => {
                      setPrefs(view.preferences);
                      setSettings(true);
                    }}
                  >
                    {view.preferences.budget_minutes} 分钟预算
                  </button>
                  <small>
                    本页估算 {Math.ceil(view.estimated_seconds / 60)} 分钟
                  </small>
                </div>
              </div>
              {focus.length ? (
                <div className="r-cards">{focus.map(card)}</div>
              ) : (
                <div className="r-empty">
                  <Glyph name="compass" size={36} />
                  <h2>
                    {query || topic
                      ? "这个范围暂时没有重点内容"
                      : view.counts.materials
                        ? "正在为有价值的信息留位置"
                        : "第一份简报，从好来源开始"}
                  </h2>
                  <p>
                    {query || topic
                      ? "可以切换方向，或到资料库搜索原始材料。"
                      : view.counts.pending
                        ? `已收取 ${view.counts.materials} 条材料，还有 ${view.counts.pending} 条等待整理。`
                        : "检查官方发布、研究与专业作者，再把有依据的变化整理给你。"}
                  </p>
                  {!running && (
                    <button
                      className="r-primary"
                      onClick={() => void refresh()}
                    >
                      更新情报 <Glyph name="arrow" size={17} />
                    </button>
                  )}
                  <button
                    className="r-text-button"
                    onClick={() => setPage("library")}
                  >
                    浏览原始资料
                  </button>
                </div>
              )}
              {radar.length > 0 && (
                <>
                  <div className="r-section-heading">
                    <h2>
                      <span>02</span>前沿速览
                    </h2>
                    <small>给值得留意的新方向一点空间</small>
                  </div>
                  <div className="r-radar">
                    {radar.map((story, index) => (
                      <button key={story.id} onClick={() => open(story)}>
                        <span className="r-radar-number">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <div>
                          <span className={"r-topic topic-" + story.topic}>
                            {story.topic_label}
                          </span>
                          <h3>{story.title}</h3>
                          <p>{story.summary}</p>
                          <small>
                            {story.source} ·{" "}
                            {evidence(
                              story.evidence,
                              story.source_role,
                              story.content_kind,
                            )}
                          </small>
                        </div>
                        <Glyph name="arrow" size={19} />
                      </button>
                    ))}
                  </div>
                </>
              )}
            </>
          ) : page === "discover" ? (
            <>
              <div className="r-section-heading">
                <h2>
                  <span>↗</span>值得探索
                </h2>
                <small>{discover.length} 项 · 以内容价值整理</small>
              </div>
              <div className="r-cards">{discover.map(card)}</div>
              {!discover.length && (
                <div className="r-empty">
                  <h2>这个方向暂时没有合适的内容</h2>
                  <p>可以调整筛选条件，或更新来源。</p>
                </div>
              )}
            </>
          ) : page === "following" ? (
            <>
              <div className="r-follow-heading">
                <div className="r-follow-tabs" aria-label="关注内容">
                  <button
                    className={followingTab === "topics" ? "active" : ""}
                    onClick={() => {
                      setFollowingTab("topics");
                      setQuery("");
                      setTopic("");
                    }}
                  >
                    <Glyph name="follow" size={17} />
                    话题追踪 <span>{follows.length}</span>
                  </button>
                  <button
                    className={followingTab === "saved" ? "active" : ""}
                    onClick={() => {
                      setFollowingTab("saved");
                      setQuery("");
                      setTopic("");
                    }}
                  >
                    <Glyph name="bookmark" size={17} />
                    我的收藏{" "}
                    <span>
                      {view.saved_events?.length ??
                        view.events.filter((e) => e.saved).length}
                    </span>
                  </button>
                </div>
                <button className="r-primary" onClick={() => beginFollow()}>
                  ＋ 新增关注
                </button>
              </div>
              {followingTab === "saved" ? (
                saved.length ? (
                  <div className="r-cards">{saved.map(card)}</div>
                ) : (
                  <div className="r-empty">
                    <Glyph name="bookmark" size={34} />
                    <h2>
                      {query || topic
                        ? "这个范围没有收藏"
                        : "把值得重读的内容留在这里"}
                    </h2>
                    <p>
                      点击情报卡片上的“收藏”，就能在这里随时找到。收藏会保留当时的内容版本。
                    </p>
                    <button
                      className="r-primary"
                      onClick={() => navigate("discover")}
                    >
                      去发现内容
                    </button>
                  </div>
                )
              ) : follows.length && followed ? (
                <div className="r-follow-layout">
                  <aside className="r-follow-list" aria-label="已关注的话题">
                    {follows.map((follow) => (
                      <button
                        key={follow.id}
                        className={follow.id === followed.id ? "active" : ""}
                        onClick={() => {
                          setSelectedFollow(follow.id);
                          setQuery("");
                          setTopic("");
                        }}
                      >
                        <strong>{follow.name}</strong>
                        <span>
                          {follow.active ? "持续追踪中" : "已暂停"}
                          {follow.unread_ids.length > 0 && (
                            <b>{follow.unread_ids.length} 条新进展</b>
                          )}
                        </span>
                      </button>
                    ))}
                  </aside>
                  <section className="r-follow-feed">
                    <header className="r-follow-feed-header">
                      <div>
                        <h2>{followed.name}</h2>
                        <p>
                          {followed.intent_plan?.intent_summary ||
                            `旧版关键词话题：${followed.query}，可重新描述需求升级。`}
                        </p>
                        <small>
                          {followed.active
                            ? `服务运行时${intervalLabel(followed.intent_plan?.interval_minutes || 30)}检查`
                            : "自动追踪已暂停，已有内容仍保留"}{" "}
                          ·{" "}
                          {followed.last_status === "queued"
                            ? "已排队，等待当前任务完成"
                            : followed.last_checked
                              ? `最近检查 ${when(followed.last_checked)}`
                              : "尚未执行外部检索"}
                        </small>
                      </div>
                      <div className="r-follow-controls">
                        <button
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
                          重新描述需求
                        </button>
                        <button
                          className="r-primary"
                          disabled={
                            followPending(followed.id) ||
                            followBusy ||
                            !followed.active ||
                            !followed.intent_plan
                          }
                          onClick={() => void updateFollow(followed, "refresh")}
                        >
                          立即追踪
                        </button>
                        <button
                          disabled={followBusy || !followed.intent_plan}
                          onClick={() => void updateFollow(followed, "pause")}
                        >
                          {!followed.intent_plan
                            ? "请先确认追踪方案"
                            : followed.active
                              ? "暂停追踪"
                              : "恢复追踪"}
                        </button>
                        <button
                          disabled={followBusy}
                          onClick={() => void updateFollow(followed, "remove")}
                        >
                          取消关注
                        </button>
                      </div>
                    </header>
                    {followed.intent_plan && (
                      <details className="r-intent-saved-plan">
                        <summary>查看已确认的追踪方案</summary>
                        <h3>重点关注</h3>
                        <ul>
                          {followed.intent_plan.focus.map((value, index) => (
                            <li key={index}>{value}</li>
                          ))}
                        </ul>
                        <h3>排除内容</h3>
                        <ul>
                          {followed.intent_plan.exclude.map((value, index) => (
                            <li key={index}>{value}</li>
                          ))}
                        </ul>
                        <p>{followed.intent_plan.relevance_criteria}</p>
                        {followed.intent_plan.searches.map((value, index) => (
                          <p key={index}>
                            <strong>{sourceName(value.source)}：</strong>
                            {value.purpose}
                            <small>{value.query}</small>
                          </p>
                        ))}
                      </details>
                    )}
                    {followed.last_status === "partial" && (
                      <p className="r-soft-warning">
                        已保留取得的线索，部分内容尚未整理。
                        {followed.last_errors?.includes(
                          "daily_model_budget_reached",
                        )
                          ? "今天的模型处理额度已用完。"
                          : "稍后会继续检查。"}
                      </p>
                    )}
                    {["failed", "cancelled"].includes(followed.last_status) && (
                      <p className="r-soft-warning">
                        {followed.last_status === "cancelled"
                          ? "本次检查已停止。"
                          : "上次检查未完成。"}
                        已有内容仍可阅读。
                      </p>
                    )}
                    <div className="r-section-heading">
                      <h3>{followed.event_ids.length} 项相关进展</h3>
                      <button
                        disabled={!followed.unread_ids.length || followBusy}
                        onClick={() => void updateFollow(followed, "seen")}
                      >
                        标记本话题已浏览
                      </button>
                    </div>
                    <div className="r-cards">{followingEvents.map(card)}</div>
                    {!followingEvents.length && (
                      <div className="r-empty">
                        <h3>
                          {query || topic
                            ? "当前筛选下没有相关进展"
                            : "正在等待有内容的新进展"}
                        </h3>
                        <p>
                          {followed.intent_plan
                            ? "候选需要符合你确认的关注重点与排除条件，整理并判断后才会出现在这里。你可以重新描述需求来调整方案。"
                            : "这是旧版关键词话题，可点击重新描述需求，升级为意图追踪。"}
                        </p>
                      </div>
                    )}
                    {followed.material_versions.length > 0 && (
                      <details className="r-follow-materials">
                        <summary>
                          已收集、待评估的资料线索 ·{" "}
                          {followed.material_versions.length}
                        </summary>
                        <ul>
                          {view.archive
                            .filter((row) =>
                              followed.material_versions.includes(row.version),
                            )
                            .map((row) => (
                              <li key={row.version}>
                                <a
                                  href={row.url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {row.title} ↗
                                </a>
                                <small>
                                  {statusLabel[row.status] || row.status}
                                </small>
                              </li>
                            ))}
                        </ul>
                      </details>
                    )}
                  </section>
                </div>
              ) : (
                <div className="r-empty r-follow-empty">
                  <Glyph name="follow" size={38} />
                  <h2>描述想了解的事，让 AI 帮你追踪</h2>
                  <p>
                    不用自己整理搜索词。说清目标、场景和偏好，先核对 AI
                    理解的意图与搜索方案，确认后持续追踪。
                  </p>
                  <button className="r-primary" onClick={() => beginFollow()}>
                    新增第一个关注
                  </button>
                  <div className="r-follow-suggestions">
                    {[
                      ["Agent 与开发", "AI agents, 智能体"],
                      ["具身智能", "embodied AI, robotics"],
                      ["大模型推理", "LLM inference, 推理优化"],
                    ].map(([name, query]) => (
                      <button
                        key={name}
                        onClick={() => beginFollow(name, query)}
                      >
                        {name} ＋
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="r-section-heading">
                <h2>
                  <span>≡</span>
                  原始资料
                </h2>
              </div>
              {
                <div className="r-library">
                  {view.archive
                    .filter(
                      (row) =>
                        (!query ||
                          (row.title + (row.summary || "") + row.source)
                            .toLowerCase()
                            .includes(query.toLowerCase())) &&
                        (!topic ||
                          view.events.some(
                            (e) =>
                              e.topic === topic &&
                              e.timeline.some((t) => t.version === row.version),
                          )),
                    )
                    .map((row) => (
                      <article key={row.version}>
                        <div>
                          <small>
                            {row.source} · {when(row.published_at)}
                          </small>
                          <a href={row.url} target="_blank" rel="noreferrer">
                            {row.title}
                            <Glyph name="external" size={16} />
                          </a>
                          {row.summary && <p>{row.summary}</p>}
                        </div>
                        <div className="r-library-side">
                          <span
                            className={"r-library-status status-" + row.status}
                            title={
                              row.failure
                                ? `已尝试 ${row.failure.attempts} 次（${row.failure.code}）`
                                : undefined
                            }
                          >
                            {statusLabel[row.status] || row.status}
                          </span>
                          {row.status === "failed" && !historical && (
                            <button onClick={() => void retry(row.version)}>
                              重新整理
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                </div>
              }
            </>
          )}
          <footer className="r-footer">
            <span>
              CFAW NEWS <i>·</i> 关注变化，保留判断。
            </span>
            <span>
              {view?.counts.materials || 0} 条原始材料 ·{" "}
              <button onClick={() => setSourcesOpen(true)}>
                查看来源与缺口
              </button>
            </span>
          </footer>
        </div>
      </main>

      {followForm && (
        <Dialog
          title="描述需求，确认后追踪"
          close={() => setFollowForm(null)}
          wide
        >
          <FollowIntentForm
            initialDescription={followForm.description}
            followId={followForm.follow_id}
            onConfirmed={confirmedFollow}
          />
        </Dialog>
      )}
      {detail && (
        <Dialog
          title="事件与原始依据"
          close={() => {
            setDetail(null);
            setRaw(null);
          }}
          wide
        >
          <div className="r-detail">
            <div className="r-card-meta">
              <span className={"r-topic topic-" + detail.topic}>
                {detail.topic_label}
              </span>
              <span>
                {evidence(
                  detail.evidence,
                  detail.source_role,
                  detail.content_kind,
                )}
              </span>
              {detail.policy_stale && (
                <span className="r-stale">按旧版规则整理，待重新整理</span>
              )}
            </div>
            <h2>{detail.title}</h2>
            <p className="r-detail-summary">{detail.summary}</p>
            {detail.reason && (
              <div className="r-detail-reason">
                <strong>为什么值得读</strong>
                <p>{detail.reason}</p>
              </div>
            )}
            {detail.conditions.length > 0 && (
              <section>
                <h3>适用条件与测试范围</h3>
                {detail.conditions.map((c, i) => (
                  <blockquote key={i}>{c}</blockquote>
                ))}
              </section>
            )}
            <section>
              <h3>
                {detail.content_kind === "benchmark_snapshot"
                  ? "榜单数据中的依据"
                  : detail.content_kind === "index_abstract"
                  ? "索引摘要支持的主张"
                  : detail.content_kind === "community_post"
                    ? "社区发言中的主张"
                    : "原文支持的主张"}
              </h3>
              {detail.claims.map((c, i) => (
                <div className="r-claim" key={i}>
                  <p>{c.statement}</p>
                  <blockquote>{c.quote}</blockquote>
                </div>
              ))}
              <a
                className="r-source-link"
                href={detail.url}
                target="_blank"
                rel="noreferrer"
              >
                {detail.source} · 阅读原始网页{" "}
                <Glyph name="external" size={16} />
              </a>
              <button
                className="r-text-button"
                onClick={() =>
                  void request<typeof raw>("/materials/" + detail.version)
                    .then(setRaw)
                    .catch((e) => setError(e.message))
                }
              >
                {detail.content_kind === "benchmark_snapshot"
                  ? "查看取得的榜单数据"
                  : detail.content_kind === "index_abstract"
                  ? "展开本次保存的索引摘要"
                  : detail.content_kind === "community_post"
                    ? "展开本次保存的社区发言"
                    : "展开本次保存的原文节选"}
              </button>
              {raw && (
                <div className="r-raw">
                  <small>取得于 {when(raw.captured_at)} · 保存的节选</small>
                  <p>{raw.text}</p>
                </div>
              )}
            </section>
            <section>
              <h3>边界与未知</h3>
              <ul>
                {detail.limitations.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
                <li>来源陈述与文中测试不等于已完成独立验证。</li>
              </ul>
            </section>
            {detail.timeline.length > 1 && (
              <section>
                <h3>
                  报道与进展{" "}
                  <small>
                    {detail.report_count} 篇报道，{detail.source_count} 个来源
                  </small>
                </h3>
                <div className="r-timeline">
                  {[...detail.timeline].reverse().map((t) => (
                    <div key={t.version}>
                      <small>
                        {when(t.published_at)} · {actionLabel[t.action]}
                      </small>
                      <a href={t.url} target="_blank" rel="noreferrer">
                        {t.title}
                      </a>
                      <p>{t.source}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}
            {!historical && (
              <div className="r-detail-actions">
                <button
                  className="r-primary"
                  onClick={() => void act(detail, "useful")}
                >
                  <Glyph name="check" size={16} />
                  有帮助
                </button>
                <button onClick={() => void act(detail, "known")}>
                  {detail.known ? "已标记了解" : "标记已了解"}
                </button>
                <button onClick={() => void act(detail, "saved")}>
                  <Glyph name="bookmark" size={17} />
                  {detail.saved ? "取消收藏" : "收藏"}
                </button>
                <button
                  onClick={() =>
                    beginFollow(
                      detail.object || detail.title,
                      detail.object || "",
                    )
                  }
                >
                  <Glyph name="follow" size={17} />
                  追踪相关话题
                </button>
                <button onClick={() => setFeedback(detail)}>不感兴趣</button>
              </div>
            )}
            {!historical &&
              detail.actions.filter(
                (a) => !["shown", "opened"].includes(a.kind),
              ).length > 0 && (
                <section>
                  <h3>我的反馈</h3>
                  {detail.actions
                    .filter((a) => !["shown", "opened"].includes(a.kind))
                    .map((a) => (
                      <div className="r-feedback-history" key={a.request_id}>
                        <span>
                          {{
                            useful: "有帮助",
                            known: "已了解",
                            saved: "收藏",
                            irrelevant: "方向无关",
                            thin: "内容空泛",
                            duplicate: "重复内容",
                          }[a.kind] || a.kind}
                        </span>
                        <button onClick={() => void undo(detail, a)}>
                          撤回
                        </button>
                      </div>
                    ))}
                </section>
              )}
          </div>
        </Dialog>
      )}
      {history && (
        <Dialog title="过去的简报" close={() => setHistory(null)}>
          <div className="r-feedback">
            {history.length ? (
              history.map((row) => (
                <button
                  key={row.id}
                  onClick={() =>
                    void request<View>("/snapshots/" + row.id)
                      .then((value) => {
                        setView(value);
                        setHistorical(row.id);
                        setPage("briefing");
                        setHistory(null);
                      })
                      .catch((e) => setError(e.message))
                  }
                >
                  {when(row.created_at)}
                  <Glyph name="arrow" size={16} />
                </button>
              ))
            ) : (
              <p>完成一次更新后，这里会保留当时的简报。</p>
            )}
          </div>
        </Dialog>
      )}
      {feedback && (
        <Dialog title="让下一份简报更合适" close={() => setFeedback(null)}>
          <div className="r-feedback">
            <p>这条内容哪里不合适？</p>
            {[
              ["irrelevant", "方向与兴趣无关"],
              ["thin", "内容空泛，信息量太少"],
              ["duplicate", "重复了，没有新增信息"],
              ["known", "已经了解这件事"],
            ].map(([kind, label]) => (
              <button key={kind} onClick={() => void act(feedback, kind)}>
                {label}
                <Glyph name="arrow" size={16} />
              </button>
            ))}
          </div>
        </Dialog>
      )}
      {settings && (
        <Dialog title="你的阅读偏好" close={() => setSettings(false)}>
          {prefs ? (
            <form
              className="r-preferences"
              onSubmit={(e) => {
                e.preventDefault();
                void savePrefs();
              }}
            >
              <fieldset>
                <legend>想多看哪些方向</legend>
                <p>其他方向仍可在“发现”中浏览。</p>
                <div className="r-interest-grid">
                  {Object.entries(topics).map(([id, label]) => (
                    <label key={id}>
                      <input
                        type="checkbox"
                        checked={prefs.topics.includes(id as Topic)}
                        onChange={(e) =>
                          setPrefs({
                            ...prefs,
                            topics: e.target.checked
                              ? [...prefs.topics, id as Topic]
                              : prefs.topics.filter((t) => t !== id),
                          })
                        }
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend>内容深度</legend>
                <div className="r-options">
                  {[
                    ["balanced", "均衡阅读"],
                    ["technical", "技术细节"],
                    ["overview", "快速了解"],
                  ].map(([id, label]) => (
                    <button
                      type="button"
                      key={id}
                      className={prefs.depth === id ? "active" : ""}
                      onClick={() =>
                        setPrefs({ ...prefs, depth: id as Prefs["depth"] })
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend>这次想读多久</legend>
                <div className="r-options">
                  {([3, 7, 15] as const).map((value) => (
                    <button
                      type="button"
                      key={value}
                      className={prefs.budget_minutes === value ? "active" : ""}
                      onClick={() =>
                        setPrefs({ ...prefs, budget_minutes: value })
                      }
                    >
                      {value} 分钟
                    </button>
                  ))}
                </div>
                <p>用于估算简报长度，不代表实际阅读速度。</p>
              </fieldset>
              <label className="r-explore-toggle">
                <input
                  type="checkbox"
                  checked={prefs.exploration}
                  onChange={(e) =>
                    setPrefs({ ...prefs, exploration: e.target.checked })
                  }
                />
                <span>留一点空间给意外发现</span>
              </label>
              {!prefs.topics.length && <p role="alert">至少选择一个方向。</p>}
              <button
                className="r-primary"
                type="submit"
                disabled={!prefs.topics.length}
              >
                保存阅读偏好
              </button>
            </form>
          ) : (
            <p className="r-dialog-padding">正在读取偏好，请稍后重试。</p>
          )}
        </Dialog>
      )}
      {sourcesOpen && (
        <Dialog title="来源与覆盖" close={() => setSourcesOpen(false)} wide>
          <div className="r-sources">
            <p>
              来源配置不代表持续覆盖。这里显示本机最近一次检查的结果；失败时保留已有资料。
            </p>
            {view?.usage && (
              <p>
                {view.usage.request_limit === null &&
                view.usage.token_limit === null
                  ? "AI 处理不设每日次数或 Token 总量上限。"
                  : "AI 处理使用本机配置的每日额度。"}
                本统计日已调用 {view.usage.requests_today} 次，记账{" "}
                {view.usage.tokens_today.toLocaleString()} Token。
              </p>
            )}
            {view?.sources.map((s) => (
              <article key={s.id}>
                <div>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.name}
                    <Glyph name="external" size={14} />
                  </a>
                  <small>
                    {s.kind === "search"
                      ? "主动检索 · " + (s.description || s.name)
                      : ({
                          official: "官方发布",
                          research: "研究机构",
                          media: "专业媒体",
                          author: "技术作者",
                          community: "开发者社区",
                        }[s.role] || "公开来源") +
                        " · " +
                        ({
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
                        }[s.kind] || "订阅来源")}
                  </small>
                  {s.kind !== "search" && (
                    <small>
                      {s.priority === 0 ? "核心来源" : "补充来源"}
                      {s.description ? " · " + s.description : ""}
                    </small>
                  )}
                </div>
                <div>
                  <span className={"r-source-state " + s.state.status}>
                    {s.state.status === "ok"
                      ? "检查成功"
                      : s.state.status === "error"
                        ? "暂不可用"
                        : s.state.status === "empty"
                          ? "本次无结果"
                          : "尚未检查"}
                  </span>
                  <small>
                    {s.state.last_success
                      ? "最近成功 " + when(s.state.last_success)
                      : "尚无成功记录"}
                  </small>
                  {s.state.count !== undefined && s.state.status !== "error" && (
                    <small>
                      采集得到 {s.state.count} 条
                      {s.state.with_text !== undefined
                        ? `，其中 ${s.state.with_text} 条带文本节选`
                        : ""}
                    </small>
                  )}
                  {s.state.http_status && <small>HTTP {s.state.http_status}</small>}
                </div>
              </article>
            ))}
          </div>
        </Dialog>
      )}
    </div>
  );
}
