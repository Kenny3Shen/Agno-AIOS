# Agno AIOS AI 信息安全中台

Agno AIOS 是一个面向安全运营场景的 AI 信息安全中台。系统基于 FastAPI、Vue 3、Agno、FastMCP、PostgreSQL、PostgresDb 和 PgVector，把 CVE 情报、资产画像、网页情报解析、Agent 对话、运行观测、MCP 工具中枢、Skills 能力包、用户认证、AgentOS 风格控制面和基础 RAG 知识库整合到同一个主服务中。

当前目标不是做一个通用聊天页面，而是构建可持续扩展的安全 Agent 工作台：安全人员可以在一个界面内完成情报查询、漏洞研判、资产排查、剧本调用、知识检索和运行观测。

## 核心能力

- **AI 安全助手**：基于 Agno Agent 的流式对话，支持模型切换、用户隔离的会话历史、MCP 工具、Skills、Memory 和知识库检索。
- **AgentOS 控制面**：参考 Agno OS 左侧导航补齐 Sessions、Studio、Memory、Metrics、Evaluation、Approvals 和 Scheduler，统一查看 Agent 运行状态和治理对象。
- **CVE 情报**：按 CVE 编号、应用名或关键词检索漏洞记录和 PoC 来源。
- **资产搜索**：基于指纹或 IP 查询资产画像。
- **URL 转 Markdown**：抓取网页正文并转换为 Markdown，便于情报沉淀。
- **运行观测**：在左侧 `Trace` 导航下展开最近 Trace Queue，右侧查看选中 Trace 的 Span Waterfall、树状关系和属性详情。
- **态势总览**：展示 Agent 运行成功率、耗时趋势、小时热力、Span/Error 分布、Agent 负载雷达和错误态势。
- **MCP 工具中枢**：FastMCP 与主 API 同进程运行，支持服务开关、Token、Hi-Agent MCP 接入、生命周期管理和基础 middleware 防护。
- **Skills 管理**：启用、禁用和查看本地 `api/agent/skills/` 能力包。
- **RAG 知识库**：基于 Agno Knowledge、PostgresDb 和 PgVector 的知识库，Agent 可通过 `search_knowledge_base` 检索内部资料，文档列表会压缩超长 metadata 以保证中后台布局稳定。
- **认证与 OAuth**：基于 FastAPI Users、JWT、SQLAlchemy Async，支持注册、密码登录和 GitHub/Google/Microsoft OAuth2 登录。
- **中后台工作台**：`frontend` 进入后即为安全数据中台工作区，提供注册登录、会话恢复、模块导航、全局指标、亮暗模式切换和退出登录。

## 技术栈

- 前端：Vue 3、TypeScript、Element Plus、UnoCSS、Vite/Rolldown、markdown-it、highlight.js、npm。
- 后端：FastAPI、FastAPI Users、SQLAlchemy Async、Pydantic Settings、Uvicorn、psycopg、psycopg-pool、httpx、Polars、loguru。
- Agent：Agno、OpenAILike、LocalSkills、PostgresDb、Tracing、PgVector RAG。
- MCP：FastMCP，同进程 ASGI 挂载。
- 包管理：uv、npm。

## 项目结构

```text
.
├── api/
│   ├── main.py                 # FastAPI 应用入口
│   ├── routes/                 # API 路由
│   ├── services/               # 业务逻辑服务
│   ├── mcp/                    # 内置 FastMCP 运行时
│   │   ├── server.py           # MCP ASGI 入口
│   │   ├── config.py           # MCP 配置、Token、Hi-Agent 状态
│   │   └── tools/              # 内置 MCP 工具模块
│   ├── agent/                  # Agent 本地资源
│   │   └── skills/             # Agent 可加载的本地技能
│   ├── models/                 # Pydantic 数据模型
│   ├── tasks/                  # 数据更新任务与命令入口
│   │   ├── update_cve.py       # CVE 数据更新任务
│   │   ├── update_ip_asset.py  # IP 资产数据更新任务
│   │   └── cve_sources.py      # CVE 数据源与增量对比逻辑
│   ├── utils/                  # 数据库与数据处理工具
│   └── data/                   # CVE/资产数据缓存
├── frontend/                   # Vue 3 + TypeScript + Element Plus + UnoCSS 主前端源码
├── frontend-react/             # React 实验/历史前端目录，不作为当前主前端
├── source/                     # 前端生产构建输出，供 FastAPI 托管
├── scripts/                    # 运维包装脚本
│   └── run_update_cve.sh       # CVE 定时更新包装脚本
├── config.toml                 # 数据源配置
├── pyproject.toml              # Python 依赖与项目配置
└── README.md
```

