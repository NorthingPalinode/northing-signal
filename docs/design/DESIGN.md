# DESIGN.md — Design System Contract

Locked 2026-11-25 from the approved HTML direction. Every page and component follows this file; tokens live in `frontend/src/tokens.css` and nowhere else.

## 1. Visual Source of Truth
- **Approved HTML Reference**: [`preview/northing-signal.html`](preview/northing-signal.html) (open in a browser; data is a local snapshot of 2026-11-24).
- **Direction**: "雾面" — a calm desktop-app feel. A soft, almost neutral wallpaper; a translucent left drawer sitting directly on it; content in one floating white window. Colour comes from content (topic dots, company brand tints, evidence marks), not from chrome.
- **Blended traits** (user choice, 2026-11-25): J's palette and drawer, without macOS window dots; B's evidence swimlane chart on the story page; G's card swipe as a small 快速翻阅 feature, never the home page; company 动向 as large logo cards without small-print descriptions.

## 2. Color Tokens
| Role | Token | Light | Dark | Usage Rule |
| :--- | :--- | :--- | :--- | :--- |
| Wallpaper | `--wall-*` | `#dfe3e8 → #e9e2d8 → #d6ded6` + 3 blurred blobs | `#0e1013 → #14161a` + dim blobs | Behind drawer and window only |
| Window | `--win` | `rgb(255 255 255 / 88%)` | `rgb(22 24 28 / 90%)` | The one content panel |
| Surface | `--surface` | `#ffffff` | `#1c1f24` | Cards, lists, inputs |
| Subtle surface | `--surface-2` | `#f7f8fa` | `#22262c` | Row hover |
| Well | `--well` / `--well-2` | `#f2f3f5` / `#e9ebef` | `#262a31` / `#2e333b` | Segmented tracks, chips, quiet fills |
| Primary text | `--ink` | `#1b1e24` | `#eceef1` | Headings, body (≥ 12:1) |
| Secondary text | `--ink-2` | `#4a505b` | `#b5bac3` | Summaries (≥ 7:1) |
| Muted text | `--muted` | `#677079` | `#949aa4` | Meta, timestamps (≥ 4.5:1 on surface) |
| Faint | `--faint` | `#a9aeb7` | `#5c626b` | Decoration only, never text |
| Hairline | `--line` / `--line-2` | ink at 8% / 14% | white at 8% / 14% | Dividers, card edges |
| Accent | `--accent` | `#2f63f0` | `#7097ff` | Primary button, active nav icon, links, official evidence |
| Accent soft | `--accent-soft` | accent at 9% | accent at 15% | Selected chips, badges |
| OK / Warn / Danger | `--ok` `--warn` `--danger` (+ `-text`) | `#0e9f78` `#c27a06` `#d9482b` | `#3fd0a0` `#e8a93b` `#ff7a5c` | Status and evidence only; text uses the `-text` shade |
| Topics | `--t-models` … `--t-industry` | violet, green, amber, blue, pink, orange-red | lighter shades | Topic dot and label only |

**Theme switching** (2026-11-25): 浅色 / 深色 / 跟随系统 (default). The dark palette lives under `:root[data-theme="dark"]` in `tokens.css`; an inline script in `index.html` sets `data-theme` (and the browser bar colour) before the first paint from `localStorage["ns-theme"]`, so a forced theme never flashes. `theme.ts` applies changes with a short view-transition cross-fade (instant under reduced motion) and, in 跟随系统, follows the system live. The choice is per device, not per account. The switch is a three-way segmented control at the bottom of the drawer.

Evidence marks (story chart, stage list, roadmap nodes): official/paper text = accent filled square · test = ink triangle · coverage = hollow ink-2 circle · opinion = small faint dot · correction = danger diamond.

## 3. Typography System
- **Family**: system UI stack with Inter first — `Inter, -apple-system, "Segoe UI Variable", "PingFang SC", "Microsoft YaHei UI", "Noto Sans SC", system-ui, sans-serif`. No remote font loading (the app runs locally and offline; no third-party requests).
- **Numbers**: `font-variant-numeric: tabular-nums` for counts, times, rankings.
- **Mono**: `"JetBrains Mono", "Cascadia Code", Consolas, monospace` for repository names and queries.
- **Scale**: H1 34/1.15 w700 −0.025em · Story H1 32/1.3 w700 · H2 19 w700 −0.015em · Card title 17 w600 · Lead title 26 w700 · Body 14.5/1.6 · Reading body 16.5/1.85 · Small 12.5 · Micro 11.5.

## 4. Layout, Spacing & Surface Rhythm
- **Shell**: wallpaper → drawer (264px, transparent, on the wallpaper) → window (margin 10px, radius `--r-win` 16px). Content column max 1040px, reading column max 820px, padding 40px/52px desktop, 16px phone.
- **Spacing**: 4px grid; card padding 16–26px; section gap 44px; list rows 13–14px vertical.
- **Radius**: `--r-sm` 8px (chips, icon buttons) · `--r-md` 11px (buttons, inputs, list containers) · `--r-lg` 16px (cards) · `--r-xl` 20px (company cards, deck cards) · `--r-win` 16px.
- **Elevation**: border-first. `--shadow-card` (hairline + 1–3px blur) at rest; `--shadow-hover` (deep soft drop) only on clickable cards; `--shadow-pop` for dialogs, toasts, the peeking drawer. No shadow on static text blocks. Never nest a card inside a card: inside a card use wells or hairlines.

