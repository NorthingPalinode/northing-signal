# PRODUCT.md — Northing Signal

Stage 0 of the UI/UX workflow (2026-11-25). Visual decisions live in [DESIGN.md](DESIGN.md).

## 1. Product Identity
- **Product Name**: Northing Signal
- **One-Sentence Pitch**: A personal AI news briefing that says what changed since you were last here, why it matters and what evidence stands behind it.
- **Platform & Tech Stack**: Web first (desktop browser); React 19 + Vite, hand-written CSS tokens, FastAPI backend at `/api/reader`. Phones get the same app with an overlay drawer.
- **Project Category**: Personal AI information tool (reading app, not a dashboard).

## 2. Target Audience & Context
- **Primary User Persona**: One technical reader (and a few invited accounts) who follows AI models, agents, research and industry moves daily; Chinese UI, English sources.
- **Usage Environment**: Desktop browser, visited voluntarily one to three times a day; no out-of-app notifications. The briefing updates itself at 00:00 and 12:00 while the service runs.
- **Desired Emotional Tone**: Calm, exact, trustworthy. Evidence is stated plainly (official text, vendor test, others' report, opinion), never as a confidence score.

## 3. Core User Flows (Jobs to Be Done)
1. **Primary — catch up**: open 今日简报 (one edition) → the masthead says when you were last here and what changed (新 / 更正 / 新测试 / 有更新 / 新报道) → read the lead and the three highlights, each with why it matters and its evidence → skim the topic columns and 快讯 → "距你上次来的变化，就这些" → open a story for its evidence timeline → mark known / save / follow.
2. **Quick pass**: 快速翻阅 → page through today's unread stories (上一张 / 打开这张 / 下一张; swipe or ← → also turn pages; 收藏 on the card) → done. Turning a page marks nothing.
3. **Look into a company or lens**: 动向 → company card (logo, move count) → the company's line, grouped by day and product.
4. **Follow a topic**: describe it in one sentence → review the AI's plan → confirm → new matches appear under 追踪.
5. **First run**: empty briefing → 立即更新 → progress (checking 74 sources, understanding N materials) → briefing.

## 4. Information Architecture & Screen Priority
| Screen / Route | Primary Goal (One Thing) | Key Modules | Primary CTA |
| :--- | :--- | :--- | :--- |
| `#briefing` 今日简报 | Know what changed since the last visit, why, and on what evidence | masthead and change summary, lead, 今日看点, topic columns, 之前的事有了新进展, 快讯, ending with 全部进展 | 更新 / 快速翻阅 |
| `#story/<id>` 阅读 | Judge one event and its evidence | summary, why, evidence chart + checklist, stage list, claims, limits | 收藏 / 已了解 |
| `#trends` 动向 | See who moved | lens tabs; company logo cards; company line; GitHub rankings | open a company |
| `#discover` 搜索 | Find in what is collected, then outside | search box, external search, results | 到外部搜索 |
| `#following` 追踪 | Watch confirmed topics | topic list, plan, matched events | 新增追踪 |
| `#saved` 收藏 | Re-read kept stories | topic chips, saved list | — |
| `#library` 资料库 | Inspect raw materials and their status | filter, status segments, materials | 重新整理 (admin) |

Navigation is a left drawer on the web: 阅读 group (简报、动向、搜索、追踪、收藏), pinned companies, followed topics, and tools (资料库、过去的简报、导出周报、来源状态、阅读偏好、账号). It hides completely and peeks from the left edge.

## 5. Real Copy & Domain Data Seed
- **Headline**: 今日简报 · 11月25日 星期三 · 更新于 01:43 · 下次自动 12:00
- **Change line**: 距你上次来，有 9 件事变了（上次 11月23日 23:46）
- **Top three (real, 2026-11-24 snapshot)**: Anthropic 研究员坚持 AI 辅助黎曼猜想证明，承认发布过程有“蠢事”（含更正，3 个来源）; 英伟达董事会恢复黄仁勋总裁、CEO及董事职务（官方新闻稿，8 个来源，33 篇报道）; Bonbon：分子相互作用基础模型的零样本涌现能力（论文自报结果）.
- **Evidence labels**: 官方原文 · 论文原文 · 厂商自测 · 他方报告的测试 · 媒体转述 · 作者观点 · 更正.
- **Companies**: NVIDIA 18 · OpenAI 11 · Anthropic 9 · Amazon 4 · xAI 3 · 蚂蚁集团 3.
- **Primary CTA**: 更新 · **Secondary**: 快速翻阅 · 追踪后续.

## 6. Hard Constraints
- **Accessibility**: WCAG AA contrast, keyboard (J/K, Esc, `[` drawer, `/` search), visible focus, `prefers-reduced-motion`.
- **Themes**: light and dark (system), Simplified Chinese.
- **Domain rules the UI must keep**: no autonomous actions; opening a story marks it known once; tracking starts only after explicit confirmation; reader actions are append-only toggles; public digest shows no reader data; split/merge/retry are admin-only.