## 环境要求

- Python 3.12+
- uv
- Node.js 24+ 与 npm
- PostgreSQL 15+，并启用 pgvector 扩展

## 快速启动

安装后端依赖：

```bash
uv sync
```

安装前端依赖：

```bash
cd frontend
npm install
```

启动后端：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端开发服务：

```bash
cd frontend
npm run dev
```

开发访问地址：

```text
http://localhost:5173
```

生产构建前端：

```bash
cd frontend
npm run build
```

构建产物会输出到仓库根目录 `source/`，并由 FastAPI 静态资源服务托管。

### 前端工作台说明

`frontend` 是当前主前端。未登录时先进入注册/登录页，登录成功后进入 AI 信息安全中台工作区：

- 注册/登录页调用 FastAPI Users 的 JWT 接口，支持邮箱密码注册、登录、会话恢复和 OAuth Provider 发现。
- 左侧导航按 Agno OS 控制面习惯组织：`Home` 下方直接是 `Dashboard`，中段优先为 `Chat / Skills / MCP / Knowledge / Trace`，随后是 `Sessions / Studio / Memory / Metrics / Evaluation / Approvals / Scheduler` 和安全数据工具。`Chat` 下方可展开会话列表，`Trace` 下方可展开最近 Trace Queue。
- 顶部展示当前模块、数据治理状态、MCP 编排状态、风险观测状态、当前用户、亮暗模式切换和退出登录。
- 中央工作区保留 CVE 情报、资产治理、情报采集、Agent 编排、知识资产、运行观测、MCP 工具、Skills 和系统配置等既有能力，并新增 AgentOS 风格轻量控制面页面。
- 生产构建仍输出到仓库根目录 `source/`，由 FastAPI 静态资源服务托管。

### AgentOS 对齐说明

本轮通过 `agno-docs` MCP 检查了 Agno Agent API、AgentOS API Overview、Memory Best Practices、Session Storage、Update Session 和 Delete Session 文档。Agno 文档建议生产 Agent API 覆盖 runs、sessions、memory、knowledge、evals、traces、metrics、schedules、approvals 和 components，并为 memory/session 提供 user 维度隔离。Agno AIOS 当前实现：

- 已有 `PostgresDb`、Tracing、Knowledge、PgVector、Skills 和 MCPTools。
- `/api/chat` 会把当前用户 ID 传入 Agno run，避免不同登录用户共享默认 memory/session 语义。
- Agno 文档中的 `DELETE /sessions/{session_id}` 是永久删除 session 和 runs；Agno AIOS 的 Chat 侧栏删除按钮改为软归档，写入 `app.chat_session_archives` 并同步 `agno_sessions.metadata.agno_aios_archived=true`，不会删除 Trace 或历史 runs。
- `/api/os/sessions`、`/api/os/studio`、`/api/os/memory`、`/api/os/metrics`、`/api/os/evaluation`、`/api/os/approvals`、`/api/os/scheduler` 提供 AgentOS 风格控制面数据。

当前 Evaluation、Approvals 和 Scheduler 是 registry scaffolding：页面和表结构已经存在，后续可接入评测执行器、paused run 审批恢复和真实调度执行器。

### Security model

Agno AIOS uses authenticated FastAPI users with `admin`, `user`, and `guest` roles. Backend APIs derive ownership from the JWT-authenticated user and do not trust frontend-provided `user_id` values for authorization.

- `admin` can read and operate across users.
- `user` can read and write their own Session/Chat data and read their own Trace data.
- `guest` is read-only for owned resources.
- Session and Trace APIs enforce backend ownership checks. Missing or foreign resources are hidden from non-admin users.
- Audit events are stored in `app.audit_logs` for login, logout, Session archive, Knowledge, MCP, Skill, Settings, and admin-style operations.

Required verification after Python changes:

```bash
uv run ruff check .
uv run ty check .
```

After frontend/backend changes, run the relevant frontend checks and Playwright browser validation before merging.

## 配置说明

创建 `.env` 文件或设置环境变量：

```bash
# PostgreSQL / PgVector
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=agno_aios
POSTGRES_PASSWORD=agno_aios
POSTGRES_DB=agno_aios
AGNO_APP_SCHEMA=app
AGNO_DB_SCHEMA=agno
AGNO_MCP_SCHEMA=mcp
AGNO_KNOWLEDGE_SCHEMA=knowledge

# ACL 资产数据更新
ACL_USERNAME=your_username
ACL_PASSWORD=your_password

# 日志
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_FILE=poc.log
CORS_ORIGINS=["*"]

# Auth / JWT / OAuth
AUTH_JWT_SECRET=replace-with-long-random-secret
AUTH_RESET_PASSWORD_SECRET=replace-with-long-random-secret
AUTH_VERIFICATION_SECRET=replace-with-long-random-secret
AUTH_OAUTH_STATE_SECRET=replace-with-long-random-secret
AUTH_TOKEN_LIFETIME_SECONDS=3600
AUTH_COOKIE_SECURE=false
OAUTH_ASSOCIATE_BY_EMAIL=true
OAUTH_IS_VERIFIED_BY_DEFAULT=true

GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_CLIENT_SECRET=
GITHUB_OAUTH_REDIRECT_URL=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URL=
MICROSOFT_OAUTH_CLIENT_ID=
MICROSOFT_OAUTH_CLIENT_SECRET=
MICROSOFT_OAUTH_TENANT=common
MICROSOFT_OAUTH_REDIRECT_URL=

# Agent / MCP
MCP_SERVER_URL=http://127.0.0.1:8000/mcp/
MCP_TOKEN=your_mcp_access_token
AGENT_TIMEZONE=Asia/Shanghai
AGNO_SKILLS_DIR=api/agent/skills
AGNO_SKILLS_CONFIG_FILE=tmp/skills_config.json

AGNO_KNOWLEDGE_PGVECTOR_TABLE=security_knowledge_vectors
AGNO_POSTGRES_KNOWLEDGE_TABLE=agno_knowledge
AGNO_KNOWLEDGE_NAME=security_knowledge
AGNO_KNOWLEDGE_TOP_K=5
AGNO_KNOWLEDGE_CHUNK_SIZE=1200
AGNO_KNOWLEDGE_CHUNK_OVERLAP=160
AGNO_KNOWLEDGE_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
AGNO_KNOWLEDGE_EMBEDDING_DIMENSIONS=512
AGNO_KNOWLEDGE_RERANK_MODEL=BAAI/bge-reranker-base
AGNO_KNOWLEDGE_DEVICE=auto
AGNO_KNOWLEDGE_RERANK_ENABLED=true
AGNO_KNOWLEDGE_RERANK_CANDIDATE_MULTIPLIER=3
AGNO_KNOWLEDGE_RERANK_MIN_CANDIDATES=10
```

默认 `uv sync` 会安装 CPU 版 `torch`，这是为了避免在不一致的 CUDA / cuDNN 环境下出现运行时崩溃。需要 GPU 推理时，先确认本机显卡和 PyTorch wheel 兼容，再覆盖安装对应的 GPU 版本。

模型参数不再通过 `LLM_*` 环境变量维护。启动服务后进入 **系统配置 -> 模型路由**，配置 API Key、Base URL、Model ID、启用状态和默认模型。运行时配置会保存到：

```text
tmp/model_config.json
```

MCP 配置和 Token 会保存到：

```text
tmp/mcp/mcp_config.toml
PostgreSQL 表：mcp.mcp_tokens
PostgreSQL 表：mcp.hiagent_exec_cache
```

知识库会保存到：

```text
PostgreSQL schema：knowledge
PgVector 表：knowledge.security_knowledge_vectors
Agno content 表：knowledge.agno_knowledge
```

## 数据库初始化

