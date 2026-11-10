# 架构

本机单用户的 Python / React 应用。运行时代码只有 `backend/cfaw_news/briefing/` 一个包和 `frontend/src/` 下的阅读器页面。产品行为与证据规则见 [内容引擎说明](CONTENT_ENGINE.md)，来源见 [来源接入说明](SOURCES.md)。

```mermaid
flowchart LR
    U[React 阅读器] -->|REST| A[app.py · FastAPI]
    A --> S[service.py · 单个有界后台任务]
    S --> C[collect.py / source_adapters.py · 固定来源]
    S --> D[discover.py / search_sources.py · 主动检索]
    C --> N[net.py · 公网 HTTPS 边界]
    D --> N
    S --> M[understand.py · 兼容模型整理]
    S --> I[intent.py · 意图理解与相关性]
    S --> DB[(store.py · SQLite .local/briefing-v2.db)]
    A --> E[engine.py · 事件投影与排序]
    E --> DB
    A --> T[tracking.py · 关注话题视图]
```

| 模块 | 职责 |
|---|---|
| `app.py` | HTTP 路由、本机来源校验、静态页面 |
| `service.py` | 刷新、检索、话题追踪共用的一个后台任务；取消后不发布迟到结果 |
| `store.py` | 独立 SQLite 文件：素材版本不可变，阅读操作只追加 |
| `collect.py`、`source_adapters.py` | 固定来源（RSS、官网列表、开源版本、模型目录、榜单）采集与正文补读 |
| `discover.py`、`search_sources.py` | 用户发起或追踪方案触发的公开检索；搜索摘要只作线索 |
| `net.py` | 公网读取边界：只允许 HTTPS，连接固定到已校验的公网 IP，按原域名校验 TLS，限制重定向和响应大小 |
| `understand.py` | 调用兼容 Chat Completions 接口整理素材；校验引文、数字与结构；记录用量与预算 |
| `intent.py` | 自然语言描述 → 可核对的追踪方案 → 方案内的相关性判断 |
| `engine.py` | 纯函数：事件聚合、阅读排序、简报选取；不依赖 HTTP 或数据库 |
| `tracking.py` | 关注话题的成员与未读版本计算 |
| `models.py`、`settings.py` | 数据契约与配置 |
| `__main__.py` | 命令行：离线检查、导出、重查与有界采集 |

前端：`ReaderApp.tsx` 负责页面与交互；`reader/types.ts` 是 `/api/reader` 返回数据的类型；`reader/logic.ts` 放不依赖 React 和浏览器的纯函数（路由、列表划分、证据标签），由 `frontend/tests/` 覆盖。

版本号只写在 `backend/cfaw_news/__init__.py`，`pyproject.toml`、API 和 `/api/health` 都从这里读取。

## 不变量

1. 素材版本写入后不改；同一版本的出处字段不同会拒绝写入。
2. 收藏、反馈、已了解等操作只追加，撤回也是一条新记录。
3. 取消任务后，迟到的模型结果不写入、不发布。
4. 追踪方案经用户确认后才会检索；修改范围需要重新确认。
5. `baseline` 模式不调用模型，也不用关键词规则冒充模型判断。
6. 引文必须能在原文中连续找到；数字必须出现在原文中。

## 数据层

- **迁移**：`store.MIGRATIONS` 按编号顺序执行，当前版本记在 `meta.schema_version`。升级已有数据库前，先用 SQLite backup 复制一份 `briefing-v2.db.bak-v<旧版本>`；遇到比程序更新的数据库会拒绝启动。新增结构只能追加新的编号，不能修改已经执行过的迁移。
- **修订号**：触发器在 `meta` 中维护两个计数器。`content_revision` 跟踪素材和判断，`reader_revision` 跟踪交互、偏好、关注和意图判断。其他进程（如命令行）的写入同样会更新。
- **缓存**：`ContentService.projection()` 缓存事件投影、收藏与关注视图，修订号变化或超过 10 分钟后重新计算。超时是为了让时间衰减排序不在空闲时冻结。`Store.materials()` 按内容修订号缓存解析结果。
- **交互校验**：`record_interaction()` 只依赖内容和收藏集合，所以高频的"已展示""已打开"不会触发完整投影。
- **快照**：只保存当时简报的 focus/radar 事件，不保存整个资料库。保留最近 60 份，以及 90 天内的全部快照。
- **线程**：路由和后台任务中的大块读取与投影计算放在线程中执行；`Store` 用一把锁串行访问 SQLite。

## 有意保留的简化

单进程、单个后台任务，适合本机使用。数据变化后的首次投影仍是全量计算（5000 条素材约 1.4 秒，在线程中执行）。尚未实现：任务队列、向量检索、用户鉴权和多用户隔离。

## 历史

2026-10 的 0.2 目标工作台和 G1–G4 研究、评测、审计材料已于 2026-11-10 从主分支移除，保存在 `archive/research-g1-g4` 分支和 `archive/g1-g4-final` 标签。旧个人数据库可用 `scripts/export_legacy.py` 只读导出。最初从比赛项目迁入的资产及其字节校验记录见 [MIGRATION.md](MIGRATION.md) 和 `docs/provenance/`。
