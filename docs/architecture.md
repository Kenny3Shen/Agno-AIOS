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

FastAPI app 在 `api/main.py` 中组装。启动生命周期会创建 auth tables、bootstrap 可选 admin、创建共享数据库连接池、启动集成 MCP runtime、include 各 API routers、挂载 `/mcp`，并从 `source/` 或 `frontend/dist` 托管前端静态资源。

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

`api/services/` 负责业务逻辑和持久化辅助层。`postgres_store.py` 集中管理 PostgreSQL 连接设置、schema 名称、Agno `PostgresDb` 构造和应用表创建。`security_run_runtime.py` 承担安全运营助手 Run runtime，集中 model、MCP、Skill、Knowledge、fallback 和流式事件编排；`llm_service.py` 保留 Chat Session persistence、session history 和兼容入口。`knowledge_service.py` 提供 Knowledge Base lifecycle interface，内部集中 Agno Knowledge、PgVector、reader、owner filtering、CRUD、search 和 status。`mcp_config_service.py` 集中 MCP service toggle 和 MCP upload 配置写入。`security_policy.py` 集中控制面 module permission、Scheduler 写权限和 policy audit event 记录。`tracing_service.py` 读取 Agno traces 与 spans，并整理成前端需要的结构。

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
- Agno `PostgresDb` session storage。
- History、memory updates、datetime context 和 Markdown output。

Tracing 通过 `setup_tracing(db=db, batch_processing=False)` 启用，因此 Chat runs 会写入 Agno trace tables，并尽量减少 UI 刷新后看不到最新 trace 的延迟。

如果 provider 拦截完整 Agent context，Run runtime 会切换到无工具 fallback assistant。fallback 会明确说明能力受限，不声称访问了 tools、knowledge 或内部数据。

## Sessions、Runs、Traces 和 Spans

Chat session 不是授权 secret。后端把 `session_id` 当作标识符，并通过存储的 `user_id` 检查归属；admin 例外。

Sessions 和 runs 从 Agno `agno_sessions` 表读取。UI 删除 Chat session 是 soft archive：服务会在 `app.chat_session_archives` 中记录 archive state，并标记 Agno session metadata，但不会删除 runs 或 traces。

Traces 通过 Agno `PostgresDb` functions 从 `agno_traces` 和 `agno_spans` 读取。Trace UI 使用 `session_id`、`run_id`、`trace_id`、`span_id`、`agent_id`、`team_id` 和 `workflow_id` 把用户会话和执行细节关联起来。

## Knowledge

Knowledge documents 通过 metadata 做 user scope。Chat runtime 在存在当前用户时传入 `knowledge_filters` user filter。Knowledge Base lifecycle module 通过 `knowledge` schema 中的 Agno `PostgresDb` 存储 document contents，并通过 PgVector 存储 vector chunks。

当前写入路径包括后端 text input、后端 server-side file path input，以及前端把 browser file upload 读取成 text 后走文本写入。Search 会返回匹配内容和 metadata，供控制面和助手使用。

## MCP

主 FastAPI app 在 `/mcp/` 挂载集成 MCP runtime。调用该 endpoint 必须通过 `Authorization: Bearer` header 或 `token` query parameter 提供有效 MCP token。

内置 MCP services 是 `playbook` 和 `basic`。启用状态最终从 `data/config/mcp/mcp_config.toml` 读取，控制面写入通过 `api/services/mcp_config_service.py` 完成。旧 Hi-Agent/`agent.*` 接入不再作为内置 MCP service 暴露。

## 数据存储

应用依赖带 `vector` extension 的 PostgreSQL。运行时 schemas：

| Schema | 当前职责 |
| --- | --- |
| `app` | FastAPI Users auth tables、CVE records、audit logs、chat session archive markers、AgentOS control tables |
| `agno` | Agno sessions、memories、traces、spans、schema versions |
| `mcp` | MCP tokens |
| `knowledge` | Agno knowledge contents 和 PgVector tables |

Schema 分域是运行时边界，不是独立服务边界。见 [ADR 0001](./adr/0001-postgres-schemas-for-runtime-domains.md)。

## 外部文档依据

当前实现使用了这些框架概念：

- Agno run 使用 `user_id` 和 `session_id` 支持 multi-user sessions。
- Agno traces 包含 trace records 和层级 spans，带 `run_id`、`session_id`、`user_id` 和组件 ID。
- Agno 文档推荐 PostgresDb 用于生产式 relational persistence，并用 PgVector 在 PostgreSQL 上做 vector search。
- FastMCP 可以作为 ASGI app 挂载到 FastAPI。
