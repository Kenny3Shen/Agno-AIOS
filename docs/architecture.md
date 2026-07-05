# 架构说明

本文描述当前 Agno AIOS 代码实现。未来规划只放在 [roadmap.md](./roadmap.md)，不放在本文中。

## 系统形态

Agno AIOS 是一个面向安全运营的 FastAPI + Vue 应用。后端提供 JSON APIs、集成 MCP endpoint 和生产前端静态资源托管；前端是用于 Chat、Trace 检查、MCP 与 Skill 管理、Knowledge、安全数据、Settings 和 AgentOS 控制视图的 Vue 控制面。

```text
Browser
  |
  v
Vue Control Plane
  |
  v
FastAPI API
  |
  +-- 认证与 RBAC
  +-- 安全运营助手
  +-- /mcp/ 上的集成 FastMCP Runtime
  +-- Knowledge 和安全数据 APIs
  +-- Trace、session、audit 和 AgentOS 控制 APIs
  |
  v
PostgreSQL + pgvector
  |
  +-- app        应用表和审计记录
  +-- agno       Agno sessions、runs、memories、traces、spans
  +-- mcp        MCP tokens
  +-- knowledge  knowledge contents 和 vector tables
```

FastAPI app 在 `api/main.py` 中组装。启动生命周期会创建 auth tables、bootstrap 可选 admin、创建共享数据库连接池、启动集成 MCP runtime、include 各 API routers、挂载 `/mcp`，并从 `source/` 或 `frontend/dist` 托管前端静态资源。AgentOS 注册 fallback agent 时使用 async `AgentFactory`，避免在 module import 阶段同步读取 prompt 或 model config。

## 后端模块

`api/auth/` 负责 FastAPI Users 集成、JWT auth、role 推导、permission 检查和资源归属检查。

`api/routes/` 负责 HTTP route 边界：

- `/api/auth/*`：登录、注册、登出、OAuth provider listing 和 user endpoints。
- `/api/chat*`：流式 Chat、session list、session history 和 session archive。
- `/api/traces*`：trace list 和 trace detail。
- `/api/knowledge*`：knowledge status、document write、search、delete 和 clear。
- `/api/mcp*`：MCP service config、token management 和 MCP manifest upload。
- `/api/skills*`：本地 skill listing、toggle 和 upload。
- `/api/cve*`、`/api/url2md*`：安全数据 workflows。
- `/api/settings` 和 `/api/models`：runtime settings 和 model configuration。
- `/api/audit/logs`：admin audit review。
- `/api/os/*`：AgentOS control modules。

`api/services/` 负责业务逻辑和持久化辅助层。`postgres_store.py` 集中管理 PostgreSQL 连接设置、schema 名称、Agno `AsyncPostgresDb` 构造和应用表创建。`security_run_runtime.py` 承担安全运营助手 Run runtime，集中 model、MCP、Skill、Knowledge、fallback 和流式事件编排；模型配置、prompt 文件、MCP TOML 读取和 Skill metadata/list/toggle 使用 awaitable file API，Skill zip install 这类批量 filesystem operation 通过线程隔离，避免阻塞 Chat stream 的事件循环。`llm_service.py` 保留 Chat Session persistence、session history 和兼容入口。`knowledge_service.py` 提供 async Knowledge Base lifecycle interface，runtime route 走 Agno async Knowledge APIs 和 async contents DB，内部集中 PgVector、reader、owner filtering、CRUD、search 和 status。`mcp_config_service.py` 集中 MCP service toggle 和 MCP upload 配置写入，只暴露 async mutation facade，TOML 文件读写使用 awaitable file API。`security_policy.py` 集中控制面 module permission、Scheduler 写权限和 policy audit event 记录。`url2md_service.py` 使用 async HTTP client 执行 URL collection。`tracing_service.py` 读取 Agno traces 与 spans，并整理成前端需要的结构。

