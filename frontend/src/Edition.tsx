import type { MouseEvent, ReactNode, RefObject } from "react";
import { Shape } from "./EvidenceChart";
import { useExposure } from "./exposure";
import { Glyph } from "./ui";
import { evidence, recentMarks, when, type Change, type Mark } from "./reader/logic";
import type { Story } from "./reader/types";

/**
 * 今日简报 as one edition (DESIGN.md §7, 2026-11-25). Every unit carries the project's three
 * pillars in the same order: what changed since the last visit, why it is worth reading, and the
 * evidence behind it. The report strip uses the evidence chart's marks.
 */

type Actions = {
  readOnly: boolean;
  send: (s: Story, kind: string) => Promise<unknown>;
  open: () => void;
  toggleSave: () => void;
  askFeedback: () => void;
};

const markName: Record<Mark, string> = {
  statement: "官方 / 论文原文",
  test: "测试",
  coverage: "报道",
  opinion: "观点",
  change: "更正与更新",
};

/** sinceVisit's label as a coloured tag: new, correction, test, update, more reports. */
export function ChangeTag({ change }: { change?: Change }) {
  if (!change) return null;
  const tone =
    change.kind === "new"
      ? "new"
      : change.kind === "correction"
        ? "fix"
        : change.label === "新测试"
          ? "test"
          : change.label === "有更新"
            ? "upd"
            : "more";
  return <span className={"r-chg " + tone}>{change.label}</span>;
}

/** One line of evidence: the rule-written standing, never a score. */
function basis(story: Story) {
  return story.standing || evidence(story.evidence, story.source_role, story.content_kind);
}

/** A week of reports on one line, ending at now. */
export function ReportStrip({ story, width = 132 }: { story: Story; width?: number }) {
  const reports = Math.max(story.report_count || 0, story.timeline.length);
  const marks = recentMarks(story);
  const h = 22;
  const y = 11;
  const pad = 6;
  const span = width - pad * 2;
  return (
    <div className="r-strip">
      <svg width={width} height={h} viewBox={`0 0 ${width} ${h}`} aria-label={`最近 7 天 ${marks.length} 篇报道`}>
        <line className="r-strip-axis" x1={pad} x2={width - pad} y1={y} y2={y} />
        {Array.from({ length: 8 }, (_, i) => (
          <line key={i} className="r-strip-tick" x1={pad + (span * i) / 7} x2={pad + (span * i) / 7} y1={y - 6} y2={y + 6} />
        ))}
        <line className="r-strip-now" x1={width - pad} x2={width - pad} y1={y - 8} y2={y + 8} />
        {marks.map((m) => (
          <g key={m.entry.version} className={"r-ev-mark m-" + m.mark}>
            <title>{`${m.entry.source} · ${m.label} · ${when(m.entry.published_at, m.entry.captured_at)}`}</title>
            <Shape mark={m.mark} x={pad + m.x * span} y={y} />
          </g>
        ))}
      </svg>
      <small>
        {reports} 篇报道 · {story.source_count} 个来源
      </small>
    </div>
  );
}

export function StripLegend() {
  return (
    <div className="r-strip-legend" aria-hidden="true">
      {(["statement", "test", "coverage", "change"] as Mark[]).map((m) => (
        <span key={m}>
          <svg width="12" height="12" viewBox="0 0 12 12" className={"r-ev-mark m-" + m}>
            <Shape mark={m} x={6} y={6} />
          </svg>
          {markName[m].split(" / ")[0]}
        </span>
      ))}
    </div>
  );
}

function Badges({ story, change, topic }: { story: Story; change?: Change; topic: boolean }) {
  return (
    <>
      {story.known ? <span className="r-chg read">已了解</span> : <ChangeTag change={change} />}
      {topic && <span className={"r-ed-topic t-" + story.topic}>{story.topic_label}</span>}
      {/* The change tag already says 更正 when the correction is what changed. */}
      {story.protected && change?.kind !== "correction" && <span className="r-badge warn">重要更正</span>}
      {story.aihot && (
        <span className="r-badge aihot" title="AIHOT（aihot.news）的编辑精选也选了这条">
          AIHOT 精选
        </span>
      )}
    </>
  );
}

