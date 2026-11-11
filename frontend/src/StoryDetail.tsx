import { useState } from "react";
import { Glyph } from "./ui";
import { actionLabel, evidence, mergeCandidates, when } from "./reader/logic";
import type { Action, Story, View } from "./reader/types";

export const feedbackKinds: [string, string][] = [
  ["irrelevant", "方向与兴趣无关"],
  ["thin", "内容空泛，信息量太少"],
  ["duplicate", "重复了，没有新增信息"],
  ["known", "已经了解这件事"],
];

const actionNames: Record<string, string> = {
  useful: "有帮助",
  known: "已了解",
  saved: "收藏",
  irrelevant: "方向无关",
  thin: "内容空泛",
  duplicate: "重复内容",
};

type Raw = { title: string; text: string; url: string; captured_at: string };

export function FeedbackChoices({ pick }: { pick: (kind: string) => void }) {
  return (
    <div className="r-choices">
      {feedbackKinds.map(([kind, label]) => (
        <button key={kind} onClick={() => pick(kind)}>
          {label}
          <Glyph name="arrow" size={15} />
        </button>
      ))}
    </div>
  );
}

type ActionProps = {
  story: Story;
  act: (kind: string) => void;
  follow: () => void;
  askFeedback: () => void;
};

/** Reader actions; `layout="bar"` is the sticky bottom bar on narrow screens. */
export function DetailActions({
  story,
  act,
  follow,
  askFeedback,
  layout = "bar",
}: ActionProps & { layout?: "bar" | "stack" }) {
  return (
    <div className={layout === "bar" ? "r-detail-actions" : "r-action-stack"}>
      <button
        className={"r-chip-button" + (story.saved ? " on" : "")}
        aria-pressed={story.saved}
        onClick={() => act("saved")}
      >
        <Glyph name="bookmark" size={16} />
        {story.saved ? "已收藏" : "收藏"}
      </button>
      <button className="r-chip-button" onClick={() => act("useful")}>
        <Glyph name="thumb" size={16} />
        有帮助
      </button>
      <button
        className={"r-chip-button" + (story.known ? " on" : "")}
        onClick={() => act("known")}
        disabled={story.known}
      >
        <Glyph name="check" size={16} />
        {story.known ? "已了解" : "标为已了解"}
      </button>
      <button className="r-chip-button" onClick={follow}>
        <Glyph name="follow" size={16} />
        {layout === "stack" ? "持续追踪这个话题" : "追踪"}
      </button>
      <button
        className="r-chip-button quiet"
        aria-label="不感兴趣"
        title="不感兴趣"
        onClick={askFeedback}
      >
        <Glyph name="more" size={16} />
        <span className={layout === "bar" ? "r-hide-sm" : ""}>不感兴趣</span>
      </button>
    </div>
  );
}

function PagerLink({
  story,
  dir,
  go,
}: {
  story?: Story;
  dir: "prev" | "next";
  go: (id: string) => void;
}) {
  if (!story) return <span />;
  return (
    <button className={"r-pager-link " + dir} onClick={() => go(story.id)}>
      <small>
        {dir === "prev" && <Glyph name="back" size={14} />}
        {dir === "prev" ? "上一条" : "下一条"}
        {dir === "next" && <Glyph name="arrow" size={14} />}
      </small>
      <strong>{story.title}</strong>
      <span className={"r-topic t-" + story.topic}>{story.topic_label}</span>
    </button>
  );
}