`api/mcp/` 负责集成 MCP runtime。`server.py` 构建主 FastMCP instance、挂载已启用的内置服务、用 token validation 包装 ASGI app，并支持 runtime refresh。`config.py` 读取和写入底层 MCP config，并存储 MCP tokens；上层配置 mutation 由 `api/services/mcp_config_service.py` 提供 module interface。

`api/tasks/` 负责运维脚本，包括 CVE update、MySQL-to-Postgres migration 和 scheduler execution。

## 前端模块

前端入口是 `frontend/src/App.vue`。它负责 shell、认证布局、导航、sidebar 状态、当前模型展示、基于 role 的导航过滤和模块挂载。

主要组件位于 `frontend/src/components/`：

- `Chat.vue`：流式助手对话。
- `Trace.vue`：以 session 为中心的 trace 与 span 检查。
- `MCP.vue`：MCP services、tokens 和 uploads。
- `Skills.vue`：本地 skill 管理。
- `Knowledge.vue`：document ingestion、retrieval、preview 和 deletion。
- `CVE.vue`、`Collect.vue`：安全数据 workflows。
- `Settings.vue`：runtime settings、model configuration 和 navigation tags。
- `AgentOSControl.vue` 以及 dashboard/workflow components：控制面视图。

状态和 API helpers 位于 `frontend/src/stores/`、`frontend/src/composables/` 和 `frontend/src/lib/`。前端 permission checks 只用于导航和控件可见性，不是安全边界。

## Chat 与 Agent Runtime

`POST /api/chat` 接收 message、session ID 和可选 model ID，并返回 `text/event-stream`。该 route 要求 `session:write:own`。如果客户端传入已有 session ID，非 admin 用户必须拥有该 session。

`api/services/security_run_runtime.py` 创建名为“安全运营助手”的 Agno `Agent`，当前包含：

- 来自 model configuration service 的 OpenAI-compatible model settings。
- 通过 streamable HTTP 使用 `MCP_SERVER_URL` 和 `MCP_TOKEN` 的 MCP tools。
- 带可选 user filter 的 Agno knowledge base。
- 来自 `api/agent/skills/` 的已启用 local skills。
- Agno `AsyncPostgresDb` session、memory、trace 和 schedule storage。
- History、memory updates、datetime context 和 Markdown output。

Tracing 通过 `setup_tracing(db=AsyncPostgresDb, batch_processing=False)` 启用，因此 Chat runs 会写入 Agno trace tables，并尽量减少 UI 刷新后看不到最新 trace 的延迟。

如果 provider 拦截完整 Agent context，Run runtime 会切换到无工具 fallback assistant。fallback 会明确说明能力受限，不声称访问了 tools、knowledge 或内部数据。

AgentOS 暴露的 fallback assistant 也复用同一个 runtime builder。`AgentFactory` 的 factory callable 是 async function，按 Agno AgentOS factories 文档在请求时 await；因此 model config 和 prompt 文件通过 awaitable file API 读取，而不是在 FastAPI import 或 AgentOS setup 时阻塞事件循环。

## Sessions、Runs、Traces 和 Spans

Chat session 不是授权 secret。后端把 `session_id` 当作标识符，并通过存储的 `user_id` 检查归属；admin 例外。

Sessions 和 runs 通过 Agno `AsyncPostgresDb` 从 Agno-owned `agno_sessions` 读取。UI 删除 Chat session 是 soft archive：服务把 archive marker 写入 Agno session metadata，不再创建或读写 `app.chat_session_archives`，也不会删除 runs 或 traces。

Traces 通过 Agno `AsyncPostgresDb` 和 async Postgres pool projection 从 `agno_traces` 和 `agno_spans` 读取。Trace UI 使用 `session_id`、`run_id`、`trace_id`、`span_id`、`agent_id`、`team_id` 和 `workflow_id` 把用户会话和执行细节关联起来。

## Knowledge

