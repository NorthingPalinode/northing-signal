# CFAW News 数据源选择调研

调研日期：2026-11-08（Asia/Shanghai）

范围：本文保留 2026-11-08 的公开资料调研快照；实际接入清单、验证记录和当前限制以 [来源接入说明](../docs/SOURCES.md) 为准。开发过程记录仅保存在本地。


调研目标：为重度 AI 读者确定首批持续采集、线索发现与按需补证来源，核实其公开入口、接入条件和证据边界；本轮先讨论来源，不修改运行配置。

## 关键问题

1. 当前 12 个固定来源和九类检索入口遗漏哪些重要发布方、独立测试和工程变化？
2. 官方发布、论文、开源产物、测试、作者及社区分别应承担什么角色？
3. 哪些提供官方 RSS/API，哪些只能检查网页或需要授权？公开可读与可再分发如何区分？
4. 如何以有限维护成本改善覆盖，避免把转载数当独立证据数？

## 本地起点

已核对 `data/briefing_sources.json` 和当前采集/发现代码。固定池为 OpenAI、Google DeepMind、Google Research、Hugging Face 博客、Microsoft Research、NVIDIA、GitHub AI & ML、BAIR、TechCrunch AI、The Decoder、Simon Willison、vLLM Releases。九类检索包含 web/arXiv/GitHub/Hugging Face/OpenAlex/Hacker News/X/抖音/小红书。配置存在不代表当前实网可用。

固定池缺少 Anthropic、Meta/xAI 及中国模型发布方的直接持续入口；论文和模型仓库主要依赖主动检索，第三方测试没有专门持续入口。这是配置覆盖判断，不是全网召回测量。

## 发现

（逐轮追加，标明已证实与待确认；网页/API说明不等于本机接口已实测。）

## 来源列表

（逐轮追加。）

### 第 1 轮：论文与平台入口

- Hugging Face 官方文档提供 Hub 端点和模型/论文查询；API 文档已指向 OpenAPI Playground，调用受平台限速。模型卡与作者组织可用于原始产物追踪，热度仍只作发现信号。
- arXiv 官方文档确认分类 RSS/Atom 与自定义查询 API；应以 arXiv ID/版本去重，按分类发现后再做内容筛选，不把摘要视为全文。
- GitHub 官方文档确认 REST 限速；持续采集设计需按仓库使用条件请求/缓存，而不是频繁全站搜索。
- Anthropic 官网新闻入口可检索到；本轮尚未从官方证实统一 RSS，不能依据第三方“无 RSS”文章断言不存在。

来源（访问日均为 2026-11-08）：
- https://huggingface.co/docs/hub/en/api — 官方 API 说明。
- https://huggingface.co/docs/huggingface_hub/en/package_reference/cli — 官方模型与论文 CLI 能力。
- https://github.com/arXiv/arxiv-docs/blob/develop/source/help/rss.md — 官方分类订阅文档。
- https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md — 官方查询接口文档。
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api — 官方接口约束。
- https://www.anthropic.com/news — 官方发布入口；接入形态待进一步检查。

### 第 2 轮：原始发布与接入现实

- Anthropic News、DeepSeek API Change Log、x.ai/news、Mistral News 本轮可由网页工具读取，能作为官方原始发布/变更入口；发布方的性能描述仍是其自身宣称。
- Qwen 博客 URL 返回页面但本轮提取不到可读文本；Meta 的旧 llama.com 入口重定向到 developer.meta.com/ai/ 后工具不可读。不能把这些结果当成候选机构没有信息源，需要检查官方仓库、Hub 组织与其他公开入口。
- arXiv API 条款和 Hugging Face 模型卡文档存在官方入口，具体限速和模型卡内容再核对；本轮未调用本项目采集器做连接试验。

来源（2026-11-08）：https://www.anthropic.com/news 、https://api-docs.deepseek.com/updates/ 、https://qwen.ai/blog 、https://www.llama.com/ 、https://x.ai/news 、https://mistral.ai/news/ 、https://info.arxiv.org/help/api/tou.html 、https://huggingface.co/docs/hub/en/model-cards 。

### 第 3 轮：中国发布方与原始产物