WSL2 / Ubuntu 本地安装 PostgreSQL 和 pgvector：

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo pg_ctlcluster 16 main start
```

创建数据库、用户、schema 和 pgvector 扩展：

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE agno_aios WITH LOGIN PASSWORD 'agno_aios';
CREATE DATABASE agno_aios OWNER agno_aios;
\connect agno_aios
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION agno_aios;
CREATE SCHEMA IF NOT EXISTS agno AUTHORIZATION agno_aios;
CREATE SCHEMA IF NOT EXISTS mcp AUTHORIZATION agno_aios;
CREATE SCHEMA IF NOT EXISTS knowledge AUTHORIZATION agno_aios;
ALTER DATABASE agno_aios SET search_path TO app, agno, mcp, knowledge, public;
SQL
```

主 API 启动时会确保 `app.cves`、`agno.*`、`mcp.*` 基础表存在。知识库第一次写入、检索或查看状态时，`PgVector.create()` 会创建 `knowledge.security_knowledge_vectors`，`PostgresDb` 会创建 `knowledge.agno_knowledge` 内容登记表。若使用托管 PostgreSQL，需要提前确认数据库已安装 pgvector 扩展，且运行用户有建表权限。

认证模块启动时会通过 SQLAlchemy Async 自动创建 FastAPI Users 所需的 `user` 和 `oauth_account` 表。OAuth Provider 只有在对应 `*_OAUTH_CLIENT_ID` 和 `*_OAUTH_CLIENT_SECRET` 配置存在时才会启用。

## 数据更新

从旧 MySQL 主库迁移到 PostgreSQL：

```bash
uv run migrate-mysql-to-postgres
```

迁移命令会读取旧 MySQL 的 `cves`、`agno_*`、`mcp_tokens` 和 `hiagent_exec_cache` 表，并幂等写入 PostgreSQL 的 `app`、`agno` 和 `mcp` schema。迁移源仍使用 `MYSQL_TEST_HOST`、`MYSQL_TEST_USER`、`MYSQL_TEST_PASSWORD`、`MYSQL_TEST_DATABASE`、`MYSQL_TEST_PORT` 环境变量。

旧 ChromaDB 知识库不会自动迁移到 PgVector，切换后需要通过知识库 API 重新写入或批量导入文档。

更新 CVE 数据：

```bash
uv run update-cve
```

更新 IP 资产数据：

```bash
uv run update-ip-asset
```

推荐定时任务：

```bash
# 每天 08:00 更新 CVE 数据
0 8 * * * cd /home/shenss/python/Agno-AIOS && ./scripts/run_update_cve.sh >> logs/cron_cve.log 2>&1

# 每天 03:00 更新 IP 资产数据
0 3 * * * cd /home/shenss/python/Agno-AIOS && uv run update-ip-asset >> logs/cron_asset.log 2>&1
```

## Agent 实现

当前 Agent 位于 `api/services/llm_service.py`，核心能力包括：

- 使用系统配置中的 OpenAI-compatible 模型。
- 通过 `MCPTools` 调用同进程 FastMCP 工具。
- 通过 `LocalSkills` 加载 `api/agent/skills/` 本地能力包。
- 使用 Agno `PostgresDb` 保存会话、记忆和运行记录。
- 使用 Agno tracing 记录运行链路。
- 通过 Agno `knowledge=Knowledge(...)` 接入 PostgresDb + PgVector 知识库。

Agent 在以下场景会优先检索知识库：

- 内部制度和处置规范。
- 历史报告和研判结论。
- 资产说明和业务背景。
- 漏洞风险研判资料。
- 用户明确要求基于已沉淀资料回答。

## RAG 知识库

当前知识库使用 Agno `Knowledge`，`PostgresDb` 保存内容登记，`PgVector` 保存向量切片，`BAAI/bge-small-zh-v1.5` 做向量化，并使用 `BAAI/bge-reranker-base` 对召回候选进行二阶段重排。Agent 通过 Agno 的 `search_knowledge_base` 工具按需检索内部知识库，实现 Agentic RAG。

默认向量表为 `knowledge.security_knowledge_vectors`，内容登记表为 `knowledge.agno_knowledge`。切换 embedding 模型后需要重新写入或重建知识库索引，避免向量维度冲突。

首次触发向量检索或 rerank 时会同步加载本地模型；如果本机尚未缓存 Hugging Face 权重，还会先下载，冷启动可能阻塞 30-120 秒。

