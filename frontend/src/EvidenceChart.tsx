import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { evidenceChecklist, evidenceLanes, when, type Mark } from "./reader/logic";
import type { Story } from "./reader/types";

// Drawn in pixels at the measured width: the source column stays put and only the days scroll
// (narrow screens), so lanes never lose their names.
const LABEL = 148;
const LABEL_NARROW = 104;
const MIN_PLOT = 440;
const LEFT = 10;
const RIGHT = 30;
const ROW = 36;
const TOP = 30;
const BOTTOM = 26;
const TIP_W = 300;

const markName: Record<Mark, string> = {
  statement: "官方 / 论文原文",
  test: "测试",
  coverage: "报道",
  opinion: "观点",
  change: "更正与更新",
};

export function Shape({ mark, x, y }: { mark: Mark; x: number; y: number }) {
  if (mark === "statement") return <rect x={x - 5} y={y - 5} width={10} height={10} rx={2} />;
  if (mark === "test") return <path d={`M${x} ${y - 6}L${x + 6} ${y + 5}H${x - 6}Z`} />;
  if (mark === "change") return <path d={`M${x} ${y - 6}L${x + 6} ${y}L${x} ${y + 6}L${x - 6} ${y}Z`} />;
  if (mark === "opinion") return <circle cx={x} cy={y} r={3} />;
  return <circle cx={x} cy={y} r={4.5} />;
}

type Chart = ReturnType<typeof evidenceLanes>;
type Hover = (i: number | null, mark?: Element) => void;

/** The plot itself. Memoised: hovering only changes the tooltip, never re-renders the marks. */
const Plot = memo(function Plot({ chart, hover, width }: { chart: Chart; hover: Hover; width: number }) {
  const label = width < 520 ? LABEL_NARROW : LABEL;
  const PW = Math.max(MIN_PLOT, width - label);
  const H = TOP + chart.lanes.length * ROW + BOTTOM;
  const px = (x: number) => LEFT + x * (PW - LEFT - RIGHT);
  const perLabel = 46; // px a day label needs
  const step = Math.max(1, Math.ceil((chart.days.length * perLabel) / (PW - LEFT - RIGHT)));
  // Hollow reports first so statements, tests and corrections draw on top of them.
  const order = chart.points
    .map((p, i) => ({ ...p, i }))
    .sort((a, b) => Number(b.mark === "coverage") - Number(a.mark === "coverage"));
  const nowX = px(chart.now);
  const short = label === LABEL ? 13 : 8;
  return (
    <>
      <svg className="r-ev-labels" width={label} height={H} aria-hidden="true">
        {chart.lanes.map((lane, i) => (
          <text key={lane} className="r-ev-source" x={14} y={TOP + i * ROW + ROW / 2 + 4}>
            <title>{lane}</title>
            {lane.length > short ? lane.slice(0, short - 1) + "…" : lane}
          </text>
        ))}
      </svg>
      <div className="r-ev-scroll" data-scroll="">
        <svg
          width={PW}
          height={H}
          role="img"
          aria-label={`${chart.points.length} 篇报道，${chart.lanes.length} 个来源的时间分布`}
        >
          {chart.days.map((d, i) => (
            <g key={i}>
              <line className="r-ev-grid" x1={px(d.x)} x2={px(d.x)} y1={TOP - 8} y2={H - BOTTOM + 6} />
              {i % step === 0 && px(d.x) + 40 < nowX && (
                <text className="r-ev-day" x={px(d.x) + 5} y={16}>
                  {d.label.replace("月", "/").replace("日", "")}
                </text>
              )}
            </g>
          ))}
          {chart.lanes.map((lane, i) => {
            const y = TOP + i * ROW + ROW / 2;
            return <line key={lane} className="r-ev-lane" x1={0} x2={PW - RIGHT} y1={y} y2={y} />;
          })}
          {chart.official !== null && (
            <line
              className="r-ev-official"
              x1={px(chart.official)}
              x2={px(chart.official)}
              y1={TOP - 8}
              y2={H - BOTTOM + 6}
            />
          )}
          <line className="r-ev-now" x1={nowX} x2={nowX} y1={TOP - 8} y2={H - BOTTOM + 6} />
          <text className="r-ev-now-label" x={nowX} y={H - 6} textAnchor="middle">
            现在
          </text>
          {order.map((p) => {
            const x = px(p.x);
            const y = TOP + p.lane * ROW + ROW / 2;
            return (
              <a
                key={p.entry.version}
                href={p.entry.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`${p.entry.source} · ${p.label} · ${when(p.entry.published_at, p.entry.captured_at)}：${p.entry.title}`}
                className={"r-ev-mark m-" + p.mark}
                style={{ "--d": `${Math.round(p.x * 500)}ms` } as CSSProperties}
                onPointerEnter={(e) => hover(p.i, e.currentTarget)}
                onPointerLeave={() => hover(null)}
                onFocus={(e) => hover(p.i, e.currentTarget)}
                onBlur={() => hover(null)}
              >
                {/* A larger transparent target: the marks are small. */}
                <circle className="r-ev-hit" cx={x} cy={y} r={11} />
                <Shape mark={p.mark} x={x} y={y} />
              </a>
            );
          })}
        </svg>
      </div>
    </>
  );
});

