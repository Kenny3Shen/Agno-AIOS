# 控制面数据使用 SQLAlchemy

Agno AIOS 默认使用异步 SQLAlchemy 作为 Control Plane Data 的访问层，并逐步把 Agno Runtime Data 调用迁移到 Agno async APIs，例如 `AsyncPostgresDb`。这个决策遵循 Agno 的生产存储建议：在同一个 PostgreSQL engine 上使用 Postgres storage 和 PgVector；同时避免本地重新实现 Agno 管理的 schemas。对于窄范围 PostgreSQL-specific setup 和 one-off migrations，仍可保留 raw SQL，但 runtime request path 应向 async DB API 收敛。

## 备选方案

- 把所有查询都迁移到 SQLAlchemy，包括 Agno runtime tables。拒绝原因：Agno 已经拥有这些 table contracts 和 upgrade paths。
- 只使用同步 SQLAlchemy。拒绝原因：AIOS 控制面面向高并发 API 和 streaming-adjacent workflows，同步 DB 调用会在 async route、FastMCP middleware 和 background workflows 中形成事件循环阻塞点。
- 保留所有当前 raw SQL。拒绝原因：app-owned tables 已经通过 auth 使用 SQLAlchemy，分散 SQL 会让 ownership、typing 和 refactors 更难维护。

## 为什么转向异步 DB

Agno 提供 `AsyncPostgresDb`，并要求使用 `postgresql+psycopg_async` 形式的连接 URL；AgentOS 示例也展示了 sync 和 async 两套 setup。Agno AgentOS factories 文档还说明 async callable 可用于需要读取 DB、HTTP 或其他 awaitable context 的 request-time agent 构造，AgentOS 会检测 coroutine 并 await。AIOS 当前目标是把控制面迁移到异步 API，以减少 FastAPI route、MCP middleware 和未来 streaming workflows 中的阻塞点。

迁移顺序应先清理 app-owned tables 的 runtime CRUD，再切 Agno-owned runtime 访问。这样可以先消除最容易控制的 raw SQL 和 sync DB calls，同时保留 Agno table ownership：AIOS 不重新定义 Agno schemas，只把调用方式从同步 facade 迁到 async facade。

当前约定是：新的 app-owned runtime persistence 使用 async SQLAlchemy Core/ORM；Agno Runtime Data 优先使用 Agno async APIs；runtime request path 不保留同步 DB 调用。

第一批已迁移的 async runtime path 是 auth bootstrap/session、MCP token、audit logs、CVE intelligence、Chat session archive/list/history、Knowledge route、URL collection、Scheduler CRUD/run history、Agno tracing 和 AgentOS control payload：`api.auth.database`、`api.persistence.database` 和 `api.services.postgres_store` 统一使用 `postgresql+psycopg_async` async driver URL；`api.mcp.config` 不再直接使用 `psycopg`/raw SQL，route 和 ASGI token middleware 通过 awaitable persistence helpers 访问 `mcp.mcp_tokens`，`api.services.mcp_config_service` 只保留 async config mutation facade；审计写入和查询通过 `api.persistence.audit_logs` 的 async SQLAlchemy helpers 访问 `app.audit_logs`；CVE 查询、更新任务和一次性迁移 target writes 复用 `api.persistence.cves` 的 async SQLAlchemy helpers，CVE update route 的数据源 config、远程数据 fetch 和本地 commit cache 使用 async file/HTTP APIs，Polars parse/read/compare/write 和文件日志 setup 通过线程隔离，避免远程 CSV、大本地 CSV 或批处理 CPU 阻塞 request event loop；Chat session facade 通过 Agno `AsyncPostgresDb` 读取 session 和写入 archive metadata；Knowledge route 通过 Agno `ainsert()`、`asearch()`、`aget_content()` 和 async contents DB 访问 knowledge catalog，同步 lifecycle methods 已删除，本地文件路径校验使用 awaitable file API，delete/clear 绕开 Agno PgVector 同步 delete helper，改用 async SQLAlchemy 删除 vector rows 后调用 async contents DB 删除 catalog row；URL collection route 使用 `httpx.AsyncClient`，不在 async route 中执行 `requests`；model config、MCP TOML config、`.env` lazy loading、MCP tool runtime env loading、Skill metadata/list/toggle、Agent prompt reads 和 API file logging setup 使用 awaitable file API 或线程隔离，相关同步 facade 不再导出；Skill zip install 作为批量 filesystem operation 通过线程隔离，避免阻塞 request event loop；Scheduler service 直接使用 Agno `AsyncPostgresDb` schedule APIs；Agno tracing setup 和 AgentOS app integration 使用 `AsyncPostgresDb`；AgentOS fallback assistant 通过 async `AgentFactory` request-time 构造，避免 module import/setup 阶段同步读取 prompt 和 model config；AgentOS control payload 通过 async service API、async Postgres pool 和 Agno async memory/session APIs 避免在 FastAPI route 中执行同步 DB 读取。一次性 MySQL-to-Postgres 迁移脚本的源库读取也已改为 `aiomysql` async connection。

Agno PgVector 文档推荐在 async Knowledge flow 中构造 `PgVector(table_name=..., db_url="postgresql+psycopg://...")` 并调用 `Knowledge.ainsert()` / `Knowledge.asearch()`。AIOS 接受的规则是：默认 Knowledge vector runtime 使用 Agno `PgVector` + Knowledge async APIs，并通过 Agno `SentenceTransformerEmbedder` / `SentenceTransformerReranker` 接入本地模型能力；只有 app-owned data，或已经记录为 Agno API gap 的窄范围 product projection，才可添加 async SQLAlchemy / async Postgres pool 访问。当前允许的 Agno-owned direct projections 是 Knowledge vector-row delete/clear、chunk-count dashboard projection、content-id hydration、Agno tracing payload shaping，以及 AgentOS control payload 所需的只读统计或状态 view。

## 迁移顺序

先从低风险 app-owned tables 开始，例如 `mcp.mcp_tokens` 和 `app.audit_logs`。然后迁移 `app.cves`、`app.chat_session_archives`、`app.os_eval_runs` 和 `app.os_approvals`。最后逐一审查剩余的 Agno session 和 trace table 读取路径：能用 Agno APIs 的替换为 Agno APIs；不能替换的路径需要单独设计，不在默认迁移策略中作为例外保留。

## 持久化形态

为 app-owned data 建立薄 async SQLAlchemy persistence layer，集中维护 async engine/session、metadata，以及 table 或 model declarations。Services 继续承载业务逻辑，通过这一层访问数据，不在各 service 里分散定义表访问。

## 第一批 Agno-owned 收敛目标

`app.chat_session_archives` 是第一批从 app-owned table 收敛到 Agno-owned storage 的目标。Archive 状态迁移到 `agno.agno_sessions.metadata` 后，AIOS 继续保留 `/api/chat/sessions` facade、权限检查和软归档语义；迁移完成后删除 `app.chat_session_archives` 建表与读写逻辑。该路径不保留直接更新 Agno table 的 SQL 例外，归档读写通过 Agno `AsyncPostgresDb` API 完成。

## 已迁移 app-owned tables

`app.audit_logs` 已迁移到薄 async SQLAlchemy persistence layer。表定义、索引、insert 和 list 查询集中在 `api.persistence.audit_logs`，`audit_service` 只保留 actor/context 投影和审计业务入口，async routes 使用 awaitable audit API。

`mcp.mcp_tokens` 已迁移到 async SQLAlchemy persistence layer。表定义、索引和 token CRUD 集中在 `api.persistence.mcp`，runtime 调用方通过 awaitable API 访问。