Knowledge documents 通过 metadata 做 user scope。Chat runtime 在存在当前用户时传入 `knowledge_filters` user filter。Knowledge route 使用 Agno `Knowledge.ainsert()`、`asearch()` 和 `aget_content()`；document contents 存在 `knowledge` schema 中的 Agno `AsyncPostgresDb`，vector chunks 由 Agno `PgVector` 管理。删除和清空不调用 Agno PgVector 的同步 delete helper，而是先通过 async SQLAlchemy 删除 vector rows，再通过 async contents DB 删除 catalog row。

PgVector 入口按 Agno 文档推荐的 async Knowledge API 使用：runtime 构造 Agno `PgVector`，业务代码只调用 `Knowledge.ainsert()`、`Knowledge.asearch()` 等 async methods。AIOS 不再把本地 vector adapter 作为默认 runtime path；新的 Agno-owned persistence 访问必须优先使用 Agno async API。

Agno API gap projections 是窄范围 async product views，不改变 table ownership：Knowledge delete/clear 使用 async SQLAlchemy 删除 vector rows 后通过 async contents DB 删除 catalog row；Knowledge dashboard 的 chunk-count 和 search result 的 content-id hydration 只读取 PgVector table 的 `id`、`content_id`、`meta_data`；Trace UI 和 dashboard 通过 Agno tracing API 读取 trace/span 后整理前端 payload，缺少聚合 API 时用 async Postgres pool 做轻量统计；AgentOS control payload 在 sessions/memory/scheduler 使用 Agno async APIs，在 metrics、knowledge 状态和 AIOS control tables 上保留 async projection。

Embedding 和 rerank 模型计算不属于 async DB I/O。默认 Knowledge runtime 使用 Agno `SentenceTransformerEmbedder` 和 `SentenceTransformerReranker` 接入 `PgVector`，AIOS 不再维护自定义本地模型 adapter；如需调整模型行为，应优先沿用 Agno 提供的 embedder/reranker 扩展点。

当前写入路径包括后端 text input、后端 server-side file path input，以及前端把 browser file upload 读取成 text 后走文本写入。Search 会返回匹配内容和 metadata，供控制面和助手使用。

## MCP

主 FastAPI app 在 `/mcp/` 挂载集成 MCP runtime。调用该 endpoint 必须通过 `Authorization: Bearer` header 或 `token` query parameter 提供有效 MCP token。

内置 MCP services 是 `playbook` 和 `basic`。启用状态最终从 `data/config/mcp/mcp_config.toml` 读取，控制面写入通过 `api/services/mcp_config_service.py` 完成。旧 Hi-Agent/`agent.*` 接入不再作为内置 MCP service 暴露。

## 数据存储

应用依赖带 `vector` extension 的 PostgreSQL。运行时 schemas：

| Schema | 当前职责 |
| --- | --- |
| `app` | FastAPI Users auth tables、CVE records、audit logs、AgentOS control tables |
| `agno` | Agno sessions、memories、traces、spans、schema versions |
| `mcp` | MCP tokens |
| `knowledge` | Agno knowledge contents 和 PgVector tables |

Schema 分域是运行时边界，不是独立服务边界。见 [ADR 0001](./adr/0001-postgres-schemas-for-runtime-domains.md)。

## 外部文档依据

当前实现使用了这些框架概念：

- Agno run 使用 `user_id` 和 `session_id` 支持 multi-user sessions。
- Agno traces 包含 trace records 和层级 spans，带 `run_id`、`session_id`、`user_id` 和组件 ID。
- Agno 文档推荐 Postgres storage 用于生产式 relational persistence，并用 PgVector 在 PostgreSQL 上做 vector search；AIOS runtime 使用 Agno `AsyncPostgresDb`。
- Agno AgentOS factories 支持 async callable，并会在请求时 await；AIOS 用它延迟构造 fallback agent。
- FastMCP 可以作为 ASGI app 挂载到 FastAPI。