- MiniMax 有官方 News & Updates 入口；Kimi 的官方代码仓库存在中文 changelog。Moonshot 状态页是故障/可用性信号，应与模型发布分开，不把恢复公告当新模型。
- Qwen 官方旧发布文章明确链接 GitHub、Hugging Face、ModelScope；首页正文提取不稳定时可以先查官方产物渠道，不能以第三方域名冒充官方。
- 搜索结果中出现不少第三方变更聚合站，本轮不拿它们作为模型版本、价格和发布时间的权威依据。

来源（2026-11-08）：https://www.minimax.io/news 、https://status.moonshot.cn/ 、https://github.com/MoonshotAI/kimi-code/blob/main/docs/zh/release-notes/changelog.md 、https://qwen.ai/blog?id=qwen1.5 。

### 阶段摘要（第 3 轮）

首要补齐发布方直连，而非增加更多转载媒体；每个发布方可通过官网更新、代码仓库、模型卡组成同一上游的多入口。它们帮助发现漏报和核对变化，但不是三份独立验证。RSS/API 优先，公开网页作为补充；尚未核实的 RSS/API 不虚构。

### 第 4 轮：评测来源与使用条件

- Artificial Analysis 官方提供数据 API，访问需要其平台账户及 API key；免费接口有字段范围，使用需要归属标注，并受其条款约束。API 页面已出现 v2 参考文档，不能照抄旧教程端点。无需本项目用户都注册，可后续由维护方在合法授权范围内集中接入；本轮不注册、不索取密钥。
- Arena 官方组织在 Hugging Face 发布 leaderboard-dataset，提供当前及历史榜单、方法变更说明和置信区间等字段。应同步榜单类型、日期和方法版本，不能把偏好分数解释为全部任务能力。
- SWE-bench 官方榜单明确区分团队运行/检查的结果；提交结果也有核验字段，不能把所有榜单条目统一称为第三方实测。

来源（2026-11-08）：https://artificialanalysis.ai/api-reference 、https://artificialanalysis.ai/data-api/docs/reference 、https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset 、https://www.swebench.com/index.html 、https://github.com/swe-bench/experiments/blob/main/checklist.md 。

### 第 5 轮：社区、学术审稿与易漂移入口

- HN Algolia 官方接口提供按时间检索及帖子/评论读取，适合线索发现、复现反馈和负面体验；原始外链与社区发言分开。
- OpenReview 官方当前主 API 为 v2，提供 Notes/修改/回复结构；仅处理公开可读的投稿、修订和评审，按会议及权限检查，不预设所有内容匿名可取。
- Kimi 旧开放平台入口本轮重定向到 platform.kimi.com，说明长期来源需记录稳定发布方与最终 URL，而非把域名永久写死。
- LiveBench 首页依赖 JS，ByteDance Seed 列表本轮无可读文本，Z.ai 所试路径不可访问；这些是网页工具观察，不代表其官方仓库/产物渠道不可用。
- X 检索搜索结果混入 docs.x.ai 的模型检索工具与第三方代理，需分别核对；不能把 x.ai 的 X Search、X 官方 API 和网页索引当作相同服务。

来源（2026-11-08）：https://hn.algolia.com/api 、https://docs.openreview.net/getting-started/using-the-api 、https://docs.openreview.net/reference/api-v2/openapi-definition 、https://platform.kimi.com/docs/get-api-key 、https://livebench.ai/ 、https://seed.bytedance.com/en/blog 、https://docs.x.ai/developers/tools/x-search 。

### 第 6 轮：X 授权与作者渠道

- X 官方近期检索文档可读；官方定价说明现为预付 credits 的按量使用模式，具体端点费率以 Developer Console 为准。不能沿用旧套餐或把网页检索当原生 API。
- Simon Willison 提供本人实践/链接/引文等不同形态；原始实践与转述分别处理。Interconnects 与 Latent Space 的官方页面可查，适合分析/工程上下文，不自动视为独立实验。
- news.smol.ai 本轮重定向到 Latent Space 的 AI News；两者在来源清单应按实际关系去重，不能算两份独立上游。
- Qwen 与 zai-org 的 Hugging Face 组织页有官网/官方 GitHub 关联和模型产物；MoonshotAI 的同平台页面本轮工具不可达，应保留待实测，不能断言所有组织入口均可用。

来源（2026-11-08）：https://docs.x.com/x-api/posts/search/quickstart/recent-search 、https://docs.x.com/x-api/getting-started/pricing 、https://simonwillison.net/ 、https://www.interconnects.ai/ 、https://latent.space/ 、https://latent.space/news/ 、https://huggingface.co/Qwen 、https://huggingface.co/zai-org 。

