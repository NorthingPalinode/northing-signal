import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { Glyph } from "./ui";
import { evidence, when } from "./reader/logic";
import type { Story } from "./reader/types";

const THRESHOLD = 90;
type Move = "next" | "prev";

/**
 * 快速翻阅: today's unread stories one card at a time, like turning pages. The bar holds
 * three buttons only (previous card, open this card, next card); swiping and ← → turn pages
 * too. 收藏 lives on the card. Turning a page marks nothing: only opening a story counts as
 * reading it, as everywhere else.
 */
export default function QuickDeck({
  stories,
  isSaved,
  toggleSave,
  open,
  close,
}: {
  stories: Story[];
  isSaved: (story: Story) => boolean;
  toggleSave: (story: Story) => Promise<void>;
  open: (story: Story) => void;
  close: () => void;
}) {
  // The deck is dealt once: saving reloads the briefing, which must not reshuffle it.
  const [deck] = useState(stories);
  const [index, setIndex] = useState(0);
  const [seen, setSeen] = useState(1);
  const [entered, setEntered] = useState<Move>("next");
  const [leaving, setLeaving] = useState(false);
  const [drag, setDrag] = useState({ x: 0, on: false });
  // Shown at once while the save request and reload run; dropped when they finish.
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const start = useRef(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const story = deck[index];
  const saved = (s: Story) => pending[s.id] ?? isSaved(s);

  useEffect(() => {
    const node = dialog.current;
    node?.showModal();
    document.documentElement.classList.add("r-locked");
    return () => {
      node?.close();
      document.documentElement.classList.remove("r-locked");
    };
  }, []);

  function next() {
    if (leaving || index >= deck.length) return;
    if (!story) return;
    setLeaving(true);
    setTimeout(() => {
      setLeaving(false);
      setDrag({ x: 0, on: false });
      setEntered("next");
      setIndex((i) => i + 1);
      setSeen((n) => Math.max(n, index + 2));
    }, 220);
  }
  function prev() {
    if (leaving || index === 0) return;
    setDrag({ x: 0, on: false });
    setEntered("prev");
    setIndex((i) => i - 1);
  }
  function save(s: Story) {
    const now = !saved(s);
    setPending((p) => ({ ...p, [s.id]: now }));
    void toggleSave(s).finally(() =>
      setPending((p) => {
        const rest = { ...p };
        delete rest[s.id];
        return rest;
      }),
    );
  }

  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "arrowright") next();
      else if (k === "arrowleft") prev();
      else if ((k === "enter" || k === "arrowup") && story && !(e.target as HTMLElement).closest?.("button"))
        open(story);
      else if (k === "s" && story) save(story);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  });

  const down = (e: PointerEvent) => {
    if ((e.target as HTMLElement).closest("button, a")) return;
    start.current = e.clientX;
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      /* no active pointer to capture (synthetic events); dragging still follows moves */
    }
    setDrag({ x: 0, on: true });
  };
  const move = (e: PointerEvent) => {
    if (drag.on) setDrag({ x: e.clientX - start.current, on: true });
  };
  const up = () => {
    if (!drag.on) return;
    if (drag.x < -THRESHOLD) return next();
    if (drag.x > THRESHOLD && index > 0) return prev();
    setDrag({ x: 0, on: false });
  };

  const savedCount = deck.filter(saved).length;
  // Dragging right on the first card only gives a little: there is nothing before it.
  const dx = index === 0 && drag.x > 0 ? drag.x * 0.25 : drag.x;
  const front: CSSProperties = leaving
    ? { transform: "translateX(-115%) rotate(-10deg)", opacity: 0 }
    : drag.on
      ? { transform: `translateX(${dx}px) rotate(${dx * 0.04}deg)`, transition: "none" }
      : {};
  const pull = Math.min(1, Math.abs(Math.min(0, dx)) / 160);

  return (
    <dialog
      ref={dialog}
      className="r-deck"
      aria-label="快速翻阅"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="r-deck-panel">
        <header className="r-deck-head">
          <div>
            <strong>快速翻阅</strong>
            <small aria-live="polite">
              {story ? `第 ${index + 1} / ${deck.length} 张` : `${deck.length} 张已翻完`}
              <span className="r-deck-keys"> · ← → 翻页 · 回车打开 · S 收藏</span>
            </small>
          </div>
          <button className="r-icon" aria-label="关闭快速翻阅" onClick={close}>
            <Glyph name="close" size={18} />
          </button>
        </header>
        <div className="r-deck-progress" aria-hidden="true">
          {deck.map((s, i) => (
            <i
              key={s.id}
              className={(i === index ? "now" : i < seen ? "seen" : "") + (saved(s) ? " saved" : "")}
            />
          ))}
        </div>

        {story ? (
          <div className="r-deck-stage">
            {deck.slice(index + 1, index + 3).reverse().map((s, k, arr) => {
              const depth = arr.length - k;
              const lift = depth === 1 ? pull : 0;
              return (
                <article
                  key={s.id}
                  className="r-deck-card behind"
                  style={{
                    "--tc": `var(--t-${s.topic})`,
                    transform: `translateY(${depth * 16 - lift * 16}px) scale(${1 - depth * 0.05 + lift * 0.05})`,
                  } as CSSProperties}
                  aria-hidden="true"
                >
                  <DeckFace story={s} saved={saved(s)} />
                </article>
              );
            })}
            <article
              key={story.id}
              className={"r-deck-card front enter-" + entered + (drag.on ? " dragging" : "")}
              style={{ "--tc": `var(--t-${story.topic})`, ...front } as CSSProperties}
              onPointerDown={down}
              onPointerMove={move}
              onPointerUp={up}
              onPointerCancel={up}
            >
              <DeckFace story={story} saved={saved(story)} onSave={() => save(story)} />
            </article>
          </div>
        ) : (
          <div className="r-deck-done">
            <span className="r-deck-check" aria-hidden="true">
              <Glyph name="check" size={30} />
            </span>
            <h2>{deck.length ? "今天的未读都翻完了" : "没有未读的内容"}</h2>
            <p>
              {deck.length
                ? savedCount
                  ? `翻过 ${deck.length} 张，收藏了 ${savedCount} 条。想细读的可以回到简报打开。`
                  : `翻过 ${deck.length} 张。想细读的可以回到简报打开。`
                : "简报里的内容都已了解。下次更新后再来。"}
            </p>
            <div className="r-deck-done-actions">
              {deck.length > 0 && (
                <button
                  className="r-button"
                  onClick={() => {
                    setEntered("prev");
                    setIndex(0);
                  }}
                >
                  从第一张再看
                </button>
              )}
              <button className="r-button primary" onClick={close}>
                回到简报
              </button>
            </div>
          </div>
        )}

        <footer className="r-deck-controls">
          <button className="r-deck-btn" title="上一张（←）" disabled={index === 0} onClick={prev}>
            <Glyph name="back" size={17} />
            <span>上一张</span>
          </button>
          <button className="r-deck-btn main" title="打开（回车）" disabled={!story} onClick={() => story && open(story)}>
            <Glyph name="external" size={17} />
            <span>打开这张</span>
          </button>
          <button className="r-deck-btn" title="下一张（→）" disabled={!story} onClick={next}>
            <span>下一张</span>
            <Glyph name="arrow" size={17} />
          </button>
        </footer>
      </div>
    </dialog>
  );
}

function DeckFace({ story, saved, onSave }: { story: Story; saved: boolean; onSave?: () => void }) {
  const reports = Math.max(story.report_count || 0, story.timeline.length);
  return (
    <>
      <div className="r-deck-band">
        <span className="r-deck-topic">{story.topic_label}</span>
        <button
          className={"r-deck-save" + (saved ? " on" : "")}
          aria-pressed={saved}
          tabIndex={onSave ? 0 : -1}
          onClick={onSave}
        >
          <Glyph name="bookmark" size={15} />
          {saved ? "已收藏" : "收藏"}
        </button>
        <span className="r-deck-count">
          <strong>{reports > 1 ? reports : story.source_count}</strong>
          <small>{reports > 1 ? "篇报道" : "个来源"}</small>
        </span>
      </div>
      <div className="r-deck-body">
        <small className="r-deck-src">
          {story.source} · {when(story.published_at, story.captured_at)} · {evidence(story.evidence, story.source_role, story.content_kind)}
        </small>
        <h3>{story.title}</h3>
        <p>{story.summary}</p>
        {story.reason && (
          <div className="r-deck-why">
            <b>为什么值得读</b>
            {story.reason}
          </div>
        )}
      </div>
    </>
  );
}