写入文本知识：

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/documents/text \
  -H 'Content-Type: application/json' \
  -d '{"title":"应急处置规范","content":"发现公网暴露服务后先确认资产归属、认证状态和漏洞利用迹象。","source":"manual"}'
```

写入本地 Markdown/TXT 文件：

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/documents/file \
  -H 'Content-Type: application/json' \
  -d '{"path":"/abs/path/report.md","title":"历史处置报告"}'
```

检索知识库：

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"公网暴露服务如何处置","limit":5}'
```

查看状态：

```bash
curl http://127.0.0.1:8000/api/knowledge
```

## MCP 工具中枢

MCP 已整合进主 API 进程：

- MCP 协议入口：`/mcp/`
- 管理 API：`/api/mcp/*`
- 配置文件：`tmp/mcp/mcp_config.toml`
- Token 表：`mcp.mcp_tokens`
- Hi-Agent 执行缓存表：`mcp.hiagent_exec_cache`
- 访问方式：`Authorization: Bearer <token>` 或 `/mcp/?token=<token>`

本轮通过 `fastmcp-docs` MCP 检查了 FastAPI 集成、lifespan、HTTP deployment 和 middleware 文档。Agno AIOS 当前保留显式 FastMCP ASGI lifespan 启动方式，并继续用 ASGI token wrapper 兼容 `MCPTools` query token。同时在可用版本中接入 FastMCP `ErrorHandlingMiddleware`、`RateLimitingMiddleware`、`TimingMiddleware` 和 `ResponseLimitingMiddleware`。

主服务启动时会自动确保存在一个 bootstrap token。服务开关和 Hi-Agent 配置更新后，重启主 API 后对 MCP 协议工具列表生效。

### 新增 MCP 服务

1. 在 `api/mcp/tools/` 新建模块，例如 `scanner.py`：

   ```python
   from fastmcp import FastMCP

   scanner_mcp = FastMCP("Scanner")

   @scanner_mcp.tool()
   async def run_scan(target: str) -> dict:
       return {"target": target, "status": "queued"}
   ```

2. 在 `api/mcp/config.py` 的 `SERVICE_IDS` 中加入 `"scanner"`。
3. 在 `api/mcp/server.py` 导入 `scanner_mcp`，并在 `build_main_mcp()` 中挂载：

   ```python
   if "scanner" in enabled:
       main_mcp.mount(scanner_mcp, namespace="scanner")
   ```

4. 在 `frontend/src/types/index.ts` 的 `McpServiceId` 中加入 `"scanner"`。
5. 在 `frontend/src/components/MCP.vue` 的服务卡片列表中增加该服务。
6. 执行 `uv run ruff check .`、`uv run ty check .` 和 `cd frontend && npm run build`。

## 低代码工作流编排规划

当前系统优先复用现有 SOAR 平台，把剧本执行能力通过 MCP 工具和 `playbook-skill` 暴露给 Agent。这样可以保留已有自动化资产、审批流程和处置经验，同时让中台先具备“查询、研判、调用、观测”的闭环能力。

低代码编排能力的长期目标是让安全人员可以在中台内完成剧本设计、参数编排、审批发布、执行观测和结果复盘。该能力不应只做成一个前端画布，而应成为 Agent、MCP 工具、SOAR、工单、告警和知识库之间的统一任务编排层。

规划路径：

- **现有 SOAR 接入**：短期以 API/MCP 适配器接入现有 SOAR，统一封装剧本列表、参数模板、执行状态、执行日志和回滚动作。
- **中台内嵌编排**：中期在信息安全中台内增加低代码工作流页面，支持节点拖拽、参数映射、条件分支、人工审批、定时触发和执行审计。
- **开源平台二次开发**：评估 Node-RED、n8n、StackStorm、Windmill 等开源编排平台，选择适合安全场景的平台进行二次开发或作为底层执行引擎。
- **Agent 参与编排**：让 Agent 可以基于告警、漏洞、资产和知识库上下文推荐剧本、补全参数、解释执行风险，但关键动作必须保留审批和审计。
- **标准化剧本资产**：沉淀漏洞应急、资产封禁、情报富化、通知上报、工单流转、证据采集等标准剧本模板。
- **安全边界**：对高风险节点增加权限校验、审批策略、幂等保护、回滚策略和敏感参数脱敏。

## Skills

本地能力放在 `api/agent/skills/<skill-name>/`，每个 Skill 至少包含一个 `SKILL.md`。稳定执行的数据访问或分析逻辑建议放入 `scripts/`，避免让模型直接生成复杂脚本。

当前内置能力：

- `threat-trace-skill`：威胁情报检索与研判。
- `darknet-trace-skill`：暗网泄露信息态势分析。
- `intranet-ip-skill`：内网告警/资产风险分析。
- `playbook-skill`：安全剧本调用规范。
- `cve-intel-skill`：CVE/应用漏洞情报、PoC 来源和风险态势分析。

新增 Skill 的建议结构：

```text
api/agent/skills/example-skill/
├── SKILL.md
└── scripts/
    └── base.py
```

`SKILL.md` 应说明：

- 触发场景。
- 输入要求。
- 可调用脚本。
- 输出格式。
- 安全边界。
- 失败时如何降级。

## API 摘要

- `GET /api/health`：健康检查。
- `POST /api/auth/register`：注册用户。
- `POST /api/auth/jwt/login`：密码登录，返回 Bearer JWT。
- `POST /api/auth/jwt/logout`：JWT 登出。
- `GET /api/auth/users/me`：读取当前用户。
- `GET /api/auth/oauth/providers`：查看已启用 OAuth Provider。
- `GET /api/auth/github/authorize` / `GET /api/auth/github/callback`：GitHub OAuth2。
- `GET /api/auth/google/authorize` / `GET /api/auth/google/callback`：Google OAuth2。
- `GET /api/auth/microsoft/authorize` / `GET /api/auth/microsoft/callback`：Microsoft OAuth2。
- `POST /api/chat`：Agent 流式对话。
- `GET /api/chat/sessions`：会话列表。
- `GET /api/chat/sessions/{session_id}`：会话历史。
- `DELETE /api/chat/sessions/{session_id}`：软归档会话，不删除 Agno runs/traces。
- `POST /api/cve/search`：CVE 查询。
- `POST /api/cve/update`：更新 CVE 数据。
- `POST /api/asset/search`：资产查询。
- `POST /api/url2md/parse`：URL 转 Markdown。
- `GET /api/settings` / `PUT /api/settings`：系统配置。
- `GET /api/models` / `PUT /api/models`：模型配置。
- `GET /api/traces` / `GET /api/traces/{trace_id}`：运行观测。
- `GET /api/os/sessions`：AgentOS 会话库存。
- `GET /api/os/studio`：Agent、Team、MCP、Hi-Agent 和 Skills 组件注册视图。
- `GET /api/os/memory`：Agno memory 库存与增长状态。
- `GET /api/os/metrics`：会话、Trace、Span、错误和 Memory 聚合指标。
- `GET /api/os/evaluation`：评测 registry。
- `GET /api/os/approvals`：审批 registry。
- `GET /api/os/scheduler`：调度 registry。
- `GET /api/skills` / `PUT /api/skills/{name}/toggle`：Skills 管理。
- `GET /api/mcp/config` / `POST /api/mcp/config`：MCP 服务开关。
- `GET /api/mcp/tokens` / `POST /api/mcp/tokens/issue` / `POST /api/mcp/tokens/delete`：MCP Token。
- `GET /api/mcp/hiagent` / `POST /api/mcp/hiagent/*`：Hi-Agent MCP 接入。
- `GET /api/knowledge`：知识库状态与文档列表。
- `POST /api/knowledge/documents/text`：写入文本知识。
- `POST /api/knowledge/documents/file`：写入本地文本/Markdown 文件。
- `POST /api/knowledge/search`：检索知识库。
- `DELETE /api/knowledge/documents/{doc_id}`：删除单个知识文档。
- `DELETE /api/knowledge`：清空知识库。

## 质量检查

Python 语法、类型和风格检查：

```bash
uv run ruff check .
uv run ty check .
```

前端构建检查：

```bash
cd frontend
npm run test:auth
npm run test:shell
npm run build
```

界面回归检查：

```bash
# 启动 frontend 开发服务后使用 Playwright 截图检查登录页和工作台
cd frontend
npm run dev
playwright-cli open http://localhost:5173
```

## 技术文档

- `docs/agent-os-control-plane.md`：Agno OS 参考图差距、Agno docs MCP 审查、FastMCP docs MCP 审查、会话软归档和本轮控制面实现范围。
- `docs/superpowers/specs/2026-07-01-agentos-control-plane-design.md`：控制面设计规格。
- `docs/superpowers/plans/2026-07-01-agentos-control-plane.md`：实现计划与验证步骤。

## 运行时文件

以下文件属于本地运行状态，不应提交：

- `.env`
- `logs/`
- `tmp/`
- `*.db`
- `.run_update_cve.lock`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`

## 发展路线

### 阶段一：可用安全中台

目标是让平台稳定完成日常安全运营任务。

- 完成 CVE、资产、URL 情报、Agent 对话、MCP 工具、Skills 和运行观测的基础闭环。
- 完成模型路由配置，支持多模型选择。
- 完成 PgVector 基础知识库接入。
- 完成前后端暗黑模式、信息架构和核心页面可读性优化。
- 完成 AgentOS 风格 Sessions、Studio、Memory、Metrics、Evaluation、Approvals 和 Scheduler 轻量控制面。
- 完成 Chat 会话软归档、Trace Queue 左侧展开和 Dashboard 多图表态势总览。

### 阶段二：Agent 能力增强

目标是让 Agent 从“能调用工具”升级为“能稳定完成任务”。

- 将单 Agent 拆分为情报分析 Agent、资产研判 Agent、处置剧本 Agent 和知识库研判 Agent。
- 引入 Agno Team，支持多 Agent 协同。
- 增加结构化输出，用 Pydantic 固定漏洞研判、资产风险和处置建议格式。
- 增加 session summary、长期 memory 和用户偏好记忆。
- 将 Evaluation、Approvals 和 Scheduler 从 registry scaffolding 接入真实执行器。
- 增加 tool call guardrail，限制危险操作和未授权 PoC 指令。

### 阶段三：RAG 知识库增强

目标是让内部知识成为 Agent 的稳定上下文来源。

- 支持更多 embedding 模型配置和索引重建。
- 支持 Markdown、PDF、HTML、CSV、JSON、网页和 Git 仓库导入。
- 支持 metadata filters，例如业务线、资产组、漏洞类型、报告来源、时间范围。
- 扩展 reranker 配置和评估，提高长文档和相似漏洞检索质量。
- 在前端展示引用来源、命中 chunk、相似度和知识更新时间。

### 阶段四：运营闭环

目标是从“辅助研判”升级为“可观测、可评估、可追踪的安全运营系统”。

- 接入 Agent 评测，包括准确性、可靠性、工具调用成功率和响应延迟。
- 建立任务状态机，支持排队、审批、执行、回滚和审计。
- 将 MCP 工具调用与 SOAR、工单、告警平台联动。
- 建设低代码工作流编排层，统一承载 SOAR 剧本、MCP 工具、人工审批和 Agent 推荐。
- 建立风险态势页面，展示漏洞、资产、告警、Agent 任务和处置进展。
- 增加权限模型、审计日志和敏感配置加密。

## 规划路线

### 短期计划

- 为知识库增加前端管理页面。
- 支持 embedding 模型配置和向量重建。
- 增加 RAG 检索引用展示。
- 修复前端构建环境依赖一致性，确保 `npm run build` 可稳定输出到 `source/`。
- 为核心服务补充最小单元测试。

### 中期计划

- 引入 Agno Team，拆分专业 Agent。
- 建立标准化漏洞研判输出 schema。
- 增加 Agent 运行质量指标和失败原因归类。
- 支持 MCP 工具权限分级和执行审批。
- 支持更多知识源导入，包括报告目录、网页、Git 仓库和安全文档库。
- 增加低代码工作流原型，优先支持现有 SOAR 剧本编排和执行观测。

### 长期计划

- 建设面向 SOC 的任务编排和闭环处置能力。
- 评估将现有 SOAR 能力嵌入中台，或基于开源编排平台进行二次开发。
- 建设企业内部安全知识图谱。
- 支持多租户、RBAC、审计和配置加密。
- 支持离线部署和私有模型/私有 embedding 服务。
- 形成安全运营数据、工具、知识和 Agent 的统一控制平面。