### 阶段摘要（第 6 轮）

建议至少包含发布方、代码/模型产物、论文、第三方测试、作者/媒体、社区发现六类。官方源覆盖广度、第三方实际测试、工程变化是当前优先缺口。X 必须有原生授权和费用决策，网页索引仍可作为降级发现；评测优先使用有公开数据/方法/归属说明的入口。

### 第 7 轮：工程仓库候选核对

通过 GitHub 连接器只读查询仓库元数据，本轮以下八个仓库均存在且 archived=false：vllm-project/vllm、sgl-project/sglang、ggml-org/llama.cpp、ollama/ollama、huggingface/transformers、langchain-ai/langgraph、MoonshotAI/kimi-code、anthropics/claude-code。适合作为首批工程对象候选；存在/未归档不等于每次 Release 都值得推荐，尚未逐个探测 Release/Atom。

来源（2026-11-08）：以上八项的 https://api.github.com/repos/{owner}/{repo}；对应公开仓库 URL 为 https://github.com/{owner}/{repo} 。

### 第 8 轮：媒体、限速与接口细节

- 机器之心官网有公开文章库与会员通讯，不能预设全文均公开；量子位本轮工具读取超时。TechCrunch AI 和 The Decoder 页面可读，保留为发现/采访报道来源，不能把其所有文章视为性能测试。
- GitHub Releases 官方接口只包含关联了 Release 的发布，不包含单独 Git tag；若仅监听 releases，仍可能漏掉只更新 changelog/标签的项目。公共已发布 Release 可匿名读取，但受限速。
- arXiv 官方当前条款对传统 API/RSS/OAI-PMH 规定整体单连接、至少三秒一次；这是接入节奏约束，不是项目已做过的长稳验证。
- HF 模型卡支持用途、限制、训练与评测结果等字段；这些由卡片发布方提供，应该保留结果来源，不能自动算作第三方验证。

来源（2026-11-08）：https://www.jiqizhixin.com/ 、https://www.qbitai.com/ 、https://techcrunch.com/category/artificial-intelligence/ 、https://the-decoder.com/ 、https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28 、https://info.arxiv.org/help/api/tou.html 、https://huggingface.co/docs/hub/en/model-cards 。

### 第 9 轮：补查 Meta 与字节

- Meta AI 官方博客本轮可读，旧 Llama 入口不可读不影响选择现行博客；meta-llama Hub 页也可读，但单一模型家族组织页不能替代 Meta 全部 AI 产品发布。
- ByteDance Seed 英文主页本轮可读，含模型、研究/博客与最新更新链接。列表页提取为空不表示全站不可接入。
- 腾讯混元主页本轮读取超时，作为扩充候选保留，不声称已连通。

来源（2026-11-08）：https://ai.meta.com/blog/ 、https://huggingface.co/meta-llama 、https://seed.bytedance.com/en/ 、https://hunyuan.tencent.com/ 。

### 阶段摘要（第 9 轮）

厂商按身份覆盖，平台按访问方式接入；不能以有没有 RSS 决定是否覆盖重要发布方。一个主体多个入口归为同一上游。代码/模型仓库更新与正式发布分开，榜单变动与独立实验分开，社区帖子与外链原文分开。

## 调研结论

### 建议首批组合

| 层次 | 候选 | 主要用途与接入方式 |
|---|---|---|
| 发布方原文 | OpenAI、Anthropic、Google/DeepMind、Meta、xAI、Mistral；Qwen、DeepSeek、Kimi、Z.ai/GLM、MiniMax、ByteDance Seed | 按发布方登记官网、开发者更新、system/model card 及官方仓库。已有可用 RSS 优先；其余逐项检查公开网页或产物 API，不虚构 RSS |
| 开源工程 | vLLM、SGLang、llama.cpp、Ollama、Transformers、LangGraph、Kimi Code、Claude Code | 重点仓库 Release、必要 changelog/标签与说明修订，不抓所有 commit，不以 stars 门槛挡住已确认发布方的新项目 |
| 模型产物 | HF 官方组织/模型卡；ModelScope 作为后续国内补充候选 | 新模型、权重/许可/运行要求与卡片修订。按作者组织和对象跟踪，不把 lastModified 当发布时间 |
| 学术 | arXiv cs.AI/cs.CL/cs.LG/cs.CV；OpenReview 按会议补充 | RSS/API 发现与版本追踪；先摘要筛选，选中后按需读原文/修订；预印本不等于独立验证 |
| 测试 | Artificial Analysis、Arena 官方数据集、SWE-bench 官方榜与结果仓库 | 保留测试者、具体模型版本、方法、日期、条件、提交者和核验状态；不制造统一的“客观最强榜” |
| 作者/媒体 | Simon Willison、Interconnects、Latent Space；The Decoder、TechCrunch AI，机器之心公开部分 | 原始实践、分析、采访或发现线索，逐篇区分；公开节选与付费内容分开 |
| 社区发现 | X 的机构/作者/维护者名单、HN、HF Daily Papers；有界网页查询 | 发现新事件、复现问题与原始链接。推荐流、热榜、搜索摘要不直接升级为结论 |

