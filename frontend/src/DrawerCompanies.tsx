import { useState } from "react";
import CompanyLogo from "./CompanyLogo";
import { Glyph, Sheet } from "./ui";
import { DRAWER_AUTO, DRAWER_MAX, type CompanyCard } from "./reader/logic";

/**
 * 编辑侧栏的公司动向: pick which companies sit in the sidebar and in what order. Saved with
 * the reader's preferences (so it follows the account); 恢复自动 goes back to the most active four.
 */
export default function DrawerCompanies({
  cards,
  shown,
  custom,
  save,
  close,
}: {
  /** Every company in the catalog, most active first. */
  cards: CompanyCard[];
  /** What the sidebar shows now. */
  shown: CompanyCard[];
  /** Whether the reader chose the list (false: automatic). */
  custom: boolean;
  save: (ids: string[] | null) => Promise<void>;
  close: () => void;
}) {
  const [ids, setIds] = useState(shown.map((c) => c.id));
  const [busy, setBusy] = useState(false);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const others = cards.filter((c) => !ids.includes(c.id));
  const full = ids.length >= DRAWER_MAX;

  const move = (i: number, by: number) =>
    setIds((list) => {
      const next = [...list];
      [next[i], next[i + by]] = [next[i + by], next[i]];
      return next;
    });
  const commit = async (value: string[] | null) => {
    setBusy(true);
    try {
      await save(value);
      close();
    } catch {
      /* the app already showed the error; the sheet stays open to retry */
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      title="编辑公司动向"
      close={close}
      footer={
        <div className="r-dc-foot">
          <button className="r-button quiet" disabled={busy || !custom} onClick={() => void commit(null)}>
            恢复自动
          </button>
          <span />
          <button className="r-button" onClick={close}>
            取消
          </button>
          <button className="r-button primary" disabled={busy} onClick={() => void commit(ids)}>
            保存
          </button>
        </div>
      }
    >
      <p className="r-sheet-lead">
        选择侧栏里显示的公司和顺序，最多 {DRAWER_MAX} 家。{custom ? "" : `现在是自动：显示动作最多的 ${DRAWER_AUTO} 家。`}
      </p>
      <h3 className="r-dc-title">侧栏中 · {ids.length}</h3>
      {ids.length ? (
        <ol className="r-dc-list">
          {ids.map((id, i) => {
            const c = byId.get(id);
            if (!c) return null;
            return (
              <li key={id}>
                <CompanyLogo id={c.id} name={c.name} size={16} className="xs" />
                <span className="r-dc-name">{c.name}</span>
                <small>{c.total} 个动作</small>
                <button className="r-icon" aria-label={`上移 ${c.name}`} disabled={i === 0} onClick={() => move(i, -1)}>
                  <span className="r-dc-up"><Glyph name="arrow" size={15} /></span>
                </button>
                <button
                  className="r-icon"
                  aria-label={`下移 ${c.name}`}
                  disabled={i === ids.length - 1}
                  onClick={() => move(i, 1)}
                >
                  <span className="r-dc-down"><Glyph name="arrow" size={15} /></span>
                </button>
                <button
                  className="r-icon"
                  aria-label={`从侧栏移除 ${c.name}`}
                  onClick={() => setIds((list) => list.filter((x) => x !== id))}
                >
                  <Glyph name="minus" size={15} />
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="r-muted small">侧栏不显示公司。可以从下面添加，或恢复自动。</p>
      )}
      <h3 className="r-dc-title">其他公司</h3>
      <ul className="r-dc-list">
        {others.map((c) => (
          <li key={c.id}>
            <CompanyLogo id={c.id} name={c.name} size={16} className="xs" />
            <span className="r-dc-name">{c.name}</span>
            <small>{c.total ? `${c.total} 个动作` : "近期没有动作"}</small>
            <button
              className="r-button small"
              disabled={full}
              title={full ? `最多 ${DRAWER_MAX} 家` : undefined}
              onClick={() => setIds((list) => [...list, c.id])}
            >
              <Glyph name="plus" size={14} /> 添加
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
