# 数据源接入、实测与限制

更新：2026-11-08（Asia/Shanghai）。本轮是在用户授权下完成的实际接入，不是仅列候选清单。

## 首轮隔离验证结果

- 固定来源从 **12 个扩展到 45 个入口（新增 33 个）**；原九类主动检索入口继续保留，另计，未把它们算进 45 个成功来源。
- 在隔离临时库逐源实际采集，每源最多 3 条：**45/45 个入口取得可解析材料，共 127 条当前材料**；其中 90 条含正文、摘要或榜单节选，其余为线索/目录元数据。入口数不等于独立发布方数。
- 对 Anthropic、MiniMax、ByteDance Seed、Meta、xAI、Mistral、量子位、Hugging Face 博客各选一份必要原文：**8/8 取得节选**，长度 3511–6000 字符。没有将列表页标题或登录壳当正文。
- 原材料、版本及用量均位于 `.tmp/source-expansion/` 的隔离验证库；没有调用内容模型，没有向个人库写入探测文章，也没有新建关注或通知。采集成功不等于推荐质量、事件召回或摘要语义已经验证。
- 本轮实网使用当前环境的正常 HTTPS 代理；保留公网地址检查、原域名 TLS/Host、允许跳转及响应大小限制。直连环境下部分境外站点失败，换环境需重新检查，不能把本次成功当连续可用承诺。

## 2026-11-24 公司官方来源补充

为「公司动向」按官方来源归类（[计划](plans/LENSES_PLAN.md)），新增 10 个入口，固定来源共 61 个。逐源用项目自己的抓取与解析实测（只读，不写个人库、不调用模型），每源取得 3–5 条带日期的材料：