### 接入优先级

1. 先补 Anthropic 与中国模型发布方的直达入口，并将重点 GitHub/HF 对象改为持续对象跟踪。
2. 同步建立 arXiv 分类发现和第三方测试补证；作者/媒体数量保持小而互补。
3. X 独立做授权与费用选择：未配置时保留网页索引降级，但不能承诺实时或完整。
4. 不为所有候选一次性开发独立爬虫。先用现有 RSS/API 及公开页采集做代表性连通/正文/修订检查，再由两周外部漏报记录决定增删和频率。

### 主要依据汇总

| 来源 | URL | 发布日期 | 可确认程度 |
|---|---|---|---|
| arXiv 官方 RSS/API/条款 | https://info.arxiv.org/help/api/tou.html | 持续更新，页面未列单一发布日期；2026-11-08 访问 | 高：接口规则；不证明论文结论 |
| GitHub Release 文档 | https://docs.github.com/en/rest/releases/releases | 持续更新；2026-11-08 访问 | 高：接口字段与访问边界 |
| HF Hub/模型卡 | https://huggingface.co/docs/hub/en/api | 持续更新；2026-11-08 访问 | 高：平台能力；卡片内容仍归发布者 |
| X 官方检索/定价 | https://docs.x.com/x-api/getting-started/pricing | 持续更新；2026-11-08 访问 | 高：当前公开接入约束；具体费率看控制台 |
| Artificial Analysis API | https://artificialanalysis.ai/data-api/docs/reference | 持续更新；2026-11-08 访问 | 高：其接口说明；测试结论保留其方法边界 |
| Arena 官方数据集 | https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset | 持续更新；2026-11-08 访问 | 高：官方发布的榜单及元数据；不代表全部使用场景 |
| SWE-bench 官方榜 | https://www.swebench.com/index.html | 持续更新；2026-11-08 访问 | 高：榜单与核验标识；逐项区分提交来源 |

### 待确认

- 每个候选的稳定机器入口、响应格式、正文/修订可获取程度和从本机网络的可达性；本轮只做网页与仓库元数据查证，没有完成全部采集联调。
- 公共展示所需的节选/归属/数据使用条款；开放代码不自动赋予整站文章或榜单再发布权。
- X 是否投入本项目自己的原生 API 授权及费用；AA API 是否由维护方集中申请。未经决定不创建账户、不启用付费接口。
- ModelScope 元数据接口与官方发布方映射、腾讯/其他长尾机构稳定入口；量子位、Moonshot HF 等本轮工具超时/不可达项需独立实测。

### 讨论建议

先确定覆盖对象和各来源职责，再决定适配器和轮询频率；不要用来源总数、转载数或点赞数代替覆盖和证据质量。每条材料至少记录发布方、平台、发现路径、原始出处、发布时间/抓取时间、版本以及证据角色。两周观察仍保留至少一个未作为固定输入的外部参照入口，避免再次把输入池当覆盖分母。

本轮未修改来源配置、现有追踪或私人数据库；没有把候选清单记成已接通能力。

## 后续接入结果

初次调研后的实际接入已完成：固定池从 12 个扩展为 45 个入口，包含官方发布、模型目录、开源版本、论文、公开榜单和作者/媒体；ModelScope 的 Qwen 匿名目录与腾讯公开模型目录也已验证。官网、HF、GitHub 与 ModelScope 上同一主体的材料不计作独立支持。

X 原生、Artificial Analysis、OpenReview 及部分动态官网/受限全文仍有权限或接入缺口，LiveBench 当前仅接入更新记录。完整逐项说明与实测日期见来源接入说明；不能把初查结果解释为已完成全部采集联调或普遍质量验证。
