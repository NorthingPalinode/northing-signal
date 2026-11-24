# Northing Signal

面向重度 AI 读者的本机事件追踪阅读器：聚合发布、文中测试与更正，帮助你查看具体变化、原始出处，以及宣称的依据与边界。

[![starter-checks](https://github.com/NorthingPalinode/northing-signal/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NorthingPalinode/northing-signal/actions/workflows/ci.yml)

当前采用独立的 Python / React 内容引擎。旧版目标工作台与 G1–G4 研究材料已从主分支移除，保存在 [`archive/research-g1-g4`](https://github.com/NorthingPalinode/northing-signal/tree/archive/research-g1-g4) 分支；旧个人数据库未自动迁移或删除，可以用 `scripts/export_legacy.py` 导出。

当前版本已接入 **61 个固定来源入口 + 9 类可选主动检索**，支持事件聚合与报道时间线、原文依据、自然语言确认追踪、收藏和阅读反馈。来源宣称、文中测试、公开榜单与本项目独立实测分别看待；当前没有开展本项目独立模型复测。

## 可以做什么

| 页面 | 用途 |
|---|---|
| 简报 | 最上方「距你上次来，有 N 件事变了」，然后是「最重要的 3 件事」，下接「重点」「前沿速览」「更多进展」三段，最新在前，可按方向筛选；最近一次更新新增的内容标【新】，已有事件出现新报道标「有更新」 |
| 搜索 | 一个搜索框：先筛选已有进展，没有结果时一键到所选公开来源检索，或交给 AI 持续追踪 |
| 追踪 | 用自然语言描述需求，核对 AI 理解与检索方案，确认后持续追踪；按话题查看新进展与未读数，打开一条即从未读数中减去，也可「全部标为已读」 |
| 收藏 | 收藏保留当时版本，可按方向筛选 |
| 资料库 | 检索原始材料，按「待整理 / 失败」筛选，区分已整理内容与尚待获取正文的线索 |

过去的简报、导出周报、来源状态与阅读偏好在左侧导航下方（手机端在右上角菜单）。

### 更新与「新」

- 服务运行期间，每天 **0 点和 12 点**（站点时区 `READER_TIMEZONE`，默认纽约时间 `America/New_York`）自动更新简报，可在「阅读偏好」中关闭。服务未运行时错过的时间点，会在下次启动后约半分钟补跑一次；手动更新同样算作这一时段的更新，不会重复。自动更新和手动更新一样会调用你配置的模型。
- 简报页右上角「更新」可随时手动更新；页头显示上次更新时间与下次自动更新时间。
- 首次收录于最近一次完成的更新的事件标【新】，读过后不再显示；页头显示「新增 N 项」。
- **距你上次来**：简报最上方列出上次来访之后首次出现（新）或有新报道的事件，并标明这篇新报道是更正、新测试、实质更新还是更多报道；读过、不感兴趣的不列出。30 分钟内重复打开算同一次来访，刷新页面不会清空；第一次使用不显示，没有变化时如实说明。和【新】不同，它跨过你没来的几次更新。
- **热度**按事件计算：48 小时内每个独立来源只算一次（以它最早的报道为准），每 24 小时减半；一家媒体发十篇也只算一次。多家来源都在报道的事件排序略微靠前（最多加 4 分）；最近 6 小时有新来源加入的多来源事件标「热度上升」。热度只统计及时抓到的报道。
- 「最重要的 3 件事」直接取简报排序（重要性、时效与你的偏好）的前三条，附「为什么值得读」，不额外调用模型。

### 阅读一条进展

点击卡片任意位置进入独立阅读页，地址为 `#story/<事件 ID>`，刷新后仍停留在同一条。

- **依据**：标题下一行按规则写出依据来自谁，例如「有官方原文 · 厂商自测，未见他方测试 · 3 个来源」或「媒体或作者转述，未见官方原文」，不调用模型。「未见」只指本项目已收取的报道；媒体文中的测试不称为独立验证，因为文章可能转述厂商数据。
- **正文**：摘要、为什么值得读、原文支持的主张与引句、适用条件、边界与未知、多来源报道时间线；可展开本机保存的原文节选，或打开原文链接。
- **操作**：收藏、有帮助、已了解、持续追踪这个话题、不感兴趣。前三项都是开关，再点一次即撤回。宽屏在右侧固定显示，窄屏和手机在底部固定操作栏。
- **打开即已了解**：第一次打开某条内容会自动标为「已了解」，卡片变灰。本期简报保持不变，下次更新起它不再进入重点；有实质更新（新版本）时仍会出现。点「已了解」可改回，之后再打开也不会重新标记。
- **连续阅读**：底部有上一条 / 下一条，顶部显示当前位置（如「3 / 10」），顺序沿用打开时所在的列表。键盘 `J` / `K` 切换，`Esc` 返回。
- **返回**：点「返回」或浏览器后退都会回到列表原来的位置。
- **纠正聚合**：时间线中可把归错的报道拆分出去，也可把重复事件合并到同方向的另一条事件。

### 界面

- 宽屏（≥1240px）右侧显示概览栏：简报页为今日数字、按方向筛选、追踪话题与最近收藏；搜索页常驻外部检索来源勾选；收藏页按方向筛选；资料库页为来源状态汇总。
- 内容区足够宽时，重点、收藏与追踪动态以双列卡片排列。
- 手机端使用底部标签栏，所有弹窗改为底部面板；界面跟随系统深色模式。

### 话题追踪

遵循 **描述需求 → AI 理解意图 → 纠正或编辑方案 → 用户确认 → 定期检索与相关性判断**。确认前不启动搜索；修改范围也需要重新确认。频率可选约每 30 分钟、2 小时、每天或每周，仅在本地服务运行期间执行，可暂停、恢复或取消（取消前会再确认，已收集内容保留在资料库）。

### 阅读反馈

列表卡片上的书签可直接收藏，划掉的眼睛图标表示不感兴趣，可说明原因（方向无关、内容空泛、重复）。在阅读页选择「不感兴趣」会直接进入下一条，提示中可撤销；已提交的反馈也可在阅读页「我的反馈」中撤回。「有帮助」会让同方向的内容排序略微靠前。收藏保留当时版本。

搜索页的输入框只筛选已有内容，按回车不会访问外部来源；需要外部检索时点「到外部搜索」。

### 周报导出

「导出周报」可选「最近 7 天」或「上周（周一至周日）」，预览后下载 Markdown 或复制。内容为：最重要的几件事（最多 5 件）、按方向分组的全部有依据进展（含来源、日期、依据类型与原文链接）、本周收藏和追踪话题的相关进展数。周报只汇总已整理的内容，不额外调用模型。

系统区分来源陈述、文中报告的测试与作者观点，搜索摘要不冒充原文，模型解释不冒充独立验证。

### 公开日报（给别人看）

把简报发布成一个任何人都能打开的静态网站和 RSS，无需对方安装或配置模型：

```bash
python -m northing_signal.briefing publish --out .local/public
```

或在 `.env` 中设置 `READER_PUBLISH_DIR`，之后每次更新（包括每天 0 点和 12 点的自动更新）完成后都会自动生成一期。生成的目录包含：

| 文件 | 内容 |
|---|---|
| `index.html` | 最新一期：「最重要的 3 件事」，其余按方向分组；每条附摘要、为什么值得读、醒目的「依据」一行（同阅读页）、边界与全部报道来源链接 |
| `editions/` | 每期的网页与数据（JSON），首页底部链接往期 |
| `feed.xml` | RSS 2.0，每期一条；需设置 `READER_PUBLIC_URL` 才能生成绝对链接 |

- **每期只含上一期之后新收录或有新报道的进展**（首期回看 48 小时），一周前发布但刚抓到的旧闻不算新闻；更正与撤回除外。没有新内容时不生成空的一期。
- **按规则编排，不调用模型**（参照 AIHOT 日报）：每期最多 15 条，正文 10 条（第 1 条为头条，第 2–4 条为今日看点，其余按方向分组），快讯 5 条（一行一条）。同一来源在正文里最多 2 条。最近 7 期报过的事件，只有当事方自己又有动作（官方来源的新发布、更新、测试或更正）或有 4 个以上来源报道时才回到正文，否则进快讯并标「跟进」。排序综合 AI 评分、热度和是否有官方原文。
- **不含任何个人数据**：使用默认偏好重新排序，不读取收藏、反馈、已了解、追踪话题或阅读记录。你标为「不感兴趣」的内容仍可能出现在公开日报中。
- **不发布原文**：只发布模型整理的标题、摘要和理由，以及原文链接；原文节选和引句仍只保存在本机。
- 发布到 GitHub Pages：新建一个仓库并开启 Pages，把 `READER_PUBLISH_DIR` 指向它的本地克隆，更新后 `git add -A && git commit && git push` 即可。本项目不会自动替你推送。

## 信息来源

固定来源池已从 12 个扩展为 61 个入口，按核心与补充来源排列。配置见 [briefing_sources.json](data/briefing_sources.json)，完整清单、逐源检查与按重要性排列的受限项见 [来源接入说明](docs/SOURCES.md)。

| 固定来源类型 | 数量 | 代表来源与材料 |
|---|---:|---|
| 官网发布与更新日志 | 10 | Anthropic、DeepSeek、Kimi、MiniMax、ByteDance Seed、Meta、xAI、Mistral、阿里云百炼（Qwen）、智谱 |
| 开源版本 | 8 | vLLM、SGLang、llama.cpp、Ollama、Transformers、LangGraph、Kimi Code、Claude Code |
| 模型目录与模型卡 | 10 | 九个 Hugging Face 官方组织，以及 ModelScope 的 Qwen 公开目录 |
| 论文发现 | 2 | arXiv 分类查询、Hugging Face Daily Papers |
| 评测数据与项目更新 | 3 | Arena 文本榜、SWE-bench Verified；LiveBench 当前仅更新记录 |
| RSS / Atom | 28 | OpenAI、Google AI 官方博客、Microsoft 新闻中心与 Azure、Apple、Amazon 与 AWS、NVIDIA 新闻稿、Google DeepMind、研究机构、Simon Willison、Interconnects、Latent Space、量子位；科技与商业媒体 The Verge、Ars Technica、CNBC、MIT Technology Review、雷峰网、极客公园等 |

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

官网列表先收录为线索，补读原文后再整理；固定模型目录每批最多读取一份公开模型卡，不获取权重或受限文件；模型日期取仓库创建时间，不用最近修改时间，以免旧模型改了模型卡就被当成新发布。**旧文不刷屏**：抓到时原文已发布超过 48 小时的报道，以及没有发布时间的内容，都按原文时间归档，不进入简报的重点、速览和更多进展，不标【新】、不触发「有更新」、不进入公开日报，但搜索和资料库仍能找到。48 小时从这次抓取之前的上一次更新算起，服务停机的那几天里发布的新闻不会因此变旧；新接入信源的历史存量会被归档。Hugging Face Daily Papers 天然比 arXiv 晚几天，单独放宽到 7 天（信源配置 `late_hours`）。整理时，模型卡、仓库页、文档和更新日志不写成「发布」，教程、分析和对过去发布的再介绍也保留原本的文章类型。Arena 文本榜与 SWE-bench 结果以“公开榜单数据”展示有界节选，保留来源条件和核验状态，不代表本项目复测。LiveBench 当前仅接入更新记录；ModelScope 当前仅接入 Qwen 公开目录元数据。

X 原生检索需要自己的应用授权；Artificial Analysis 数据 API 与 OpenReview 尚未接入默认采集。部分厂商官网独有内容、受限全文及当前完整评测榜单仍有缺口，详见来源说明。接口可用性以本机实际检查为准；公开 GET 支持当前环境的 HTTPS 代理，并保留公网地址、TLS 与响应大小边界。

## 启动

需要 Python 3.11+、Node.js 24（CI 使用版本；也支持 Node.js 22.12+）以及 Git。

### Windows / PowerShell

```powershell
git clone https://github.com/NorthingPalinode/northing-signal.git
cd northing-signal
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

启动脚本创建本项目虚拟环境、安装锁定依赖、构建前端并启动本机服务。已有依赖与前端构建时，可使用 `scripts/start.ps1 -SkipInstall`；需要指定 Python 或端口时使用 `-Python`、`-Port`。

### macOS / Linux

```bash
git clone https://github.com/NorthingPalinode/northing-signal.git
cd northing-signal
[ -e .env ] || cp .env.example .env
bash scripts/start.sh
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，点击右上角「更新」。每次更新按有限批量执行并可取消；未完成的材料保留待处理状态。刷新、主动检索和话题追踪共用一个后台任务：忙碌时新任务进入队列，手动操作排在定时追踪之前，排队中的任务可以单独取消。除每天两次的自动更新外，没有站外通知，也不会自动替用户操作第三方系统。

默认需要用令牌登录（见下一节）。只在本机自己用时，可在 `.env` 中设置 `READER_AUTH=off`，不需要登录，和以前一样。

## 账号与云端部署

每个令牌就是一个账号，不需要邮箱或手机号。所有读者共享同一份内容库（采集的材料、AI 整理结果和事件聚合）；**偏好、收藏、反馈、已了解、追踪话题、访问记录和过去的简报按账号分开**，互相看不到。

- **登录**：在登录页粘贴令牌。登录状态保存在仅服务端可读的 Cookie 中；脚本也可以用 `Authorization: Bearer <令牌>` 请求接口。
- **一键创建令牌**：登录页点击即可得到一个新账号。令牌只显示一次，数据库只保存它的哈希，丢失后无法找回。可用 `READER_SIGNUP=false` 关闭；每个来源地址每小时最多创建 `READER_SIGNUPS_PER_HOUR` 个。
- **管理员**：用命令行签发。第一次部署时，用下面的命令接管升级前的数据（原来的收藏、追踪话题等都在「原始账号」里）：

  ```bash
  python -m northing_signal.briefing token --admin --claim-local   # 接管原有数据并成为管理员
  python -m northing_signal.briefing token --admin                 # 另建一个管理员
  python -m northing_signal.briefing token --claim <账号ID>         # 为丢失令牌的账号重新签发（旧令牌立即失效）
  python -m northing_signal.briefing users                         # 列出账号
  ```

- **权限与限额**：

  | 操作 | 普通账号 | 管理员 |
  |---|---|---|
  | 阅读、收藏、反馈、偏好、周报 | ✓ | ✓ |
  | 「更新」全站内容（同一时间只运行一次，重复点击会合并） | ✓ | ✓ |
  | 外部检索、AI 理解追踪需求、手动检查追踪话题 | 合计每天 `READER_USER_REQUESTS_PER_DAY` 次（默认 10） | 不限 |
  | 追踪话题数 | `READER_USER_FOLLOW_LIMIT` 个（默认 3） | 12 个 |
  | 拆分、合并事件，重新整理失败材料（对所有人生效） | — | ✓ |
  | 取消任务 | 只能取消自己发起的 | 任何任务 |

  别人发起的检索或追踪任务在你的页面上只显示为「其他读者的任务」，不会显示检索内容。全站更新完成后，会为最近 30 天内登录过的账号各保存一份自己的「过去的简报」。

- **部署**：`docker compose up -d --build` 后，在同一台机器上用 Caddy 或 Nginx 提供 HTTPS 并反向代理到 `127.0.0.1:8000`。容器信任代理传来的 `X-Forwarded-For` / `X-Forwarded-Proto`，所以不要把 8000 端口直接暴露到公网。HTTPS 下登录 Cookie 自动带 Secure 标记。Caddy 最简配置：

  ```
  reader.example.com {
      reverse_proxy 127.0.0.1:8000
  }
  ```

  在容器里签发管理员令牌：`docker compose exec northing-signal python -m northing_signal.briefing token --admin --claim-local`。

- **Cloudflare Tunnel 部署（免费，无需公网 IP）**：适合直接在本机或内网机器上保留现有 SQLite 数据并对外提供 HTTPS 访问（完整交互式阅读器，需要 `READER_AUTH=token`）：

  1. 安装 `cloudflared`（Windows：`winget install --id Cloudflare.cloudflared`）。
  2. 临时体验（无需域名，每次重启生成新地址）：

     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/cloudflare.ps1
     ```

  3. 固定域名（已有托管在 Cloudflare 的域名时）：在 Cloudflare Zero Trust → Networks → Tunnels 创建隧道，将 Public Hostname 指向 `http://127.0.0.1:8000`（Docker 部署时指向 `http://northing-signal:8000`），复制 Tunnel Token 后运行：

     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/cloudflare.ps1 -TunnelToken "<你的TunnelToken>"
     ```

     或在 `.env` 设置 `CLOUDFLARE_TUNNEL_TOKEN` 后用 Docker 启动：`docker compose -f compose.yaml -f compose.cloudflare.yaml up -d --build`。

## 模型与可选接口配置

在本项目 `.env` 中填写自己的兼容 Chat Completions 接口；已有 `.env` 不要用模板覆盖。

```dotenv
LLM_MODE=compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model
```

默认 `LLM_MODE=baseline` 不调用联网模型。阅读器仍能保存原始材料，但会明确显示尚未整理；AI 意图理解和相关性判断需要配置模型，不用关键词规则冒充模型理解。

**每日模型调用次数与 Token 总量默认均不设上限**，继续记录实际用量，并按站点时区 `READER_TIMEZONE`（默认纽约时间）的零点统计每日用量。单次工作批量、请求超时和来源接口的限速仍保留；供应商计费与限流由供应商决定。没有可靠定价资料时只显示次数与 Token，不估造费用。

**每次更新最多整理 80 条新材料**（以前是 24 条，一天三百多条新材料大多没人读），同时发 2 个模型请求；每条约 1,500 Token。先读哪些不再按“最新优先”，而是按 [triage.py](backend/northing_signal/briefing/triage.py) 的免费排序：还算新闻的在前；**多家来源同时报道的事**（标题共享名称）最先；文章排在模型卡目录和论文列表之前；同一来源最多占前面 6 个位置。普通读者手动更新时只能用默认参数，规模由站点运营者决定。

“与 AI 有关”包括 AI 产业的重大动向：主要 AI 公司或芯片、算力公司的 CEO 与创始人任免、董事会决定、监管调查与听证、出口管制、重大诉讼、并购上市和大额融资（2026-11-24 起；此前黄仁勋复任英伟达 CEO 被判为无关）。修改判断规则后，可用 `python -m northing_signal.briefing rejudge --days 14 --limit 120` 把近期被判为“无关”或“不确定”的材料按新规则重新整理一遍，新判断与旧判断并存、以新的为准。

整理失败的材料不会在每次更新时反复消耗 Token：分别等待 1 小时、6 小时后重试，第三次失败后停止自动重试，可在资料库中点“重新整理”。引文或数字与原文不符这类失败，用同样的提示词重试大概率还会失败，所以直接从 6 小时开始。模型漏掉部分条目时，其余合格结果照常保存。供应商请求失败（网络错误或任何 HTTP 错误状态，如鉴权失败、限流、服务异常）不计入材料的失败次数，本轮停止继续请求。

| 可选配置 | 用途 |
|---|---|
| `READER_WEB_API_KEY` | 本项目自己的 AnySearch 密钥；留空时匿名访问，受提供方限额约束 |
| `READER_OPENALEX_API_KEY` | 本项目自己的 OpenAlex 密钥；留空时使用匿名基础接口 |
| `READER_X_BEARER_TOKEN` | 自有授权的 X 应用 Bearer Token；不配置时仅检索公开网页线索 |
| `READER_REQUESTS_PER_DAY`、`READER_TOKENS_PER_DAY` | 可选的每日模型调用上限；留空不限制 |
| `READER_TIMEZONE` | 站点时区，默认 `America/New_York`：决定 0 点/12 点自动更新、每日用量与读者额度的重置时间、也是读者没选时区时的默认显示（公开日报另用 `READER_PUBLISH_TIMEZONE`）；可改成 `Asia/Shanghai`，设为空值使用系统时区。每位读者可在「阅读偏好 → 时区」切换纽约时间或北京时间，只影响自己看到的日期时间和周报起止日；可选时区在 `models.py` 的 `TIMEZONES` 中增加 |
| `READER_BATCH_SIZE` | 每次模型请求整理的材料数，默认 4（1–6）；回复被截断时自动对半拆分重试 |
| `READER_FOLLOW_ANALYZE_LIMIT` | 话题追踪每轮最多整理的材料数，默认 6 |
| `READER_MODEL_CONCURRENCY` | 同时进行的模型请求数，默认 2；按供应商限流调整 |
| `READER_PUBLISH_DIR` | 公开日报输出目录；设置后每次更新完成自动生成一期，留空则只能手动运行 `publish` |
| `READER_PUBLIC_URL` | 公开日报的访问地址（如 `https://you.github.io/daily/`），用于 RSS 中的绝对链接 |
| `READER_PUBLISH_TIMEZONE` | 公开日报期号与日期所用时区，默认 `Asia/Shanghai`（日报是中文，站点可以按纽约时间运行）；设为空值则跟随 `READER_TIMEZONE` |

不读取其他项目的密钥、浏览器 Cookie 或私人账户内容。模型理解需求时会接收所提交的描述；内容整理和相关性判断会向配置的模型发送相应材料节选与确认意图。来源检索只发送所选方向的检索词。

## 校准筛选标准

什么内容值得读，最终要由你的判断来定。用自己标注的样本检查 AI 的筛选准不准，再调整门槛（做法参照 AIHOT 的 SelectBench）：

```powershell
.venv\Scripts\python -m northing_signal.briefing label        # 逐条标注：y 值得 / n 不值得 / e 两可 / k 跳过 / q 保存退出
.venv\Scripts\python -m northing_signal.briefing calibrate --split development
.venv\Scripts\python -m northing_signal.briefing calibrate --split holdout   # 调完后最后检查一次
```

- `label` 从库里抽 120 条已整理的材料（`--n` 可改），六成是分数贴近门槛的难例，官方来源和其他来源交替出现；不显示 AI 的判断，避免先入为主。每答一条立即保存，随时退出、下次接着标。每条材料固定分到开发集或留出集（约 7:3）。
- 只按「这条值不值得我花时间读」来标，不用管同一件事是否已经选过别的报道。
- `calibrate` 用已有的 AI 判断计算查准率、查全率、F1、覆盖率和完整准确率，**不调用模型、不花钱**；把门槛从 0 扫到 24，分别给出官方与研究来源、媒体作者与社区来源 F1 最高的门槛，并列出判错的条目。完整报告保存在 `.local/reader-quality/`。
- 先在开发集上调，最后用留出集检查一次，避免把门槛调成只会做这几道题。结论写进 `.env` 的 `READER_THRESHOLD_OFFICIAL`、`READER_THRESHOLD_OTHER`。
- 门槛只能整体移动。如果判错的条目分数并不贴近门槛，说明是整理提示词没讲清这类内容为什么重要或不重要，要改提示词，而改了提示词需要重新整理之后，这里的数字才有意义。
- 标注是你本人的判断，和旧的 `evaluate` 所用的 AI 编写参照集分开保存，不混用。

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

主要入口是 `backend/northing_signal/briefing/` 与 `frontend/src/ReaderApp.tsx`。实现、真实开发检查与限制见 [内容引擎说明](docs/CONTENT_ENGINE.md)；范围和后续方向见 [开发计划](docs/plans/AI_INFORMATION_QUALITY_IMPLEMENTATION_PLAN.md)。

下一轮重点是外部重要事件漏报观察、主张级测试归属、持续事件与回访增量，以及对象快捷关注。它们仍有待实施或验证的部分，不能把计划或一次来源连通检查当作两周覆盖效果与用户收益。

## 数据与当前限制

- 账号使用令牌登录，按账号隔离个人数据；尚未提供令牌自助重置、账号删除、团队共享或审计日志。创建令牌的频率限制保存在内存中，重启后清零，多进程部署时不共享；令牌为 256 位随机数，登录失败只做短暂延迟，没有锁定。每天 0 点和 12 点的自动更新是全站共享的，开关以「原始账号」的阅读偏好为准。所有账号共用同一个后台任务队列和同一份模型额度。
- 数据默认保存在 `.local/briefing-v2.db`，结构升级前会自动备份为同目录下的 `.bak-v<旧版本号>` 文件；旧个人库（`.local/cfaw-news.db`）不自动迁移，可用 `python scripts/export_legacy.py` 只读导出为 JSON Lines。`data/archive/articles.json` 等迁移出处保留。
- 在 Docker Compose 中升级时，沿用原来的项目名可复用数据卷。旧项目名为 `cfaw-news` 时，运行 `docker compose -p cfaw-news up --build --remove-orphans` 即可替换旧容器并保留数据。
- 事件聚合使用具体事件框架和原文指纹，归属保存在本地：报道一旦归入某个事件，就不随重新整理而改变，事件 ID 保持稳定。不同措辞的同一次发布（如 “GPT-5” 与 “GPT-5 release”）会自动归并，规则刻意保守：主体、版本号和产品词标准化后必须完全一致，且相隔不超过 7 天。**不同说法、不同语言的同一件事**由模型判断后合并（参照 AIHOT）：每次更新后，先免费找出最近两周里来自不同来源、对象名称相同、版本号不冲突、标题摘要有一定重合的事件对，再请模型判断关系：同一次发生、同一事件的直接进展（如发布后的评测、更正）、无关、汇总稿。只有前两种才合并，新事件并入旧事件；拿不准按无关处理。每次更新最多判断 `READER_RELATION_PAIRS` 对（默认 24，8 对一次请求；设为 0 关闭），每个判断都保存，同一对不会再问（例外：旧版提示词下答“汇总稿”的对，在新提示词下会再问一次）；读者手动拆开的事件不会被模型并回去。“最近两周”按事件最新一篇报道算，持续发酵的事件即使开头很早也能参与配对。**汇总稿**（标题用分号并列几件事，或早报、周报、newsletter 等合集）不会成为事件的主报道，也不提供事件标题；只有汇总稿报道的事件不参加配对，也不进入焦点，最多出现在雷达里。模型标为更正或撤回的内容，重要性至少为 2 才会置顶（软件修 bug 的小版本不算更正）。存量可用 `python -m northing_signal.briefing relate --limit 60` 补一次。归错的报道可在阅读页的报道时间线中拆分，重复的事件可以手动合并。尚未实现向量检索，召回依赖对象名称，名称写法差异很大的同一件事仍可能漏合并。
- 真实材料、AI 开发标签、合成样例与用户反馈分开记录；小样本结果不等于独立研究结论或普遍准确率。
- `.env`、`.local/`、`.tmp/`、虚拟环境、依赖、生成的 `frontend/dist/` 和 `dev-diaries/` 均不提交 Git。开发日记与私人数据永远仅保留在本地。
- 能抓到公开内容不代表拥有全文再分发权限；当前保存必要节选和出处，没有对外全文发布服务。

归档分支中的 G1–G4 文档保留其原始研究与验收含义，不作为新内容引擎已实现能力或质量提升的证明。

## 许可证

自本次许可变更起，项目方有权授权且此前未按其他条款发布的原创代码采用 [PolyForm Strict 1.0.0](LICENSE)。该许可允许非商业使用，商业使用、修改和再分发须另行获得授权。

此前按 Apache 2.0 发布的代码（包括 [变更前的版本 `4b837cc`](https://github.com/NorthingPalinode/northing-signal/tree/4b837ccd1be72d6d4eed895704827d60c67f87ca) 及后续版本沿用的对应部分）仍可依 [Apache 2.0](LICENSE-APACHE) 使用。第三方依赖、来源内容及素材适用各自条款，见 [NOTICE](NOTICE)。