| 公司 | 新入口 | 接入方式与边界 |
|---|---|---|
| Google | [Google · AI 官方博客](https://blog.google/technology/ai/rss/) | RSS 摘要；Gemini 应用、模型与产品发布。Google Developers Blog 的条目没有日期，接入会被当作旧闻，未接 |
| Microsoft | [新闻中心](https://news.microsoft.com/source/feed/)、[Azure 博客](https://azure.microsoft.com/en-us/blog/feed/) | RSS；新闻中心含 Microsoft AI（MAI）模型发布。`blogs.microsoft.com/ai/feed/` 返回 410 |
| Apple | [机器学习研究](https://machinelearning.apple.com/rss.xml)、[新闻室](https://www.apple.com/newsroom/rss-feed.rss) | RSS；新闻室为综合频道 |
| Amazon | [About Amazon](https://www.aboutamazon.com/news/rss)、[AWS 机器学习博客](https://aws.amazon.com/blogs/machine-learning/feed/) | RSS；AWS 博客含大量使用教程 |
| NVIDIA | [新闻稿](https://nvidianews.nvidia.com/releases.xml) | RSS；与原有 NVIDIA 博客部分重复 |
| 阿里 / Qwen | [阿里云百炼 · 模型发布与更新](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) | 官方更新记录按日期拆分（`updates`，`block: rkb-update`），同日多节合并；含平台上架的第三方模型。`qwenlm.github.io` 博客最后更新于 2025-09，Qwen 官网仍为动态页面 |
| 智谱 | [模型与产品发布记录](https://docs.bigmodel.cn/cn/update/new-releases) | 官方文档更新区块按日期拆分（`updates`）。`z.ai/blog` 与其 RSS 返回 404 |

综合频道（Microsoft 新闻中心、Azure、Apple 新闻室、About Amazon）设置 `require` 关键词规则：标题与摘要不含 AI 相关词的条目在采集时丢弃，不占用模型整理额度。关键词规则可能漏掉措辞特殊的 AI 新闻。

## 2026-11-24 GitHub 开源榜单

「开源与社区」新增 4 个榜单入口（固定来源共 65 个），实测均取得 AI 项目：Trending 今日榜 12 个、本周榜 11 个（每页约 16 个仓库，过滤后保留 AI 相关项目），近 30 天新建 15 个、star 总量 15 个。

- [GitHub Trending](https://github.com/trending) 没有官方接口，解析公开网页（`github_trending`）；GitHub 改版会使解析失效，届时在来源状态中显示为空或失败。
- 近 30 天新建与 star 总量用[官方搜索接口](https://docs.github.com/en/rest/search/search#search-repositories)（`github_search`）。接口不接受主题之间的 OR，按每个主题分别查询再按 star 合并去重。匿名额度较低，可配置 `READER_GITHUB_TOKEN`。实测中曾有一次 `api.github.com` 被本机网络解析到非公网地址而被公网读取边界拒绝，重试即恢复。
- 榜单存放在该来源的状态中（`source_states`），不新增数据表、不生成材料、不调用模型；失败时保留上一次的榜单与时间。
- 2026-11-25 更新：按所有者要求移除 `llama.cpp · 开源发布`（`llamacpp-release`），固定来源入口现为 64 个。

## 按重要性排列的未完成项

| 优先级 | 来源 / 尚缺能力 | 实际限制或观察 | 当前替代与后续条件 |
|---|---|---|---|
| 1 · 核心 | X 原生帖子检索、完整线程及媒体 | 本项目未配置应用 Bearer Token；官方近期检索需要获批应用，当前按量计费。既有公开网页索引不保证实时或完整正文 | 保留索引线索。需要为本项目提供自己的官方授权及可用额度后再验原生路径；不使用浏览器 Cookie 或其他项目密钥 |
| 2 · 核心补证 | Artificial Analysis 数据 API | 对官方免费数据端点的匿名请求实际返回 HTTP 401 | Arena / SWE-bench 已可提供另一类补证。AA 需其账户生成的 API Key，并按实际套餐、归属要求与可用字段接入；本轮未创建账户或调用付费接口 |
| 3 · 研究覆盖 | OpenReview 公开投稿 / 修订 / 评审 | 选定 ICLR 公开 Notes 接口实际返回 HTTP 403；仅凭此不能认定一定需要某种 Key，原因尚未确认 | arXiv 与 HF Daily Papers 已接通，但不能代替评审记录。待确认平台访问条件后复验，不绕过拒绝 |
| 4 · 部分厂商独有信息 | Qwen 官网博客、Z.ai 新闻页的完整持续采集 | Qwen 页面为动态壳；尝试其公开 article 列表得到空数据，尚未形成稳定文章入口。所试 Z.ai 新闻路径返回 404 | Qwen / GLM 官方 HF 目录与模型卡已接，另有 Qwen ModelScope 目录；官网独有的闭源/API 公告仍可能遗漏，需要核实稳定官网路径或公开接口 |
| 5 · 完整评测覆盖 | LiveBench 当前完整榜单 | 首页为 JS 壳；官方仓库 README 中的静态成绩已旧，不能拿来冒充当前榜单 | 已接官方 changelog，当前最新可读条目为 2026-01-08，并保留该日期，避免当作今天的新事件；当前完整成绩仍待稳定入口 |
| 6 · 中文媒体补充 | 机器之心文章流 / 会员内容 | 本轮首页与 /rss 返回数据服务介绍页，不是可解析的文章 RSS | 量子位公开 RSS 已接。机器之心需进一步确认官方数据服务的接入与内容使用范围，不宣称会员内容已接通 |
| 7 · 部分内容 | Meta Llama 的部分模型卡、ModelScope 全文 | Meta 目录可用，但本次首个卡片补读未成功；ModelScope 本轮只验证并接入 Qwen 元数据目录 | 继续保留目录状态，不以元数据生成事实卡；Meta 官网与 HF 其他公开卡片路径分别解释，不获取受限权重 |
| 8 · 较低 | 抖音、小红书原生搜索与视频/图片理解 | 仍为现有公开网页索引线索，尚无本项目原生授权与可用正文/字幕链路 | 不把视频标题、摘要或登录壳当视频内容；对重度 AI 受众本轮优先级最低 |

X 接入依据：[近期检索](https://docs.x.com/x-api/posts/search/quickstart/recent-search)、[当前计费](https://docs.x.com/x-api/getting-started/pricing)。AA 接入依据：[官方 API](https://artificialanalysis.ai/api-reference)。ModelScope 匿名目录按其[官方 SDK 的公开接口定义](https://github.com/modelscope/modelscope_hub/blob/main/src/modelscope_hub/_openapi.py)验证，未安装会自动载入本机既有 Token 的 SDK。

## 已接入来源，核心优先

以下条数是本轮小批量验证，不是该站全部内容。带文本仍可能只是摘要或节选，不代表模型已经判断或事实已独立证实。官网类在采集时为线索，表中“带文本”含随后选取的原文补读。

| 等级 | 来源 | 接入方式 | 本轮材料 / 带文本 |
|---|---|---|---:|
| 核心 | [OpenAI](https://openai.com/news/rss.xml) | RSS / Atom 节选 | 3 / 3 |
| 核心 | [Google DeepMind](https://deepmind.google/blog/rss.xml) | RSS / Atom 节选 | 3 / 2 |
| 核心 | [vLLM · 开源发布](https://github.com/vllm-project/vllm/releases) | GitHub Releases | 3 / 3 |
| 核心 | [Anthropic · 官网发布](https://www.anthropic.com/news) | 官网列表 → 原文补读 | 3 / 1 |
| 核心 | [DeepSeek · API 更新日志](https://api-docs.deepseek.com/updates/) | 按日期拆分更新日志 | 3 / 3 |
| 核心 | [Kimi · 平台更新日志](https://platform.kimi.com/docs/changelog) | 公开文档节选 | 1 / 1 |
| 核心 | [MiniMax · 研究与发布](https://www.minimax.io/blog) | 官网列表 → 原文补读 | 3 / 1 |
| 核心 | [ByteDance Seed · 官网发布](https://seed.bytedance.com/en/) | 官网列表 → 原文补读 | 3 / 1 |
| 核心 | [Meta AI · 官网发布](https://ai.meta.com/blog/) | 官网列表 → 原文补读 | 3 / 1 |
| 核心 | [xAI · 官网发布](https://x.ai/news) | 官网列表 → 原文补读 | 3 / 1 |
| 核心 | [Mistral · 官网发布](https://mistral.ai/news/) | 官网列表 → 原文补读 | 3 / 1 |
| 核心 | [SGLang · 开源发布](https://github.com/sgl-project/sglang/releases) | GitHub Releases | 3 / 3 |
| 核心 | [Ollama · 开源发布](https://github.com/ollama/ollama/releases) | GitHub Releases | 3 / 3 |
| 核心 | [Transformers · 开源发布](https://github.com/huggingface/transformers/releases) | GitHub Releases | 3 / 3 |
| 核心 | [LangGraph · 开源发布](https://github.com/langchain-ai/langgraph/releases) | GitHub Releases | 3 / 3 |
| 核心 | [Kimi Code · 开源发布](https://github.com/MoonshotAI/kimi-code/releases) | GitHub Releases | 3 / 3 |
| 核心 | [Claude Code · 开源发布](https://github.com/anthropics/claude-code/releases) | GitHub Releases | 3 / 3 |
| 核心 | [Qwen · 模型目录与模型卡](https://huggingface.co/Qwen) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [DeepSeek · 模型目录与模型卡](https://huggingface.co/deepseek-ai) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [Kimi · 模型目录与模型卡](https://huggingface.co/moonshotai) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [GLM / Z.ai · 模型目录与模型卡](https://huggingface.co/zai-org) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [MiniMax · 模型目录与模型卡](https://huggingface.co/MiniMaxAI) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [ByteDance Seed · 模型目录与模型卡](https://huggingface.co/ByteDance-Seed) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [Meta Llama · 模型目录与模型卡](https://huggingface.co/meta-llama) | 模型目录 + 有界公开模型卡 | 3 / 0 |
| 核心 | [Mistral · 模型目录与模型卡](https://huggingface.co/mistralai) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 核心 | [arXiv · AI / 语言 / 学习 / 视觉](https://export.arxiv.org/api/query?search_query=cat%3Acs.AI+OR+cat%3Acs.CL+OR+cat%3Acs.LG+OR+cat%3Acs.CV&sortBy=submittedDate&sortOrder=descending&max_results=12) | 分类查询 API / 索引摘要 | 3 / 3 |
| 补充 | [Google Research](https://research.google/blog/rss/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [Hugging Face](https://huggingface.co/blog/feed.xml) | RSS / Atom 节选 | 3 / 1 |
| 补充 | [Microsoft Research](https://www.microsoft.com/en-us/research/feed/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [NVIDIA](https://blogs.nvidia.com/feed/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [GitHub · AI & ML](https://github.blog/ai-and-ml/feed/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [Berkeley AI Research](https://bair.berkeley.edu/blog/feed.xml) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [TechCrunch · AI](https://techcrunch.com/category/artificial-intelligence/feed/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [The Decoder](https://the-decoder.com/feed/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [Simon Willison](https://simonwillison.net/atom/everything/) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [Hugging Face · Daily Papers](https://huggingface.co/api/daily_papers?limit=8) | 公开 API / 索引摘要 | 3 / 3 |
| 补充 | [Interconnects · Nathan Lambert](https://www.interconnects.ai/feed) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [Latent Space / AI News](https://latent.space/feed) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [量子位 · 公开 RSS](https://www.qbitai.com/feed) | RSS / Atom 节选 | 3 / 3 |
| 补充 | [The Verge · AI](https://www.theverge.com/rss/ai-artificial-intelligence/index.xml) | RSS / Atom 全文 | 8 / 8 |
| 补充 | [Ars Technica · AI](https://arstechnica.com/ai/feed/) | RSS / Atom 全文 | 8 / 8 |
| 补充 | [CNBC · Technology](https://www.cnbc.com/id/19854910/device/rss/rss.html) | RSS 摘要（科技商业综合） | 8 / 0 |
| 补充 | [MIT Technology Review · AI](https://www.technologyreview.com/topic/artificial-intelligence/feed) | RSS / Atom 全文 | 8 / 7 |
| 补充 | [雷峰网](https://www.leiphone.com/feed) | RSS / Atom 全文 | 8 / 8 |
| 补充 | [极客公园](https://www.geekpark.net/rss) | RSS / Atom 全文（科技商业综合） | 8 / 8 |
| 补充 | [Arena · 文本偏好榜单](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset) | 官方文本榜数据节选 | 1 / 1 |
| 补充 | [SWE-bench Verified · 公开结果](https://www.swebench.com/) | 官方 Verified 数据节选 | 1 / 1 |
| 补充 | [LiveBench · 官方更新记录](https://github.com/LiveBench/LiveBench/blob/main/changelog.md) | 官方更新记录 | 1 / 1 |
| 补充 | [Tencent · 模型目录与模型卡](https://huggingface.co/tencent) | 模型目录 + 有界公开模型卡 | 3 / 1 |
| 补充 | [ModelScope · Qwen 公开目录](https://modelscope.cn/models) | 公开目录元数据 | 3 / 0 |

2026-11-24 补充：黄仁勋复任英伟达 CEO 当天，TechCrunch、The Decoder、量子位都已采集，却因相关性规则把产业新闻判为“与 AI 无关”而未进简报（已修正规则并重判）。同时补入上面六个科技与商业媒体（The Verge、Ars Technica、CNBC、MIT Technology Review、雷峰网、极客公园），固定入口增至 51 个；每源每次最多 8 条。试采时 36 氪与机器之心的 RSS 为空、虎嗅超时、VentureBeat 返回 429，未接入。

## 材料与展示规则

- 官网索引只产生线索；取得必要原文后新建材料版本。标题、搜索摘要、目录元数据不能直接作为已读全文的事实依据。
- 固定 HF 组织每批最多补读一份公开模型卡，只读取公开文本，不读取权重或受限文件；卡片失败时保留目录。显式 HF/GitHub 搜索仍沿用其既有有界 README 读取规则。仓库更新时间与创建时间不冒充模型发布日期。
- arXiv 与 HF Daily Papers 标为索引摘要。arXiv 仅一个分类查询入口；固定采集和主动检索在同一任务循环内串行请求，并共享至少三秒间隔，避免同时启动多个采集进程。不能把今天抓到的旧论文说成今天发布。
- Arena 只接当前 text / overall 的至多 12 行公开数据，保留日期、票数与区间，不宣称全榜覆盖。SWE-bench 只取 Verified 中按提交日期选出的 8 项，保留 checked、系统、条件与警示；提交日期不当成整个榜单的发布日期。
- 榜单以 `benchmark_snapshot` 保存，显示“公开榜单数据”，数据经过结构化选取，不冒充原文叙述或本项目复测。
- 同一主体在官网、GitHub、HF、ModelScope 和媒体的重复材料不是独立支持。45 个入口也不是 45 个彼此独立的发布方。
- Latent Space / AI News 作为一个入口，允许官网的 www/裸域名正常跳转；已迁移的 news.smol.ai 不再重复加入。
- 来源状态显示收录数与带文本数；检查成功可以只是目录可用。真实状态随每次更新变化，验证状态未伪写回个人库。

## 日常使用与验证

2026-11-08 用户进一步要求全部接入实际项目后，已备份本地资料库并重载本机 8000 端口的正式阅读器，确认启动入口加载 45 个固定来源与原九类主动检索。一轮正常刷新（每源最多 3 条、最多整理 12 条）完成，45 个固定来源均成功，11 条整理完成、1 条未通过校验并保留待处理。这是有限的实际运行记录，不是普遍语义质量或召回验证；探测库中的文章未复制进个人库。

已检查旧材料、判断、收藏/交互、偏好、草稿、简报快照与关注配置保留；备份和运行细节仅保存在本地 `.local/`。未新建关注或站外动作。

现在点击“更新情报”，45 个固定来源即参与现有有界刷新。查看“来源与覆盖”可见核心/补充来源、最近检查与材料数量。来源变多不取消单批处理上限，材料可以保留待整理，不自动凑满简报。以后修改采集代码或来源配置时，仍需重载相应服务。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

本轮日常验证：79 passed，Ruff 与前端构建通过；包含新增来源、证据类型、拒绝隔离、时间归属、arXiv 请求节奏与代理拒绝边界的合成回归。浏览器已检查来源面板的实际内容。保留既有 FastAPI/Starlette 测试依赖弃用警告，未把它作为来源失败。真实采集与合成测试分别解释，不使用历史 G1–G4 封存结果背书。
