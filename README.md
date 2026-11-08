# CFAW News

面向 AI 读者的本机个人情报空间：从公开材料中整理值得知道的变化，减少重复报道、无关消息和只有标题的噪声，并保留原始出处与判断边界。

[![starter-checks](https://github.com/V-Giotto/cfaw-news/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/V-Giotto/cfaw-news/actions/workflows/ci.yml)

当前采用独立的 Python / React 内容引擎。默认入口已从旧目标工作台切换到阅读器；旧个人数据库与历史研究材料保留，未自动迁移或删除。

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

固定订阅池目前包含 12 个官方、研究、媒体、技术作者和开源发布来源，配置见 [briefing_sources.json](data/briefing_sources.json)。另有九类可选检索入口：

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

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，点击“更新情报”。每次更新按有限批量执行并可取消；未完成的材料保留待处理状态。用户主动访问，没有站外通知或自动替用户操作第三方系统。

## 模型与可选接口配置

在本项目 `.env` 中填写自己的兼容 Chat Completions 接口；已有 `.env` 不要用模板覆盖。

```dotenv
LLM_MODE=compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model
```

默认 `LLM_MODE=baseline` 不调用联网模型。阅读器仍能保存原始材料，但会明确显示尚未整理；AI 意图理解和相关性判断需要配置模型，不用关键词规则冒充模型理解。

**每日模型调用次数与 Token 总量默认均不设上限**，继续记录实际用量。单次工作批量、请求超时和来源接口的限速仍保留；供应商计费与限流由供应商决定。没有可靠定价资料时只显示次数与 Token，不估造费用。

| 可选配置 | 用途 |
|---|---|
| `READER_WEB_API_KEY` | 本项目自己的 AnySearch 密钥；留空时匿名访问，受提供方限额约束 |
| `READER_OPENALEX_API_KEY` | 本项目自己的 OpenAlex 密钥；留空时使用匿名基础接口 |
| `READER_X_BEARER_TOKEN` | 自有授权的 X 应用 Bearer Token；不配置时仅检索公开网页线索 |

不读取其他项目的密钥、浏览器 Cookie 或私人账户内容。模型理解需求时会接收所提交的描述；内容整理和相关性判断会向配置的模型发送相应材料节选与确认意图。来源检索只发送所选方向的检索词。

## 验证与开发

Windows 日常检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

其他环境或分步运行：

```bash
. .venv/bin/activate
python -m ruff check backend tests_reader
mkdir -p .tmp
python -m pytest -q --basetemp .tmp/reader-check
cd frontend
npm test
npm run build
```

默认 pytest 覆盖当前内容引擎和共用公网读取边界。CI 使用同一范围，并运行既有前端纯函数检查与构建；合成测试不是实网模型或真人阅读效果证明。历史研究测试保留显式入口 `pytest tests` 或 `scripts/verify.ps1 -Legacy`，不作为新阅读器的默认运行门槛，也不重签旧封存报告。

主要入口是 `backend/cfaw_news/briefing/` 与 `frontend/src/ReaderApp.tsx`。实现、真实开发检查与限制见 [内容引擎说明](docs/CONTENT_ENGINE.md)；范围和后续方向见 [开发计划](docs/plans/AI_INFORMATION_QUALITY_IMPLEMENTATION_PLAN.md)。

## 数据与当前限制

- 当前是本机单用户开发版，不提供生产鉴权、公网部署或多用户隔离。
- 数据默认保存在 `.local/briefing-v2.db`；旧个人库与 `data/archive/articles.json` 的迁移出处保留。
- 事件聚合使用具体事件框架和原文指纹；跨语言去重、长尾召回与摘要语义仍可能出错，尚未实现向量检索。
- 真实材料、AI 开发标签、合成样例与用户反馈分开记录；小样本结果不等于独立研究结论或普遍准确率。
- `.env`、`.local/`、`.tmp/`、虚拟环境、依赖、生成的 `frontend/dist/` 和 `dev-diaries/` 均不提交 Git。开发日记与私人数据永远仅保留在本地。
- 能抓到公开内容不代表拥有全文再分发权限；当前保存必要节选和出处，没有对外全文发布服务。

代码许可：[Apache-2.0](LICENSE)；第三方资产见 [NOTICE](NOTICE)。旧 G1–G4 文档保留其原始研究与验收含义，不作为新内容引擎已实现能力或质量提升的证明。