## 5. Navigation, Iconography & Imagery
- **Drawer groups**: search field (`/`) · 阅读 (今日简报、动向、追踪、收藏、资料库) · 公司动向 (the reader's own list, up to 8 in their order, saved in preferences as `drawer_companies`; default the 4 with most moves; real logo + count, opens the roadmap; a pencil beside the label, shown on hover, opens the 编辑公司动向 sheet) · 追踪话题 (unread count) · 工具 at the bottom (过去的简报、导出周报、来源状态、阅读偏好、账号) · next automatic update. Active item: white pill with soft shadow that slides (`--spring`). `[` hides the drawer; a hidden drawer peeks as a floating glass panel when the pointer reaches the left edge. Phones: the drawer is an overlay opened from the window bar, plus a bottom tab bar.
- **Icons**: one set — `Glyph` in `ui.tsx`, 24px grid, 1.7px stroke, round caps. No emoji.
- **Company logos**: `CompanyLogo.tsx` vector marks in brand colour; cards tint their corner with the brand at ≤ 16%.

## 6. Motion Tokens
- **Easing**: `--ease: cubic-bezier(.2,.8,.2,1)`; `--spring: cubic-bezier(.34,1.4,.64,1)` for indicators and toasts only.
- **Durations**: `--fast` 140ms (hover, press) · `--base` 220ms (tabs, menus, view swap) · `--slow` 380ms (drawer, dialogs, deck fly-out).
- **View change**: content fades out 140ms, new content rises 10px with a 40ms stagger (max 5 steps).
- **Signature moments (only these three)**: the sliding drawer indicator; evidence-chart marks arriving left to right on open; 快速翻阅 page turn (the card slides out left for 下一张, the previous card slides back in from the left).
- **Reduced motion**: `prefers-reduced-motion: reduce` removes travel and stagger; state changes stay instant.

## 7. Component Conventions
- **Buttons**: `r-button` (white, hairline) · `.primary` (accent) · `.quiet` (no fill) · `.danger` text. Height 34px, icon 15–16px.
- **Segmented / chips**: grey track (`--well`) with a white selected pill; used for topic filters, lenses, library status, report range.
- **Story card**: topic label (coloured text on a soft tint) · badges · title · summary (2–3 lines) · "值得读" well · footer with evidence standing and icon actions. Lead card spans the full width.
- **Company card**: logo tile 56px, name, move count (large), `+N 新` if fresh. No product summary, no latest titles, no timestamps.
- **Evidence chart**: on every story page, right after 为什么值得读, even with a single report (a note says later coverage lands on the same chart). Header row: "证据时间线 · N 篇报道，M 个来源" left, legend right. The time axis runs from the first report's day (at least two days before today) to "现在" at the right edge, never into empty future days. Drawn in pixels at the measured width: the source column is pinned and only the days scroll on narrow screens, opened at "现在". The tooltip lives outside the scrolling frame and flips above or below the mark; the plot is memoised so hovering re-renders only the tooltip. One lane per source (max 8, rest grouped), one column per day, dashed accent line at the official text, danger line at "现在", hover tooltip with source, label, time and title; followed by the four-item checklist row (the only checklist on the page).
- **快速翻阅 (QuickDeck)**: modal card stack of at most 30 unread briefing stories (top three first), dealt once when opened. The bar holds exactly three buttons: 上一张 · 打开这张 (accent) · 下一张. Swipe left / → = next, swipe right / ← = previous, Enter = open, S = 收藏. 收藏 is a chip on the card's coloured band (white chip, `--on-chip` text, green when saved). Progress segments on top (seen, current, saved in green); after the last card a summary offers 从第一张再看 / 回到简报. Turning pages marks nothing; only opening a story counts as reading it.

## 8. Implementation Notes (synced after the browser audit, 2026-11-25)
- The page scrolls the document, not the window panel, so scroll restoration and exposure tracking keep working; the drawer is `position: sticky`.
- The window has no `backdrop-filter` and the wallpaper does not drift (2026-11-25): the window is as tall as the page, so blurring it while 70px-blurred blobs moved behind repainted everything every frame and made hover and scroll stutter. The blobs are already blurred, so the 88% window looks the same. Backdrop blur stays only on small surfaces (window bar, toasts, peeking drawer, sheets). A filter on the window would also become the containing block of the fixed reader action bar on phones.
- The right rail was removed; its parts moved to the drawer (follows, saved count, source status), the page header (counts, update times) and the library stats row.
- Verified at 375 / 768 / 1024 / 1440 px, light and dark, with no horizontal page overflow.
- Company roadmaps group nodes by publication day (`lineDays`), newest first; stories without a publication date close the line under one 发布日期未知 heading, never under their collection day (that repeated day headings and broke React keys).
- The drawer pill is measured against `.r-drawer-nav` with bounding boxes, not `offsetTop` (each group is positioned). A company outside the drawer's four keeps 动向 highlighted.

## 9. Anti-Patterns (Never Do in This Project)
- [ ] No macOS traffic-light dots or other operating-system costume.
- [ ] No small-print descriptions on company cards (product lists, latest titles, "最近 …" timestamps).
- [ ] No emoji as UI icons; no mixed icon stroke weights.
- [ ] No cards nested in cards; no triple borders.
- [ ] No ad-hoc hex colours outside `tokens.css` (company brand colours come from `CompanyLogo.tsx`).
- [ ] No purple-to-blue gradients, gradient text or glowing neon edges.
- [ ] No confidence scores or percentages for evidence; use the plain labels above.
- [ ] No autoplaying or looping motion, the wallpaper included; no `backdrop-filter` on page-tall surfaces.
- [ ] The card swipe is never the home page.