/** One story as a full reading page: article, a sticky side column, and prev/next. */
export default function StoryReader({
  story,
  view,
  historical,
  prev,
  next,
  go,
  act,
  follow,
  askFeedback,
  undo,
  regroup,
  loadRaw,
}: ActionProps & {
  view: View | null;
  historical: boolean;
  prev?: Story;
  next?: Story;
  go: (id: string) => void;
  undo: (action: Action) => void;
  regroup: (path: string, body: object, done: string) => void;
  loadRaw: () => Promise<Raw>;
}) {
  const [raw, setRaw] = useState<Raw | null>(null);
  const [rawBusy, setRawBusy] = useState(false);
  const [mergeInto, setMergeInto] = useState("");
  const kind = story.content_kind;
  const candidates = historical ? [] : mergeCandidates(view, story);
  const history = story.actions.filter(
    (a) => !["shown", "opened"].includes(a.kind),
  );
  const minutes = Math.max(1, Math.round(story.reading_seconds / 60));
  return (
    <div className="r-reader">
      <article className="r-detail">
        <div className="r-meta">
          <span className={"r-topic t-" + story.topic}>{story.topic_label}</span>
          <span className="r-badge">
            {evidence(story.evidence, story.source_role, kind)}
          </span>
          {story.protected && (
            <span className="r-badge warn">重要{actionLabel[story.action]}</span>
          )}
          {story.policy_stale && (
            <span className="r-badge">按旧版规则整理，待重新整理</span>
          )}
        </div>
        <h1>{story.title}</h1>
        <p className="r-detail-byline">
          {[
            story.source +
              (story.source_count > 1 ? ` 等 ${story.source_count} 个来源` : ""),
            when(story.published_at, story.captured_at),
            `约 ${minutes} 分钟`,
          ].join(" · ")}
        </p>
        <p className="r-detail-summary">{story.summary}</p>
        {story.reason && (
          <div className="r-callout">
            <strong>为什么值得读</strong>
            <p>{story.reason}</p>
          </div>
        )}

        <section>
          <h2>
            {kind === "benchmark_snapshot"
              ? "榜单数据中的依据"
              : kind === "index_abstract"
                ? "索引摘要支持的主张"
                : kind === "community_post"
                  ? "社区发言中的主张"
                  : "原文支持的主张"}
          </h2>
          {story.claims.length ? (
            story.claims.map((c, i) => (
              <div className="r-claim" key={i}>
                <p>{c.statement}</p>
                <blockquote>{c.quote}</blockquote>
              </div>
            ))
          ) : (
            <p className="r-muted">没有可引用的原文主张。</p>
          )}
          <div className="r-source-row">
            <a
              className="r-button"
              href={story.url}
              target="_blank"
              rel="noreferrer"
            >
              阅读原文 <Glyph name="external" size={15} />
            </a>
            <button
              className="r-link"
              disabled={rawBusy}
              onClick={() => {
                if (raw) return setRaw(null);
                setRawBusy(true);
                void loadRaw()
                  .then(setRaw)
                  .finally(() => setRawBusy(false));
              }}
            >
              {raw
                ? "收起保存的节选"
                : kind === "benchmark_snapshot"
                  ? "查看取得的榜单数据"
                  : "查看本机保存的节选"}
            </button>
          </div>
          {raw && (
            <div className="r-raw">
              <small>取得于 {when(raw.captured_at)} · 保存的节选</small>
              <p>{raw.text}</p>
            </div>
          )}
        </section>

        {story.conditions.length > 0 && (
          <section>
            <h2>适用条件与测试范围</h2>
            <ul className="r-list">
              {story.conditions.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h2>边界与未知</h2>
          <ul className="r-list">
            {story.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
            <li>来源陈述与文中测试不等于已完成独立验证。</li>
          </ul>
        </section>

        {story.timeline.length > 1 && (
          <section>
            <h2>
              报道与进展
              <small>
                {story.report_count} 篇报道 · {story.source_count} 个来源
              </small>
            </h2>
            <ol className="r-timeline">
              {[...story.timeline].reverse().map((t) => (
                <li key={t.version}>
                  <small>
                    {when(t.published_at)} · {actionLabel[t.action]} · {t.source}
                  </small>
                  <a href={t.url} target="_blank" rel="noreferrer">
                    {t.title}
                  </a>
                  {!historical && (
                    <button
                      className="r-link small"
                      aria-label={"不是同一件事：" + t.title}
                      onClick={() =>
                        regroup(
                          "split",
                          { version: t.version },
                          "已拆分为单独的事件，之后不会自动并回。",
                        )
                      }
                    >
                      不是同一件事？拆分
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}

        {candidates.length > 0 && (
          <details className="r-fold">
            <summary>和另一条事件重复？</summary>
            <div className="r-merge">
              <select
                aria-label="选择要合并到的事件"
                value={mergeInto}
                onChange={(e) => setMergeInto(e.target.value)}
              >
                <option value="">选择同一方向下的事件…</option>
                {candidates.map((e) => (
                  <option key={e.id} value={e.id}>
                    {when(e.published_at, e.captured_at)} · {e.title}
                  </option>
                ))}
              </select>
              <button
                className="r-button"
                disabled={!mergeInto}
                onClick={() =>
                  regroup(
                    "merge",
                    { into: mergeInto },
                    "已合并，收藏和反馈随报道一起保留。",
                  )
                }
              >
                合并
              </button>
            </div>
          </details>
        )}
      </article>

      <aside className="r-reader-aside" aria-label="这条内容">
        {!historical && (
          <section className="r-card r-reader-actions">
            <DetailActions
              story={story}
              act={act}
              follow={follow}
              askFeedback={askFeedback}
              layout="stack"
            />
          </section>
        )}
        <section className="r-card">
          <h2 className="r-card-title">来源</h2>
          <dl className="r-facts">
            <dt>发布方</dt>
            <dd>{story.source}</dd>
            <dt>时间</dt>
            <dd>{when(story.published_at, story.captured_at)}</dd>
            <dt>依据</dt>
            <dd>{evidence(story.evidence, story.source_role, kind)}</dd>
            <dt>报道</dt>
            <dd>
              {story.report_count} 篇 · {story.source_count} 个来源
            </dd>
          </dl>
          <a
            className="r-button block"
            href={story.url}
            target="_blank"
            rel="noreferrer"
          >
            阅读原文 <Glyph name="external" size={15} />
          </a>
        </section>
        {!historical && history.length > 0 && (
          <section className="r-card">
            <h2 className="r-card-title">我的反馈</h2>
            {history.map((a) => (
              <div className="r-feedback-row" key={a.request_id}>
                <span>
                  {actionNames[a.kind] || a.kind}
                  <small>{when(a.at)}</small>
                </span>
                <button className="r-link" onClick={() => undo(a)}>
                  撤回
                </button>
              </div>
            ))}
          </section>
        )}
        <p className="r-keys">
          <kbd>J</kbd> <kbd>K</kbd> 切换上下条 · <kbd>Esc</kbd> 返回
        </p>
      </aside>

      {(prev || next) && (
        <nav className="r-pager" aria-label="上一条与下一条">
          <PagerLink story={prev} dir="prev" go={go} />
          <PagerLink story={next} dir="next" go={go} />
        </nav>
      )}
    </div>
  );
}
