import { useEffect, useRef, useState } from "react";
import { failureMessage, reach, signedOut } from "./auth";
import type { View } from "./reader/types";
import { searchSources, sourceName, type SearchSource } from "./searchSources";

export type TrackingPlan = {
  title: string;
  intent_summary: string;
  focus: string[];
  exclude: string[];
  entities: string[];
  topics: string[];
  searches: { source: SearchSource; query: string; purpose: string }[];
  include_feeds: boolean;
  interval_minutes: 30 | 120 | 1440 | 10080;
  relevance_criteria: string;
  assumptions: string[];
  limitations: string[];
};
type Draft = { id: string; description: string; plan: TrackingPlan };
export const intervalLabel = (minutes: number) =>
  ({ 30: "约每 30 分钟", 120: "约每 2 小时", 1440: "约每天", 10080: "约每周" })[
    minutes
  ] || "定期";

export default function FollowIntentForm({
  initialDescription,
  followId,
  onConfirmed,
}: {
  initialDescription: string;
  followId?: string;
  onConfirmed: (value: View) => void;
}) {
  const [description, setDescription] = useState(initialDescription);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [feedback, setFeedback] = useState("");
  const [editing, setEditing] = useState(false);
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState<"understand" | "confirm" | null>(null);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const form = useRef<HTMLDivElement | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    form.current?.closest("dialog")?.scrollTo(0, 0);
  }, [draft?.id]);

  async function post<T>(path: string, body: unknown): Promise<T> {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const response = await reach("/api/reader/follows" + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) signedOut();
    if (!response.ok)
      throw new Error(failureMessage(response.status, result, "方案内容不完整，请检查后重试。"));
    return result;
  }
  async function interpret() {
    const text =
      description.trim() +
      (draft && feedback.trim() ? "\n补充要求：" + feedback.trim() : "");
    if (text.length > 2000) {
      setError("描述和补充要求合计请控制在 2000 字内。");
      return;
    }
    setBusy("understand");
    setError("");
    try {
      const value = await post<Draft>("/interpret", {
        description: text,
        follow_id: followId || null,
      });
      setDraft(value);
      setDescription(text);
      setFeedback("");
      setEditing(false);
    } catch (reason) {
      if ((reason as Error).name !== "AbortError")
        setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  }
  async function confirm() {
    if (!draft) return;
    setBusy("confirm");
    setError("");
    const clean = (items: string[]) =>
      items.map((v) => v.trim()).filter(Boolean);
    const plan = {
      ...draft.plan,
      title: draft.plan.title.trim(),
      focus: clean(draft.plan.focus),
      exclude: clean(draft.plan.exclude),
    };
    try {
      onConfirmed(await post<View>("", { draft_id: draft.id, plan, active }));
    } catch (reason) {
      if ((reason as Error).name !== "AbortError")
        setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  }
  function change(changes: Partial<TrackingPlan>) {
    setDraft((value) =>
      value ? { ...value, plan: { ...value.plan, ...changes } } : value,
    );
  }

  return (
    <div className="r-intent-form" ref={form} aria-busy={!!busy}>
      <ol className="r-intent-steps" aria-label="创建追踪的步骤">
        <li className={!draft ? "active" : "done"}>1 描述需求</li>
        <li className={draft ? "active" : ""}>2 核对意图</li>
        <li>3 自动追踪</li>
      </ol>
      {!draft ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void interpret();
          }}
        >
          <h2>你想持续了解什么？</h2>
          <p>
            像和研究助手交流一样，描述目标、使用场景、关注重点，以及不想看到的内容。AI
            会帮你拆解意图和制定检索方向。
          </p>
          <label>
            描述你的关注需求
            <textarea
              aria-label="描述你的关注需求"
              rows={7}
              minLength={10}
              maxLength={2000}
              required
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="我想跟进能在本地运行的开源 Agent，重点看工具调用、长期记忆和真实项目。希望看到代码或测试结果，不想看融资消息和只有宣传的发布。"
            />
          </label>
          <small>
            描述会交给当前配置的 AI
            模型理解。此步骤只生成方案，确认后才开始搜索和追踪。
          </small>
          <p className="r-intent-note">
            可用来源：网页搜索、模型卡、研究索引、开源项目、预印本与开发者社区。AI
            根据你的需求选择，确认前可调整。也支持
            X、抖音、小红书的公开网页线索；
            这不代表站内全量检索，尚不能直接理解视频或语音。
          </p>
          {followId && (
            <p className="r-intent-note">
              现有追踪方案保持不变，确认新方案后才会替换。
            </p>
          )}
          {error && (
            <p role="alert" className="r-alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            className="r-primary"
            disabled={!!busy || description.trim().length < 10}
          >
            {busy ? "正在理解你的需求…" : "理解意图，生成追踪方案"}
          </button>
        </form>
      ) : (
        <>
          <div className="r-intent-review-heading">
            <h2>先看看，我理解得对不对</h2>
            <button
              className="r-text-button"
              onClick={() => setEditing(!editing)}
            >
              {editing ? "查看方案" : "直接修改理解"}
            </button>
          </div>
          <section className="r-intent-understanding">
            {editing ? (
              <>
                <label>
                  追踪名称
                  <input
                    aria-label="追踪名称"
                    value={draft.plan.title}
                    maxLength={60}
                    onChange={(e) => change({ title: e.target.value })}
                  />
                </label>
                <label>
                  对意图的理解
                  <textarea
                    aria-label="对意图的理解"
                    rows={4}
                    maxLength={600}
                    value={draft.plan.intent_summary}
                    onChange={(e) => change({ intent_summary: e.target.value })}
                  />
                </label>
              </>
            ) : (
              <>
                <h3>{draft.plan.title}</h3>
                <p>{draft.plan.intent_summary}</p>
              </>
            )}
          </section>
          <div className="r-intent-columns">
            <section>
              <h3>重点关注</h3>
              {editing ? (
                <textarea
                  aria-label="重点关注"
                  rows={5}
                  value={draft.plan.focus.join("\n")}
                  onChange={(e) =>
                    change({ focus: e.target.value.split("\n") })
                  }
                />
              ) : (
                <ul>
                  {draft.plan.focus.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              )}
            </section>
            <section>
              <h3>主动排除</h3>
              {editing ? (
                <textarea
                  aria-label="主动排除"
                  rows={5}
                  value={draft.plan.exclude.join("\n")}
                  onChange={(e) =>
                    change({ exclude: e.target.value.split("\n") })
                  }
                />
              ) : draft.plan.exclude.length ? (
                <ul>
                  {draft.plan.exclude.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p>暂未设定额外排除条件。</p>
              )}
            </section>
          </div>
          <section>
            <h3>什么内容才值得推给你</h3>
            {editing ? (
              <textarea
                aria-label="内容筛选标准"
                rows={3}
                maxLength={600}
                value={draft.plan.relevance_criteria}
                onChange={(e) => change({ relevance_criteria: e.target.value })}
              />
            ) : (
              <p>{draft.plan.relevance_criteria}</p>
            )}
          </section>
          {!!draft.plan.assumptions.length && (
            <section className="r-intent-note">
              <h3>这些理解需要你核对</h3>
              <ul>
                {draft.plan.assumptions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          )}
          <details className="r-intent-strategy">
            <summary>
              查看搜索策略 · {draft.plan.searches.length} 个检索方向
            </summary>
            <label className="r-follow-check">
              <input
                type="checkbox"
                checked={draft.plan.include_feeds}
                onChange={(e) => change({ include_feeds: e.target.checked })}
              />
              跟进已接入的官方、研究与媒体订阅源
            </label>
            {draft.plan.searches.map((search, index) => (
              <div key={index} className="r-intent-search-direction">
                <label>
                  检索来源
                  <select
                    aria-label={`检索来源 ${index + 1}`}
                    value={search.source}
                    onChange={(e) =>
                      change({
                        searches: draft.plan.searches.map((item, i) =>
                          i === index
                            ? {
                                ...item,
                                source: e.target.value as SearchSource,
                              }
                            : item,
                        ),
                      })
                    }
                  >
                    {Object.entries(searchSources).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <p>{search.purpose}</p>
                <input
                  aria-label={`检索方向 ${index + 1}`}
                  value={search.query}
                  maxLength={100}
                  onChange={(e) =>
                    change({
                      searches: draft.plan.searches.map((item, i) =>
                        i === index ? { ...item, query: e.target.value } : item,
                      ),
                    })
                  }
                />
              </div>
            ))}
            <small>
              检索词由 AI 根据意图生成。确认后才发送给对应来源；每次最多执行 2
              个方向，其余方向轮流检查。
            </small>
          </details>
          <section className="r-intent-coverage">
            <h3>来源与执行方式</h3>
            <p>
              {[
                draft.plan.include_feeds ? "订阅来源" : "",
                ...Array.from(
                  new Set(
                    draft.plan.searches.map((item) => sourceName(item.source)),
                  ),
                ),
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <label>
              检查频率
              <select
                aria-label="检查频率"
                value={draft.plan.interval_minutes}
                onChange={(e) =>
                  change({
                    interval_minutes: Number(
                      e.target.value,
                    ) as TrackingPlan["interval_minutes"],
                  })
                }
              >
                {[30, 120, 1440, 10080].map((v) => (
                  <option key={v} value={v}>
                    {intervalLabel(v)}
                  </option>
                ))}
              </select>
            </label>
            <p>
              服务运行期间自动检查。每条候选还会按你的关注重点和排除条件判断，说明它为什么与你有关。
            </p>
            {draft.plan.limitations.length > 0 && (
              <ul>
                {draft.plan.limitations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            )}
          </section>
          <div className="r-intent-refine">
            <label>
              理解有偏差？补充一句话
              <textarea
                aria-label="补充或纠正理解"
                rows={2}
                maxLength={1000}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="比如：优先看个人电脑能跑的项目，不需要云服务商业方案。"
              />
            </label>
            <button
              className="r-text-button"
              disabled={!!busy || feedback.trim().length < 2}
              onClick={() => void interpret()}
            >
              {busy === "understand" ? "正在重新理解…" : "按补充要求重新理解"}
            </button>
          </div>
          {error && (
            <p role="alert" className="r-alert">
              {error}
            </p>
          )}
          <label className="r-follow-check">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            确认后立即开始追踪
          </label>
          <div className="r-intent-confirm">
            <button
              disabled={!!busy}
              onClick={() => {
                setDraft(null);
                setError("");
              }}
            >
              返回修改描述
            </button>
            <button
              className="r-primary"
              disabled={!!busy || !draft.plan.focus.some((v) => v.trim())}
              onClick={() => void confirm()}
            >
              {busy === "confirm"
                ? "正在保存方案…"
                : active
                  ? "确认方案，开始追踪"
                  : "确认方案，暂不启动"}
            </button>
          </div>
          <small>后续修改关注范围也需要重新确认。可随时暂停或取消追踪。</small>
        </>
      )}
    </div>
  );
}