function QuickActions({ story, readOnly, toggleSave, askFeedback }: Actions & { story: Story }) {
  if (readOnly) return null;
  return (
    <span className="r-ed-actions">
      <button
        className={"r-icon" + (story.saved ? " on" : "")}
        aria-label={(story.saved ? "取消收藏：" : "收藏：") + story.title}
        aria-pressed={story.saved}
        title={story.saved ? "取消收藏" : "收藏"}
        onClick={toggleSave}
      >
        <Glyph name="bookmark" size={16} />
      </button>
      <button className="r-icon" aria-label={"不感兴趣：" + story.title} title="不感兴趣" onClick={askFeedback}>
        <Glyph name="hide" size={16} />
      </button>
    </span>
  );
}

/** Opens the story unless the click was on a control or selected text. */
function opener(open: () => void) {
  return (event: MouseEvent) => {
    if (!(event.target as HTMLElement).closest("button, a, input, select") && !window.getSelection()?.toString())
      open();
  };
}

export function EditionLead({ story, change, ...actions }: { story: Story; change?: Change } & Actions) {
  const ref = useExposure(story, actions.send);
  return (
    <article ref={ref} className={"r-ed-lead" + (story.known ? " known" : "")} onClick={opener(actions.open)}>
      <div className="r-ed-lead-main">
        <div className="r-ed-row">
          <span className="r-ed-kicker">头条</span>
          <Badges story={story} change={change} topic />
        </div>
        <h2>
          <button className="r-ed-title" onClick={actions.open}>
            {story.title}
          </button>
        </h2>
        <p className="r-ed-dek">{story.summary}</p>
        {story.reason && (
          <p className="r-ed-why-box">
            <b>为什么值得读</b>
            {story.reason}
          </p>
        )}
        <QuickActions story={story} {...actions} />
      </div>
      <aside className="r-ed-lead-side">
        <h3>依据</h3>
        <p className="r-ed-basis-big">{basis(story)}</p>
        <ReportStrip story={story} width={220} />
        <p className="r-ed-src">
          {story.source} · {when(story.published_at, story.captured_at)}
        </p>
        <StripLegend />
      </aside>
    </article>
  );
}

export function EditionItem({
  story,
  change,
  topic = true,
  strip = false,
  ...actions
}: { story: Story; change?: Change; topic?: boolean; strip?: boolean } & Actions) {
  const ref = useExposure(story, actions.send);
  const reports = Math.max(story.report_count || 0, story.timeline.length);
  return (
    <article ref={ref} className={"r-ed-item" + (story.known ? " known" : "")} onClick={opener(actions.open)}>
      <div className="r-ed-row">
        <Badges story={story} change={change} topic={topic} />
      </div>
      <h3>
        <button className="r-ed-title" onClick={actions.open}>
          {story.title}
        </button>
      </h3>
      {story.reason && <p className="r-ed-why">{story.reason}</p>}
      <p className="r-ed-evidence">
        <span className="r-ed-basis">{basis(story)}</span>
        <span>
          {story.source} · {when(story.published_at, story.captured_at)}
        </span>
      </p>
      {strip || reports > 1 ? (
        <ReportStrip story={story} />
      ) : (
        <div className="r-strip">
          <small>1 篇报道</small>
        </div>
      )}
      <QuickActions story={story} {...actions} />
    </article>
  );
}

export function EditionQuick({ story, change, ...actions }: { story: Story; change?: Change } & Actions) {
  const ref = useExposure(story, actions.send);
  return (
    <li ref={ref as RefObject<HTMLLIElement>} className={"r-ed-quick" + (story.known ? " known" : "")} onClick={opener(actions.open)}>
      {story.known ? <span className="r-chg read">已了解</span> : <ChangeTag change={change} />}
      <button className="r-ed-title" onClick={actions.open}>
        {story.title}
      </button>
      <small>
        {basis(story).split(" · ")[0]} · {story.source}
      </small>
    </li>
  );
}

export function EditionSection({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="r-ed-sec">
      <header className="r-ed-sec-head">
        <h2>{title}</h2>
        {note && <small>{note}</small>}
      </header>
      {children}
    </section>
  );
}
