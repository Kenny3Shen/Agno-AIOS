# 控制面数据使用 SQLAlchemy

Agno AIOS 默认使用同步 SQLAlchemy 作为 Control Plane Data 的访问层，同时让 Agno Runtime Data 继续由 Agno `PostgresDb` 和 `PgVector` 管理。这个决策遵循 Agno 的生产存储建议：在同一个 PostgreSQL engine 上使用 `PostgresDb` 和 `PgVector`；同时避免本地重新实现 Agno 管理的 schemas。对于窄范围 PostgreSQL-specific setup 和 migrations，仍可保留 raw SQL。

## 备选方案

- 把所有查询都迁移到 SQLAlchemy，包括 Agno runtime tables。拒绝原因：Agno 已经拥有这些 table contracts 和 upgrade paths。
- 立即把 app-owned persistence layer 改为异步 SQLAlchemy。拒绝原因：Agno runtime 当前仍使用同步 `PostgresDb`，而 app-owned audit/MCP/CVE 控制面查询不是已证明的高吞吐瓶颈；立即异步化会把 `await`、async engine 和错误处理扩散到大量 service 与 route 边界。
- 保留所有当前 raw SQL。拒绝原因：app-owned tables 已经通过 auth 使用 SQLAlchemy，分散 SQL 会让 ownership、typing 和 refactors 更难维护。

## 为什么现在不使用异步 DB

Agno 提供 `AsyncPostgresDb`，并要求使用 `postgresql+psycopg_async` 形式的连接 URL；AgentOS 示例也展示了 sync 和 async 两套 setup。但这不是当前迁移的默认选择。

当前 AIOS 的 Agno Runtime Data 仍通过同步 `PostgresDb` 访问。只把 app-owned SQLAlchemy 改成 async 会让同一请求路径同时维护同步 Agno storage、异步 app storage 和已有 `psycopg_pool`，降低边界清晰度。`record_audit_event()` 又被 auth、MCP、Knowledge、Skill 等多条同步和异步路径调用，改成 async 会把调用方一起重写，或者引入后台任务语义；这比消除当前短事务阻塞更昂贵。

因此当前约定是：app-owned tables 使用同步 SQLAlchemy Core/ORM；只有当以下任一条件成立时，再创建新的 ADR 迁移到异步 DB：

- Agno runtime 整体切换为 `AsyncPostgresDb`。
- 生产或压测数据证明 app-owned DB 访问阻塞事件循环，并且同步 SQLAlchemy pool tuning 不能解决。
- 新增的 app-owned workflow 本身是高并发、长事务或 streaming-adjacent DB workload。

## 迁移顺序

先从低风险 app-owned tables 开始，例如 `mcp.mcp_tokens`、`mcp.hiagent_exec_cache` 和 `app.audit_logs`。然后迁移 `app.cves`、`app.chat_session_archives`、`app.os_eval_runs` 和 `app.os_approvals`。最后逐一审查剩余的 Agno session 和 trace table 读取路径：能用 Agno APIs 的替换为 Agno APIs；不能替换的路径需要单独设计，不在默认迁移策略中作为例外保留。

## 持久化形态

为 app-owned data 建立薄 SQLAlchemy persistence layer，集中维护 engine/session、metadata，以及 table 或 model declarations。Services 继续承载业务逻辑，通过这一层访问数据，不在各 service 里分散定义表访问。

## 第一批 Agno-owned 收敛目标

`app.chat_session_archives` 是第一批从 app-owned table 收敛到 Agno-owned storage 的目标。Archive 状态迁移到 `agno.agno_sessions.metadata` 后，AIOS 继续保留 `/api/chat/sessions` facade、权限检查和软归档语义；迁移完成后删除 `app.chat_session_archives` 建表与读写逻辑。该路径不保留直接更新 Agno table 的 SQL 例外，归档读写通过 Agno `PostgresDb` API 完成。

## 已迁移 app-owned tables

`app.audit_logs` 已迁移到薄 SQLAlchemy persistence layer。表定义、索引、insert 和 list 查询集中在 `api.persistence.audit_logs`，`audit_service` 只保留 actor/context 投影和审计业务入口。
