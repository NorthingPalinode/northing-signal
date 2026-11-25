// Round-3 mockup engine: data, hash routing and view markup shared by every style.
// A style supplies: #drawer with [data-page] buttons (optional .nav-ind, [data-badge], [data-collapse]),
// a #view container, an optional #scroller, and CSS for the v-/s-/co-/rk- classes below.
(function () {
  const D = window.NS, X = window.NS2;
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const asOf = new Date(D.as_of), last = new Date(D.last_visit);
  const day0 = (s) => new Date(s.slice(0, 10)).getTime();
  const md = (at) => { const d = new Date(at); return `${d.getMonth() + 1}月${d.getDate()}日`; };
  const when = (at) => {
    if (!at) return "日期未知";
    const diff = Math.round((day0(D.as_of) - day0(at)) / 864e5);
    return diff <= 0 ? "今天 " + at.slice(11, 16) : diff === 1 ? "昨天 " + at.slice(11, 16) : md(at);
  };
  const topics = { models: "模型与多模态", agents: "Agent 与开发", research: "研究与评测", engineering: "部署与成本", products: "产品与应用", industry: "产业与政策" };
  const lensLabel = { company: "公司动向", community: "开源与社区", research: "研究", policy: "政策与产业" };

  /* ---------- data ---------- */
  const main = [...D.focus, ...D.more];
  const extra = X.extra.map((e) => ({
    ...e, source_count: 1, claims: [], limitations: [], heat: 0, updated: false, action: "",
    standing: e.official ? "有官方原文 · 1 个来源" : e.role === "research" ? "有论文原文" : "媒体或作者转述，未见官方原文",
    timeline: [{ at: e.published, source: e.source, stage: e.official || e.role === "research" ? "statement" : "coverage", label: e.evidence, title: e.title }],
    extra: true,
  }));
  const stories = [...main, ...extra];
  const byId = Object.fromEntries(stories.map((s) => [s.id, s]));
  const isNew = (s) => !!s.published && new Date(s.published) > last;
  const flag = (s) => (s.action === "更正" ? "含更正" : s.updated ? "有新报道" : isNew(s) && !s.extra ? "新" : "");
  const changed = main.filter((s) => isNew(s) || s.updated || s.action === "更正");
  const coName = Object.fromEntries(X.companies.map((c) => [c.id, c.name]));
  const BRAND = { openai: "#10a37f", anthropic: "#d97757", google: "#4285f4", microsoft: "#00a4ef", nvidia: "#76b900", meta: "#0081fb", xai: "#6b7280", apple: "#6e6e73", amazon: "#ff9900", deepseek: "#4d6bfe", alibaba: "#615ced", bytedance: "#3c8cff", moonshot: "#1783ff", zhipu: "#4f6bff", minimax: "#eb3665", mistral: "#fa500f", baidu: "#4e6ef2", ant: "#1677ff", tencent: "#1e6fff" };
  /* evidence swimlane chart (from direction B) */
  function evChart(s) {
    const tl = s.timeline.filter((t) => t.at);
    if (tl.length < 2) return "";
    const srcs = [...new Set(tl.map((t) => t.source))];
    const lanes = srcs.length > 8 ? [...srcs.slice(0, 7), "其他来源"] : srcs;
    const lane = (src) => (lanes.includes(src) ? lanes.indexOf(src) : lanes.length - 1);
    const W = 760, L = 150, R = 24, rowH = 30, top = 26, H = top + lanes.length * rowH + 14;
    const t0 = day0(tl[0].at), t1 = Math.max(day0(D.as_of) + 864e5, t0 + 3 * 864e5);
    const x = (at) => L + ((new Date(at).getTime() - t0) / (t1 - t0)) * (W - L - R);
    const days = Math.round((t1 - t0) / 864e5), step = days > 10 ? 2 : 1;
    let g = "";
    for (let d = 0; d <= days; d++) {
      const xx = L + (d / days) * (W - L - R);
      g += `<line x1="${xx}" x2="${xx}" y1="${top - 6}" y2="${H - 8}" stroke="rgba(27,30,36,${d % step ? 0.03 : 0.07})"/>`;
      if (d % step === 0 && d < days) { const dd = new Date(t0 + d * 864e5 + 6e6); g += `<text x="${xx + 4}" y="14" fill="#a9aeb7" font-size="11">${dd.getMonth() + 1}/${dd.getDate()}</text>`; }
    }
    lanes.forEach((ln, i) => { const y = top + i * rowH + rowH / 2; g += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="rgba(27,30,36,.06)"/><text x="16" y="${y + 4}" fill="#4a505b" font-size="12">${esc(ln.length > 14 ? ln.slice(0, 13) + "…" : ln)}</text>`; });
    const off = tl.find((t) => t.stage === "statement");
    if (off) { const xo = x(off.at); g += `<line x1="${xo}" x2="${xo}" y1="${top - 6}" y2="${H - 8}" stroke="#2f63f0" stroke-dasharray="2 3" opacity=".55"/>`; }
    const nowX = x(D.as_of);
    g += `<line x1="${nowX}" x2="${nowX}" y1="${top - 6}" y2="${H - 8}" stroke="#e05a33" opacity=".7"/><text x="${nowX - 4}" y="${H - 1}" fill="#e05a33" font-size="10.5" text-anchor="end">现在</text>`;
    const mark = (t) => (t.stage === "coverage" && t.label === "作者观点" ? "opinion" : t.stage);
    const shape = (k, cx, cy, i) => {
      const c = `class="dot" data-i="${i}"`;
      if (k === "statement") return `<rect ${c} x="${cx - 5}" y="${cy - 5}" width="10" height="10" rx="2" fill="#2f63f0"/>`;
      if (k === "test") return `<path ${c} d="M${cx} ${cy - 6}L${cx + 6} ${cy + 5}H${cx - 6}Z" fill="#1b1e24"/>`;
      if (k === "change") return `<rect ${c} x="${cx - 4.5}" y="${cy - 4.5}" width="9" height="9" fill="#e05a33" transform="rotate(45 ${cx} ${cy})"/>`;
      if (k === "opinion") return `<circle ${c} cx="${cx}" cy="${cy}" r="3" fill="#a9aeb7"/>`;
      return `<circle ${c} cx="${cx}" cy="${cy}" r="4.5" fill="#fff" stroke="#4a505b" stroke-width="1.5"/>`;
    };
    tl.map((t, i) => [t, i]).sort((a, b) => (mark(b[0]) === "coverage") - (mark(a[0]) === "coverage"))
      .forEach(([t, i]) => (g += shape(mark(t), x(t.at), top + lane(t.source) * rowH + rowH / 2, i)));
    const checks = [["官方或论文原文", tl.some((t) => t.stage === "statement")], ["发布方自测", tl.some((t) => t.stage === "test" && /厂商|论文/.test(t.label))], ["他方报告的测试", tl.some((t) => t.stage === "test" && !/厂商|论文/.test(t.label))], ["更正或撤回", tl.some((t) => t.stage === "change") || s.action === "更正"]];
    return `<section class="r-sec" style="grid-column:1/-1"><h3>证据时间线 · ${tl.length} 篇报道，${srcs.length} 个来源</h3>
      <div class="ev-legend"><span><svg width="10" height="10"><rect width="10" height="10" rx="2" fill="#2f63f0"/></svg>官方 / 论文原文</span><span><svg width="12" height="11"><path d="M6 0L12 11H0Z" fill="#1b1e24"/></svg>测试</span><span><svg width="11" height="11"><circle cx="5.5" cy="5.5" r="4.2" fill="#fff" stroke="#4a505b" stroke-width="1.5"/></svg>报道</span><span><svg width="8" height="8"><circle cx="4" cy="4" r="3" fill="#a9aeb7"/></svg>观点</span><span><svg width="11" height="11"><rect x="2" y="2" width="7" height="7" fill="#e05a33" transform="rotate(45 5.5 5.5)"/></svg>更正</span></div>
      <div class="ev-chart pre"><svg width="100%" style="min-width:600px" viewBox="0 0 ${W} ${H}" role="img" aria-label="${tl.length} 篇报道的时间分布">${g}</svg><div class="ev-tip"></div></div>
      <div class="ev-check">${checks.map(([l, ok]) => `<div class="${ok ? "ok" : ""}"><i></i>${ok ? l : "未见" + l}</div>`).join("")}</div></section>`;
  }
  function bindChart() {
    const c = document.querySelector(".ev-chart"); if (!c) return;
    const [, id] = parse(), s = byId[id], tl = s.timeline.filter((t) => t.at), tip = c.querySelector(".ev-tip");
    c.querySelectorAll(".dot").forEach((d) => (d.style.transitionDelay = 12 * +d.dataset.i + "ms"));
    requestAnimationFrame(() => requestAnimationFrame(() => c.classList.remove("pre")));
    c.addEventListener("mousemove", (e) => {
      const dot = e.target.closest(".dot"); if (!dot) return tip.classList.remove("on");
      const t = tl[+dot.dataset.i], box = c.getBoundingClientRect();
      tip.innerHTML = `<small>${esc(t.source)} · ${esc(t.label)} · ${when(t.at)}</small>${esc(t.title)}`;
      let lx = e.clientX - box.left + 14; if (lx > box.width - 310) lx -= 330;
      tip.style.left = lx + "px"; tip.style.top = e.clientY - box.top + 12 + "px"; tip.classList.add("on");
    });
    c.addEventListener("mouseleave", () => tip.classList.remove("on"));
  }

  const S = {
    saved: new Set([D.focus[1].id, extra[0].id, extra[6].id]),
    known: new Set(),
    topic: "all", lens: "company", rank: 0, co: null, q: "", from: "briefing",
  };
  try { const k = JSON.parse(localStorage.getItem("ns-r3-known") || "[]"); k.forEach((x) => S.known.add(x)); } catch {}
  const persist = () => { try { localStorage.setItem("ns-r3-known", JSON.stringify([...S.known])); } catch {} };

  /* ---------- small markup helpers ---------- */
  const topicTag = (s) => `<span class="s-topic" style="--tc:var(--t-${s.topic})">${esc(s.topic_label)}</span>`;
  const flagTag = (s) => { const f = flag(s); return f ? `<span class="s-flag${f === "含更正" ? " warn" : ""}">${f}</span>` : ""; };
  const srcLine = (s) => `${esc(s.source.split(" · ")[0])}${s.source_count > 1 ? ` +${s.source_count - 1}` : ""} · ${when(s.published)}`;
  const icon = {
    save: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 3.5h12v17l-6-4-6 4z"/></svg>`,
    saved: `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.8"><path d="M6 3.5h12v17l-6-4-6 4z"/></svg>`,
    check: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.5 10 17l9-10"/></svg>`,
    back: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 5l-7 7 7 7"/></svg>`,
    arrow: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`,
    refresh: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/></svg>`,
    search: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
  };
  const saveBtn = (s) => `<button class="icon-btn${S.saved.has(s.id) ? " on" : ""}" data-save="${s.id}" aria-pressed="${S.saved.has(s.id)}" aria-label="收藏">${S.saved.has(s.id) ? icon.saved : icon.save}</button>`;

  function lead(s, i) {
    return `<article class="s-card s-lead${S.known.has(s.id) ? " known" : ""}" data-open="${s.id}" style="--tc:var(--t-${s.topic})">
      <div class="s-no">${String(i + 1).padStart(2, "0")}</div>
      <div class="s-body">
        <div class="s-meta">${topicTag(s)}${flagTag(s)}<span class="s-src">${srcLine(s)}</span></div>
        <h3 class="s-title">${esc(s.title)}</h3>
        <p class="s-sum">${esc(s.summary)}</p>
        <p class="s-why"><span>值得读</span>${esc(s.reason)}</p>
        <div class="s-foot"><span class="s-ev">${esc(s.standing || s.evidence)}</span>${saveBtn(s)}</div>
      </div></article>`;
  }
  function row(s, q) {
    const t = q ? hl(s.title, q) : esc(s.title);
    return `<article class="s-card s-row${S.known.has(s.id) ? " known" : ""}" data-open="${s.id}" style="--tc:var(--t-${s.topic})">
      <span class="s-dot"></span>
      <div class="s-body"><h3 class="s-title">${t}</h3>
      <div class="s-meta">${topicTag(s)}${flagTag(s)}<span class="s-src">${srcLine(s)}</span></div></div>
      ${saveBtn(s)}</article>`;
  }
  const hl = (text, q) => esc(text).replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), (m) => `<mark>${m}</mark>`);
  const head = (title, sub, actions = "") => `<header class="v-head"><div><h1>${title}</h1>${sub ? `<p class="v-sub">${sub}</p>` : ""}</div>${actions ? `<div class="v-actions">${actions}</div>` : ""}</header>`;
  const sec = (title, aside, body, cls = "") => `<section class="v-section ${cls}"><div class="v-sh"><h2>${title}</h2>${aside ? `<span>${aside}</span>` : ""}</div>${body}</section>`;
  const empty = (t, d) => `<div class="empty"><b>${t}</b><p>${d}</p></div>`;
  const logo = (id) => `<span class="co-logo" aria-hidden="true">${esc((coName[id] || id).replace(/[^A-Za-z一-龥]/g, "").slice(0, /^[A-Za-z]/.test(coName[id] || "") ? 2 : 1))}</span>`;

  /* ---------- views ---------- */
  const views = {
    briefing() {
      const wk = "日一二三四五六"[asOf.getDay()];
      const rest = [...D.focus.slice(3), ...D.more].filter((s) => S.topic === "all" || s.topic === S.topic);
      const chips = [["all", "全部"], ...Object.entries(topics)].map(([k, v]) => `<button class="chip" data-topic="${k}" aria-pressed="${S.topic === k}">${v}</button>`).join("");
      return head("今日简报", `${asOf.getMonth() + 1}月${asOf.getDate()}日 星期${wk} · 更新于 ${D.as_of.slice(11, 16)} · 下次自动 12:00`,
        `<button class="btn" data-act="deck">快速翻阅</button><button class="btn primary" data-act="update">${icon.refresh}<span>更新</span></button>`) +
        `<div class="v-progress" hidden><span class="v-progress-t"></span><i><b></b></i></div>` +
        `<section class="since"><div class="since-h"><b>${changed.length}</b><span>件事在你上次来之后有变化<br><small>上次 ${when(D.last_visit)}</small></span></div>
          <div class="since-list">${changed.slice(0, 6).map((s) => `<button class="since-item" data-open="${s.id}"><span class="s-flag${flag(s) === "含更正" ? " warn" : ""}">${flag(s) || "新"}</span><span>${esc(s.title)}</span></button>`).join("")}</div></section>` +
        sec("最重要的 3 件事", "按影响与证据排序", `<div class="leads">${D.focus.slice(0, 3).map(lead).join("")}</div>`) +
        sec("也值得看", `${rest.length} 件`, `<div class="chips">${chips}</div><div class="rows">${rest.length ? rest.map((s) => row(s)).join("") : empty("这个方向今天没有新内容", "换一个方向，或者去动向页看更长时间的变化。")}</div>`);
    },
    trends() {
      const tabs = Object.entries(lensLabel).map(([k, v]) => `<button class="tab" data-lens="${k}" aria-selected="${S.lens === k}">${v}</button>`).join("");
      let body = "";
      if (S.lens === "company") {
        if (S.co) {
          const list = stories.filter((s) => s.companies.includes(S.co)).sort((a, b) => (b.published || "").localeCompare(a.published || ""));
          const c = X.companies.find((x) => x.id === S.co);
          body = `<button class="btn ghost" data-co="">${icon.back}<span>全部公司</span></button>
            <div class="co-hero">${logo(S.co)}<div><h2>${esc(c.name)}</h2><p>${c.products.map(esc).join(" · ")}</p></div><span class="co-n"><b>${list.length}</b>条动向</span></div>
            <ol class="co-line">${list.map((s) => `<li data-open="${s.id}"><time>${when(s.published)}</time><div>${topicTag(s)}<h3>${esc(s.title)}</h3><p>${esc(s.standing || s.evidence)}</p></div></li>`).join("")}</ol>`;
        } else {
          const cos = X.companies.map((c) => ({ ...c, list: stories.filter((s) => s.companies.includes(c.id)).sort((a, b) => (b.published || "").localeCompare(a.published || "")) }))
            .sort((a, b) => b.list.length - a.list.length);
          const card = (c) => `<button class="co-card${c.list.length ? "" : " quiet"}" data-co="${c.id}" style="--brand:${BRAND[c.id] || "#5b6472"}">${logo(c.id)}<b class="co-name">${esc(c.name)}</b>${c.list.length ? `<span class="co-count"><b>${c.list.length}</b>个动作</span>` : ""}${c.list.some(isNew) ? `<span class="co-fresh">+${c.list.filter(isNew).length} 新</span>` : ""}</button>`;
          body = `<div class="co-grid">${cos.filter((c) => c.list.length).map(card).join("")}</div>` +
            sec("近期暂无本身动作", "", `<div class="co-quiet">${cos.filter((c) => !c.list.length).map(card).join("")}</div>`);
        }
      } else if (S.lens === "community") {
        const R = X.rankings[S.rank], mx = Math.max(...R.rows.map((r) => r.gained || r.stars || 1));
        body = `<div class="chips">${X.rankings.map((r, i) => `<button class="chip" data-rank="${i}" aria-pressed="${S.rank === i}">${esc(r.name.replace("GitHub Trending · ", "热门 · ").replace("GitHub · ", ""))}</button>`).join("")}</div>
          <ol class="rk">${R.rows.map((r, i) => { const v = r.gained ?? r.stars; return `<li class="rk-row"><span class="rk-i">${i + 1}</span><div class="rk-main"><b>${esc(r.name)}</b><p>${esc(r.description || "")}</p><span class="rk-bar"><i style="--w:${(100 * v) / mx}%"></i></span></div><span class="rk-v"><b>${r.gained != null ? "+" + r.gained.toLocaleString() : (r.stars || 0).toLocaleString()}</b><small>${r.gained != null ? "新增 ★" : "★ 总量"} · ${esc(r.language || "—")}</small></span></li>`; }).join("")}</ol>`;
      } else {
        const list = stories.filter((s) => s.lenses.includes(S.lens)).sort((a, b) => (b.published || "").localeCompare(a.published || ""));
        body = `<div class="rows">${list.map((s) => row(s)).join("") || empty("暂时没有内容", "")}</div>`;
      }
      return head("动向", "按公司、开源社区、研究和政策看一段时间里的变化") + `<div class="tabs" role="tablist">${tabs}<i class="tab-ind"></i></div><div class="trend-body">${body}</div>`;
    },
    search() {
      const q = S.q.trim().toLowerCase();
      const res = q ? stories.filter((s) => (s.title + s.summary + s.source + (s.subject || "")).toLowerCase().includes(q)).slice(0, 30) : [];
      const sugg = ["OpenAI", "英伟达", "Claude", "评测", "开源", "Agent", "Gemini", "芯片"];
      return head("搜索", `在 ${stories.length} 条已整理的事件里查找；找不到时可以发起外部搜索`) +
        `<label class="search-box">${icon.search}<input id="q" value="${esc(S.q)}" placeholder="输入公司、产品或话题" autocomplete="off"><kbd>/</kbd></label>
        <div class="chips sugg">${sugg.map((w) => `<button class="chip" data-q="${w}">${w}</button>`).join("")}</div>
        <div id="results">${q ? (res.length ? `<p class="v-count">${res.length} 条结果</p><div class="rows">${res.map((s) => row(s, S.q.trim())).join("")}</div>` : empty(`没有找到「${esc(S.q)}」`, "可以把它设为追踪话题，新的报道出现时会出现在追踪页。")) : empty("从一个关键词开始", "也可以按 / 随时回到这里。")}</div>`;
    },
    following() {
      const match = (f) => { const words = f.query.split(/\s+/).filter((w) => /^[A-Z]/.test(w)); return stories.filter((s) => words.some((w) => s.title.includes(w))).slice(0, 4); };
      return head("追踪", "你确认过的话题。只在你打开时检查，不发站外通知", `<button class="btn primary" data-act="new-follow">新建追踪</button>`) +
        `<div class="fl-new" hidden><label class="search-box"><input placeholder="想持续关注什么？例如：DeepSeek 的新模型和评测"></label><p class="v-sub">提交后会先生成追踪计划，确认后才开始。</p></div>` +
        `<div class="fl-list">${X.follows.map((f) => { const m = match(f); return `<article class="fl-card"><div class="fl-top"><span class="fl-state ${f.active ? "on" : ""}">${f.active ? "追踪中" : "已暂停"}</span><small>上次检查 ${when(f.checked)}${f.status === "partial" ? " · 部分来源未返回" : ""}</small></div>
          <h3>${esc(f.name)}</h3><p class="fl-q">${esc(f.description || f.query)}</p>
          <div class="fl-hits">${m.map((s) => `<button data-open="${s.id}"><span>${esc(s.title)}</span><small>${when(s.published)}</small></button>`).join("")}</div>
          <div class="fl-act"><button class="btn ghost">${f.active ? "暂停" : "恢复"}</button><button class="btn ghost">编辑计划</button></div></article>`; }).join("")}</div>`;
    },
    saved() {
      const list = [...S.saved].map((id) => byId[id]).filter(Boolean);
      return head("收藏", `${list.length} 条 · 收藏的事件有新报道时会在这里标出`) +
        (list.length ? `<div class="saved-grid">${list.map((s) => `<article class="sv-card" data-open="${s.id}" style="--tc:var(--t-${s.topic})"><div class="s-meta">${topicTag(s)}<span class="s-src">${srcLine(s)}</span></div><h3>${esc(s.title)}</h3><p>${esc(s.summary)}</p><div class="s-foot"><span class="s-ev">${esc(s.standing || s.evidence)}</span>${saveBtn(s)}</div></article>`).join("")}</div>`
          : empty("还没有收藏", "在简报或详情里点书签图标，内容会留在这里。"));
    },
    library() {
      const groups = { official: "官方", media: "媒体", research: "论文与研究", community: "社区", author: "作者与通讯", search: "搜索" };
      const ok = X.sources.filter((s) => s.status === "ok").length, err = X.sources.filter((s) => s.error).length;
      const by = {}; X.sources.forEach((s) => (by[s.role] = by[s.role] || []).push(s));
      return head("资料库", "订阅来源与最近一次抓取状态") +
        `<div class="stats"><div><b>${X.sources.length}</b><span>订阅来源</span></div><div><b>${ok}</b><span>上次正常</span></div><div><b>${err}</b><span>上次出错</span></div><div><b>${D.counts.materials.toLocaleString()}</b><span>已收材料</span></div><div><b>${D.counts.events}</b><span>事件</span></div></div>` +
        Object.entries(by).map(([role, list]) => sec(groups[role] || role, `${list.length} 个`, `<div class="src-grid">${list.map((s) => `<div class="src"><span class="src-dot ${s.error ? "err" : s.status === "ok" ? "ok" : ""}"></span><b>${esc(s.name)}</b><small>${s.kind.toUpperCase()} · 最近 ${s.count ?? 0} 条 · ${s.at ? when(s.at) : "未抓取"}</small></div>`).join("")}</div>`)).join("");
    },
    story(id) {
      const s = byId[id]; if (!s) return empty("找不到这条事件", "");
      const days = {}; const t0 = s.timeline.find((t) => t.at)?.at;
      s.timeline.forEach((t) => { const d = t.at && t0 ? Math.round((day0(t.at) - day0(t0)) / 864e5) : "?"; (days[d] = days[d] || []).push(t); });
      const tl = Object.entries(days).reverse().map(([d, list]) => `<li class="tl-day"><div class="tl-h"><b>D${d}</b><span>${list[0].at ? md(list[0].at) : "日期待核对"} · ${list.length} 篇</span></div>
        ${list.slice().reverse().map((t) => `<div class="tl-item" data-stage="${t.stage}"><i></i><div><small><em>${esc(t.label)}</em> · ${esc(t.source)} · ${t.at ? t.at.slice(11, 16) : ""}</small><p>${esc(t.title)}</p></div></div>`).join("")}</li>`).join("");
      const ids = stories.map((x) => x.id), i = ids.indexOf(id);
      return `<div class="reader" style="--tc:var(--t-${s.topic})">
        <div class="r-bar"><button class="btn ghost" data-back>${icon.back}<span>返回</span></button><span class="r-pos">${i + 1} / ${ids.length}</span>
          <button class="icon-btn" data-open="${ids[Math.max(0, i - 1)]}" aria-label="上一条">${icon.back}</button><button class="icon-btn" data-open="${ids[Math.min(ids.length - 1, i + 1)]}" aria-label="下一条">${icon.arrow}</button></div>
        <div class="r-meta">${topicTag(s)}${flagTag(s)}<span class="s-src">${esc(s.source)} · ${when(s.published)}</span></div>
        <h1>${esc(s.title)}</h1>
        <p class="r-sum">${esc(s.summary)}</p>
        <div class="r-why"><span>为什么值得读</span><p>${esc(s.reason)}</p></div>
        <div class="r-acts"><button class="btn${S.saved.has(s.id) ? " on" : ""}" data-save="${s.id}" aria-pressed="${S.saved.has(s.id)}">${S.saved.has(s.id) ? icon.saved : icon.save}<span>${S.saved.has(s.id) ? "已收藏" : "收藏"}</span></button>
          <button class="btn${S.known.has(s.id) ? " on" : ""}" data-known="${s.id}" aria-pressed="${S.known.has(s.id)}">${icon.check}<span>已了解</span></button>
          <button class="btn" data-act="follow-story">追踪后续</button>${s.url ? `<a class="btn ghost" href="${esc(s.url)}" target="_blank" rel="noopener">原文 ${icon.arrow}</a>` : ""}</div>
        <div class="r-grid">${evChart(s)}
          <div>${s.claims.length ? `<section class="r-sec"><h3>原文要点</h3><ul class="r-list">${s.claims.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></section>` : ""}
          ${s.limitations.length ? `<section class="r-sec"><h3>尚未说明</h3><ul class="r-list muted">${s.limitations.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></section>` : ""}
          <section class="r-sec"><h3>证据状态</h3><p class="r-standing">${esc(s.standing || s.evidence)}</p></section></div>
          <section class="r-sec"><h3>报道经过 · ${s.timeline.length} 篇</h3><ol class="tl">${tl}</ol></section>
        </div></div>`;
    },
  };

  /* ---------- router + transitions ---------- */
  const pages = ["briefing", "trends", "search", "following", "saved", "library"];
  const parse = () => { const h = location.hash.slice(1); if (h.startsWith("story/")) return ["story", decodeURIComponent(h.slice(6))]; return [pages.includes(h) ? h : "briefing"]; };
  let first = true;
  function render() {
    const [page, arg] = parse();
    if (page !== "story") S.from = page;
    const view = $("#view"), scroller = $("#scroller") || document.scrollingElement;
    const paint = () => {
      view.innerHTML = views[page](arg);
      view.dataset.page = page;
      scroller.scrollTop = 0;
      navState(page === "story" ? S.from : page);
      after(page);
      view.classList.remove("out"); view.classList.add("in");
      clearTimeout(view._t); view._t = setTimeout(() => view.classList.remove("in"), 900);
      document.title = `Northing Signal · ${({ briefing: "简报", trends: "动向", search: "搜索", following: "追踪", saved: "收藏", library: "资料库", story: "阅读" })[page]}`;
    };
    if (first) { first = false; paint(); return; }
    view.classList.add("out"); setTimeout(paint, 170);
  }
  function navState(page) {
    document.querySelectorAll("#drawer [data-page]").forEach((b) => {
      const sub = b.hasAttribute("data-coid");
      b.toggleAttribute("aria-current", sub ? page === "trends" && b.dataset.page === "trends" && b.dataset.coid === S.co : b.dataset.page === page);
    });
    document.querySelectorAll("#drawer nav").forEach((nav) => {
      const ind = nav.querySelector(".nav-ind"); if (!ind) return;
      const cur = nav.querySelector("[data-page][aria-current]");
      if (cur) { ind.style.transform = `translateY(${cur.offsetTop}px)`; ind.style.height = cur.offsetHeight + "px"; ind.style.opacity = 1; } else ind.style.opacity = 0;
    });
    document.querySelectorAll("[data-badge=saved]").forEach((b) => (b.textContent = S.saved.size || ""));
    document.querySelectorAll("[data-badge=new]").forEach((b) => (b.textContent = changed.length));
  }
  function after(page) {
    const ti = $(".tab-ind"), ts = $('.tab[aria-selected="true"]');
    if (ti && ts) { ti.style.left = ts.offsetLeft + "px"; ti.style.width = ts.offsetWidth + "px"; }
    if (page === "search") { const q = $("#q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
    document.querySelectorAll(".rk-bar i").forEach((i, k) => setTimeout(() => i.classList.add("go"), 120 + k * 50));
    if (page === "story") bindChart();
  }
  const go = (h) => { if (location.hash.slice(1) === h) render(); else location.hash = h; };
  addEventListener("hashchange", render);

  /* ---------- events ---------- */
  let tt;
  const toast = (t) => { let el = $("#toast"); if (!el) { el = document.createElement("div"); el.id = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); } el.textContent = t; el.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 1900); };
  const rerender = () => { const v = $("#view"), y = ($("#scroller") || document.scrollingElement).scrollTop; const [p, a] = parse(); v.innerHTML = views[p](a); after(p); ($("#scroller") || document.scrollingElement).scrollTop = y; navState(p === "story" ? S.from : p); };
  document.addEventListener("click", (e) => {
    const t = e.target;
    const nav = t.closest("#drawer [data-page]");
    if (nav) { S.co = nav.dataset.coid || null; if (S.co) S.lens = "company"; if (nav.dataset.coid !== undefined || parse()[0] !== nav.dataset.page) return go(nav.dataset.page); return go(nav.dataset.page); }
    if (t.closest("[data-collapse]")) { document.documentElement.classList.toggle("collapsed"); setTimeout(() => navState(parse()[0] === "story" ? S.from : parse()[0]), 360); return; }
    const sv = t.closest("[data-save]");
    if (sv) { e.stopPropagation(); const id = sv.dataset.save; S.saved.has(id) ? S.saved.delete(id) : S.saved.add(id); toast(S.saved.has(id) ? "已收藏" : "已取消收藏"); return rerender(); }
    const kn = t.closest("[data-known]");
    if (kn) { const id = kn.dataset.known; S.known.has(id) ? S.known.delete(id) : S.known.add(id); persist(); toast(S.known.has(id) ? "已了解，列表里这条会变灰" : "已撤销"); return rerender(); }
    if (t.closest("[data-back]")) { return history.length > 1 ? history.back() : go(S.from); }
    const op = t.closest("[data-open]"); if (op) return go("story/" + encodeURIComponent(op.dataset.open));
    const tp = t.closest("[data-topic]"); if (tp) { S.topic = tp.dataset.topic; return rerender(); }
    const ln = t.closest("[data-lens]"); if (ln) { S.lens = ln.dataset.lens; S.co = null; return rerender(); }
    const rk = t.closest("[data-rank]"); if (rk) { S.rank = +rk.dataset.rank; return rerender(); }
    const co = t.closest("[data-co]"); if (co) { S.co = co.dataset.co || null; const v = $("#view"); v.classList.add("out"); setTimeout(() => { rerender(); ($("#scroller") || document.scrollingElement).scrollTop = 0; v.classList.remove("out"); v.classList.add("in"); setTimeout(() => v.classList.remove("in"), 900); }, 170); return; }
    const sq = t.closest("[data-q]"); if (sq) { S.q = sq.dataset.q; return rerender(); }
    const act = t.closest("[data-act]");
    if (act) {
      const k = act.dataset.act;
      if (k === "follow-story") return toast("已生成追踪草稿，确认后才开始追踪");
      if (k === "new-follow") { const n = $(".fl-new"); n.hidden = !n.hidden; if (!n.hidden) $("input", n).focus(); return; }
      if (k === "update") return update(act);
      if (k === "deck") return toast("快速翻阅：逐张浏览未读事件（右滑收藏、左滑已了解、上滑展开），见 DESIGN.md");
    }
  });
  document.addEventListener("input", (e) => {
    if (e.target.id !== "q") return;
    S.q = e.target.value; const tmp = document.createElement("div"); tmp.innerHTML = views.search(); $("#results").replaceWith($("#results", tmp));
  });
  addEventListener("keydown", (e) => {
    if (e.target.matches("input,textarea")) { if (e.key === "Escape") e.target.blur(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); return go("search"); }
    if (e.key === "[") return document.querySelector("[data-collapse]")?.click();
    const n = +e.key; if (n >= 1 && n <= 6) return go(pages[n - 1]);
    if (e.key === "Escape" && parse()[0] === "story") return go(S.from);
  });
  function update(btn) {
    const box = $(".v-progress"); if (!box || btn.disabled) return;
    btn.disabled = true; box.hidden = false; let n = 0;
    const iv = setInterval(() => {
      n++; $(".v-progress-t").textContent = n <= 74 ? `正在检查订阅来源 ${n}/74` : `正在整理材料 ${n - 74}/12`;
      $(".v-progress b").style.width = (n / 86) * 100 + "%";
      if (n >= 86) { clearInterval(iv); box.hidden = true; btn.disabled = false; toast("简报已是最新（样稿模拟，未请求服务）"); }
    }, 30);
  }

  window.App = { S, stories, go, render, toast };
  const boot = () => { render(); requestAnimationFrame(() => document.documentElement.classList.add("ready")); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  if (document.fonts) document.fonts.ready.then(() => navState(parse()[0] === "story" ? S.from : parse()[0]));
})();
