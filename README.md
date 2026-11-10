# CFAW News

面向重度 AI 读者的本机事件追踪阅读器：聚合发布、文中测试与更正，帮助你查看具体变化、原始出处，以及宣称的依据与边界。

[![starter-checks](https://github.com/V-Giotto/cfaw-news/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/V-Giotto/cfaw-news/actions/workflows/ci.yml)

当前采用独立的 Python / React 内容引擎。旧版目标工作台与 G1–G4 研究材料已从主分支移除，保存在 [`archive/research-g1-g4`](https://github.com/V-Giotto/cfaw-news/tree/archive/research-g1-g4) 分支；旧个人数据库未自动迁移或删除，可以用 `scripts/export_legacy.py` 导出。

当前版本已接入 **45 个固定来源入口 + 9 类可选主动检索**，支持事件聚合与报道时间线、原文依据、自然语言确认追踪、收藏和阅读反馈。来源宣称、文中测试、公开榜单与本项目独立实测分别看待；当前没有开展本项目独立模型复测。

## 可以做什么

| 页面 | 用途 |
|---|---|
| 我的简报 | 汇总重要事件、具体变化、阅读价值与原文依据，支持阅读偏好、反馈与历史简报 |
| 发现 | 按 AI 方向浏览，搜索已有资料，或选择公开来源主动检索新材料 |
| 关注 | 用自然语言描述需求，核对 AI 理解与检索方案，确认后持续追踪；集中查看收藏 |
| 资料库 | 检索原始材料，区分已整理内容与尚待获取正文的线索 |

话题追踪遵循 **描述需求 → AI 理解意图 → 纠正或编辑方案 → 用户确认 → 定期检索与相关性判断**。确认前不启动搜索；修改范围也需要重新确认。频率可选约每 30 分钟、2 小时、每天或每周，仅在本地服务运行期间执行，可暂停、恢复或取消。

卡片正文与空白区域均可打开详情；收藏和反馈按钮独立响应。打开不等于“已了解”，收藏保留当时版本。系统区分来源陈述、文中报告的测试与作者观点，搜索摘要不冒充原文，模型解释不冒充独立验证。

## 信息来源

固定来源池已从 12 个扩展为 45 个入口，按核心与补充来源排列。配置见 [briefing_sources.json](data/briefing_sources.json)，完整清单、逐源检查与按重要性排列的受限项见 [来源接入说明](docs/SOURCES.md)。

| 固定来源类型 | 数量 | 代表来源与材料 |
|---|---:|---|
| 官网发布与更新日志 | 8 | Anthropic、DeepSeek、Kimi、MiniMax、ByteDance Seed、Meta、xAI、Mistral |
| 开源版本 | 8 | vLLM、SGLang、llama.cpp、Ollama、Transformers、LangGraph、Kimi Code、Claude Code |
| 模型目录与模型卡 | 10 | 九个 Hugging Face 官方组织，以及 ModelScope 的 Qwen 公开目录 |
| 论文发现 | 2 | arXiv 分类查询、Hugging Face Daily Papers |
| 评测数据与项目更新 | 3 | Arena 文本榜、SWE-bench Verified；LiveBench 当前仅更新记录 |
| RSS / Atom | 14 | OpenAI、Google DeepMind、研究机构、Simon Willison、Interconnects、Latent Space、量子位等 |

这些是入口数量，不等于独立发布方数，也不代表完整或持续覆盖。另有以下九类主动检索入口，与固定池另计：

| 检索入口 | 覆盖与边界 |
|---|---|
| 网页搜索 | 通过 AnySearch 发现官方发布、文档、技术文章与评测；摘要先作线索，补读原文后再整理 |
| arXiv | 研究预印本与摘要，不代表同行评审或结论已验证 |
| GitHub | 开源项目与有限 README 节选，热度不作为质量证明 |
| Hugging Face | 模型仓库与模型卡，仓库更新时间不当作模型发布日期 |
| OpenAlex | 跨期刊、会议的研究索引与收录摘要，明确区分索引摘要和论文全文 |
| Hacker News | 开发者分享与讨论线索，社区提交时间不当作外链原文发布时间 |
| X / Twitter | 默认检索公开网页中的帖子线索；可选接入自有授权的官方近期帖子 API |
| 抖音 | 公开网页索引中的视频、图文线索，尚未接入站内原生搜索或视频字幕 |
| 小红书 | 公开网页索引中的笔记线索，尚未接入站内笔记搜索或登录正文 |

三家社交平台当前默认采用无需账号或原生 API 授权的公开检索。只有链接或摘要的条目标为“搜索线索 · 正文待获取”，不会生成仿佛已看过全文或视频的事实卡片。视频、音频、图片内容理解尚未实现；公开索引不保证全量、实时覆盖。来源状态会分别显示成功、无结果和失败，单个来源故障不阻断其他来源。

官网列表先收录为线索，补读原文后再整理；固定模型目录每批最多读取一份公开模型卡，不获取权重或受限文件。Arena 文本榜与 SWE-bench 结果以“公开榜单数据”展示有界节选，保留来源条件和核验状态，不代表本项目复测。LiveBench 当前仅接入更新记录；ModelScope 当前仅接入 Qwen 公开目录元数据。

X 原生检索需要自己的应用授权；Artificial Analysis 数据 API 与 OpenReview 尚未接入默认采集。部分厂商官网独有内容、受限全文及当前完整评测榜单仍有缺口，详见来源说明。接口可用性以本机实际检查为准；公开 GET 支持当前环境的 HTTPS 代理，并保留公网地址、TLS 与响应大小边界。

## 启动

需要 Python 3.11+、Node.js 24（CI 使用版本；也支持 Node.js 22.12+）以及 Git。

### Windows / PowerShell

```powershell
git clone https://github.com/V-Giotto/cfaw-news.git
cd cfaw-news
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

启动脚本创建本项目虚拟环境、安装锁定依赖、构建前端并启动本机服务。已有依赖与前端构建时，可使用 `scripts/start.ps1 -SkipInstall`；需要指定 Python 或端口时使用 `-Python`、`-Port`。

### macOS / Linux

```bash
git clone https://github.com/V-Giotto/cfaw-news.git
cd cfaw-news
[ -e .env ] || cp .env.example .env
bash scripts/start.sh
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，点击“更新情报”。每次更新按有限批量执行并可取消；未完成的材料保留待处理状态。刷新、主动检索和话题追踪共用一个后台任务：忙碌时新任务进入队列，手动操作排在定时追踪之前，排队中的任务可以单独取消。用户主动访问，没有站外通知或自动替用户操作第三方系统。

## 模型与可选接口配置

在本项目 `.env` 中填写自己的兼容 Chat Completions 接口；已有 `.env` 不要用模板覆盖。

```dotenv
LLM_MODE=compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model
```

默认 `LLM_MODE=baseline` 不调用联网模型。阅读器仍能保存原始材料，但会明确显示尚未整理；AI 意图理解和相关性判断需要配置模型，不用关键词规则冒充模型理解。

**每日模型调用次数与 Token 总量默认均不设上限**，继续记录实际用量，并按 `READER_TIMEZONE`（默认系统时区）的零点统计每日用量。单次工作批量、请求超时和来源接口的限速仍保留；供应商计费与限流由供应商决定。没有可靠定价资料时只显示次数与 Token，不估造费用。

整理失败的材料不会在每次更新时反复消耗 Token：分别等待 1 小时、6 小时后重试，第三次失败后停止自动重试，可在资料库中点“重新整理”。引文或数字与原文不符这类失败，用同样的提示词重试大概率还会失败，所以直接从 6 小时开始。模型漏掉部分条目时，其余合格结果照常保存。供应商请求失败（网络错误或任何 HTTP 错误状态，如鉴权失败、限流、服务异常）不计入材料的失败次数，本轮停止继续请求。

| 可选配置 | 用途 |
|---|---|
| `READER_WEB_API_KEY` | 本项目自己的 AnySearch 密钥；留空时匿名访问，受提供方限额约束 |
| `READER_OPENALEX_API_KEY` | 本项目自己的 OpenAlex 密钥；留空时使用匿名基础接口 |
| `READER_X_BEARER_TOKEN` | 自有授权的 X 应用 Bearer Token；不配置时仅检索公开网页线索 |
| `READER_REQUESTS_PER_DAY`、`READER_TOKENS_PER_DAY` | 可选的每日模型调用上限；留空不限制 |
| `READER_TIMEZONE` | 每日用量统计所用时区，如 `Asia/Shanghai`；留空使用系统时区 |
| `READER_BATCH_SIZE` | 每次模型请求整理的材料数，默认 4（1–6）；回复被截断时自动对半拆分重试 |
| `READER_FOLLOW_ANALYZE_LIMIT` | 话题追踪每轮最多整理的材料数，默认 6 |
| `READER_MODEL_CONCURRENCY` | 同时进行的模型请求数，默认 1；按供应商限流调整 |

不读取其他项目的密钥、浏览器 Cookie 或私人账户内容。模型理解需求时会接收所提交的描述；内容整理和相关性判断会向配置的模型发送相应材料节选与确认意图。来源检索只发送所选方向的检索词。

## 验证与开发

Windows 日常检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

其他环境或分步运行：

```bash
. .venv/bin/activate
python -m ruff check backend tests_reader scripts
mkdir -p .tmp
python -m pytest -q --basetemp .tmp/reader-check
cd frontend
npm test
npm run build
```

默认 pytest 覆盖内容引擎和公网读取边界（`tests_reader/`）。CI 使用同一范围，并运行前端测试与构建；合成测试不是实网模型或真人阅读效果证明。

主要入口是 `backend/cfaw_news/briefing/` 与 `frontend/src/ReaderApp.tsx`。实现、真实开发检查与限制见 [内容引擎说明](docs/CONTENT_ENGINE.md)；范围和后续方向见 [开发计划](docs/plans/AI_INFORMATION_QUALITY_IMPLEMENTATION_PLAN.md)。

下一轮重点是外部重要事件漏报观察、主张级测试归属、持续事件与回访增量，以及对象快捷关注。它们仍有待实施或验证的部分，不能把计划或一次来源连通检查当作两周覆盖效果与用户收益。

## 数据与当前限制

- 当前是本机单用户开发版，不提供生产鉴权、公网部署或多用户隔离。
- 数据默认保存在 `.local/briefing-v2.db`；旧个人库（`.local/cfaw-news.db`）不自动迁移，可用 `python scripts/export_legacy.py` 只读导出为 JSON Lines。`data/archive/articles.json` 等迁移出处保留。
- 事件聚合使用具体事件框架和原文指纹；跨语言去重、长尾召回与摘要语义仍可能出错，尚未实现向量检索。
- 真实材料、AI 开发标签、合成样例与用户反馈分开记录；小样本结果不等于独立研究结论或普遍准确率。
- `.env`、`.local/`、`.tmp/`、虚拟环境、依赖、生成的 `frontend/dist/` 和 `dev-diaries/` 均不提交 Git。开发日记与私人数据永远仅保留在本地。
- 能抓到公开内容不代表拥有全文再分发权限；当前保存必要节选和出处，没有对外全文发布服务。

代码许可：[Apache-2.0](LICENSE)；第三方资产见 [NOTICE](NOTICE)。归档分支中的 G1–G4 文档保留其原始研究与验收含义，不作为新内容引擎已实现能力或质量提升的证明。