/** Every report of one story on a lane per source and a column per day up to now, with the
 * official text and "now" marked, followed by the itemised evidence checklist. Shown on every
 * story: a single report is still a point in time, and later coverage lands on the same chart. */
export default function EvidenceChart({ story }: { story: Story }) {
  const chart = useMemo(() => evidenceLanes(story), [story]);
  const [tip, setTip] = useState<{ i: number; left: number; top: number; above: boolean } | null>(null);
  const plot = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const node = frame.current;
    if (!node) return;
    setWidth(node.clientWidth);
    const watch = new ResizeObserver(() => setWidth(node.clientWidth));
    watch.observe(node);
    return () => watch.disconnect();
  }, [chart.points.length > 0]);
  // On narrow screens the days scroll sideways: open them at "现在", where the news is.
  useLayoutEffect(() => {
    const scroll = frame.current?.querySelector<HTMLElement>("[data-scroll]");
    if (scroll) scroll.scrollLeft = scroll.scrollWidth;
  }, [chart, width]);
  const hover = useCallback<Hover>((i, mark) => {
    const box = plot.current?.getBoundingClientRect();
    if (i === null || !mark || !box) return setTip(null);
    const r = mark.getBoundingClientRect();
    const center = r.left + r.width / 2 - box.left;
    const above = r.top - box.top > 110;
    setTip({
      i,
      left: Math.max(0, Math.min(center - TIP_W / 2, box.width - TIP_W)),
      top: above ? r.top - box.top - 8 : r.bottom - box.top + 8,
      above,
    });
  }, []);
  const shown = tip ? chart.points[tip.i] : null;
  return (
    <section className="r-evchart" aria-label="证据时间线">
      <header className="r-evchart-head">
        <h2>
          证据时间线 · {story.report_count} 篇报道，{story.source_count} 个来源
        </h2>
        <div className="r-evchart-legend" aria-hidden="true">
          {(["statement", "test", "coverage", "opinion", "change"] as Mark[]).map((m) => (
            <span key={m}>
              <svg width="14" height="14" viewBox="0 0 14 14" className={"r-ev-mark m-" + m}>
                <Shape mark={m} x={7} y={7} />
              </svg>
              {markName[m]}
            </span>
          ))}
        </div>
      </header>
      {chart.points.length > 0 && (
        // The tooltip sits outside the scrolling frame, so the frame never clips it.
        <div className="r-evchart-plot" ref={plot}>
          <div className="r-evchart-frame" ref={frame} onScrollCapture={() => setTip(null)}>
            {width > 0 && <Plot chart={chart} hover={hover} width={width} />}
          </div>
          {shown && tip && (
            <div
              className={"r-ev-tip" + (tip.above ? " above" : "")}
              role="tooltip"
              style={{ left: tip.left, top: tip.top, width: TIP_W }}
            >
              <small>
                {shown.entry.source} · {shown.label} · {when(shown.entry.published_at, shown.entry.captured_at)}
              </small>
              {shown.entry.title}
            </div>
          )}
        </div>
      )}
      <ul className="r-evcheck" aria-label="依据清单">
        {evidenceChecklist(story).map((item) => (
          <li key={item.label} className={item.ok ? "ok" : ""}>
            <i aria-hidden="true" />
            {item.ok ? item.label : "未见" + item.label}
          </li>
        ))}
      </ul>
      {(chart.undated > 0 || chart.points.length === 1) && (
        <p className="r-evchart-note">
          {chart.points.length === 1 && "目前只收到这 1 篇报道；之后的跟进报道、测试和更正会画在同一张图上。"}
          {chart.undated > 0 && `另有 ${chart.undated} 篇报道日期待核对，未画入图中。`}
        </p>
      )}
    </section>
  );
}
