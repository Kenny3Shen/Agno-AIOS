# Agno AIOS

Agno AIOS 是面向安全运营的 AgentOS 控制面与 AI 信息安全中台。系统把 Agent 对话、会话与 Trace 观测、MCP 工具、Skills、知识库、CVE 情报、资产查询和审计权限收敛到一个 FastAPI + Vue 应用中。

设计原则是安全优先：所有用户数据绑定 `user_id`，后端按当前 JWT 用户做权限过滤，前端隐藏入口不作为安全边界。

## 技术栈

- 前端：Vue 3、TypeScript、Vite/Rolldown、Element Plus、Pinia、vue-i18n、markdown-it、highlight.js、Mermaid、Bun。
- 后端：FastAPI、FastAPI Users、SQLAlchemy Async、Pydantic Settings、Uvicorn、psycopg、psycopg-pool、httpx、Polars、loguru。
- Agent：Agno、OpenAI-compatible model、PostgresDb、Tracing、PgVector Knowledge、LocalSkills、MCPTools。
- MCP：FastMCP，同进程 ASGI 挂载在 `/mcp/`。
- 数据库：PostgreSQL + pgvector，按 `app`、`agno`、`mcp`、`knowledge` schema 分域。
- 工具链：uv、ruff、ty、Bun、Playwright。JavaScript 清单只保留 `frontend/package.json` 与 `frontend/bun.lock`。

## 架构图

```text
Browser
  |
  | Vue 3 Control Plane
  | - Chat / Trace / MCP / Skills / Knowledge
  | - CVE / Assets / Collect / Settings
  v
FastAPI API
  |
  +-- Auth & RBAC
  |     FastAPI Users, JWT, roles: admin/user/guest
  |
  +-- Agent Runtime
  |     Agno Agent, streaming chat, sessions, traces, skills, knowledge
  |
  +-- FastMCP Runtime
  |     /mcp/ protocol endpoint, token validation, built-in tools
  |
  +-- Security Data APIs
  |     CVE search, asset search, URL collection, model settings
  |
  v
PostgreSQL + pgvector
  |
  +-- app         auth-adjacent app tables, audit logs, CVE data
  +-- agno        sessions, traces, spans, memory-style Agent data
  +-- mcp         MCP tokens, service config, Hi-Agent cache
  +-- knowledge   Agno content table and PgVector embeddings
```

## 关键能力

- Chat：流式 Agent 对话，支持自动滚动、Token streaming 动画、Markdown loading skeleton、代码块复制、Mermaid、图片缩放、来源折叠、thinking 折叠和 tool call timeline。
- Trace：按 `session_id`、状态、时间范围等参数查询 Trace，查看 Span 瀑布、树结构、错误上下文和属性详情。
- MCP：管理 FastMCP 服务开关、访问 Token、Hi-Agent 接入和内置工具。
- Skills：启用、禁用和查看 `api/agent/skills/` 下的本地能力包。
- Knowledge：基于 Agno Knowledge、PostgresDb 和 PgVector 的 RAG 知识库。
- AgentOS 控制面：提供 Sessions、Studio、Memory、Metrics、Evaluation、Approvals、Scheduler 等控制面数据视图。
- 安全数据：CVE 检索、资产查询、URL 转 Markdown、模型路由配置。
- 审计：记录登录、登出、删除、Knowledge、MCP、Skill、Settings 和管理员操作。

## 权限模型

角色采用 RBAC：

| Role      | 权限                                                         |
| --------- | ------------------------------------------------------------ |
| `admin` | 读取和操作全部用户数据，读取 Audit Log。                     |
| `user`  | 读取/写入自己的 Session、Chat、Knowledge，读取自己的 Trace。 |
| `guest` | 只读自己的资源。                                             |

后端会从 JWT 当前用户推导权限和 `user_id`：

- Session、Chat、Trace、Knowledge 查询默认限定当前用户。
- 非 admin 用户不能查看、删除或修改其他用户资源。
- Admin 可以跨用户查看 Trace、Session 和 Conversation。
- 猜测其他用户 `session_id` 会被权限检查拦截。
- 前端菜单隐藏只是体验优化，所有后台接口都必须通过权限校验。

## Agno 数据设计

数据库字段参考 Agno 文档：

- [Session Storage](https://docs.agno.com/database/session-storage)
- [Async PostgreSQL](https://docs.agno.com/database/providers/async-postgres/overview)

Session 记录遵循 Agno session schema 的核心字段：

```text
session_id
session_type
agent_id
team_id
workflow_id
user_id
session_data
agent_data
team_data
workflow_data
metadata
runs
summary
created_at
updated_at
```

Agno 文档将 `agno_sessions` 描述为按 `(user_id, session_id)` 保存会话历史。本项目沿用这个模型：`session_id` 不是授权凭据，所有查询必须同时匹配当前 `user_id` 或通过 admin 权限。

## 项目结构

```text
.
├── api/
│   ├── main.py                 # FastAPI 入口
│   ├── auth/                   # FastAPI Users、RBAC、bootstrap admin
│   ├── routes/                 # API 路由
│   ├── services/               # Agent、Trace、Knowledge、Audit 等服务
│   ├── mcp/                    # FastMCP runtime 和工具注册
│   ├── agent/skills/           # 本地 Skills
│   ├── tasks/                  # CVE/资产更新、数据库迁移脚本入口
│   ├── tests/                  # 后端单元测试
│   └── data/                   # 本地安全数据缓存
├── frontend/
│   ├── src/components/         # 控制面页面
│   ├── src/stores/             # Pinia 状态
│   ├── src/i18n/               # 中英文文案
│   └── src/styles/             # 设计 token
├── source/                     # 前端生产构建输出，由 FastAPI 托管
├── scripts/                    # 运维脚本
├── docs/                       # 设计与实现文档
├── AGENTS.md                   # 本仓库开发约定
├── pyproject.toml
└── README.md
```

## 环境要求

- WSL2 Ubuntu 24.04 或 Linux。
- Python 3.12+。
- uv。
- Bun，仓库默认路径为 `/home/shenss/.bun/bin/bun`。
- PostgreSQL 15/16 + pgvector。

## 配置

创建 `.env`：

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

# Auth
AUTH_JWT_SECRET=replace-with-long-random-secret
AUTH_RESET_PASSWORD_SECRET=replace-with-long-random-secret
AUTH_VERIFICATION_SECRET=replace-with-long-random-secret
AUTH_OAUTH_STATE_SECRET=replace-with-long-random-secret
AUTH_TOKEN_LIFETIME_SECONDS=3600
AUTH_COOKIE_SECURE=false

# Manual acceptance admin account.
# This account is created or promoted at API startup only when both values are set.
AGNO_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
AGNO_BOOTSTRAP_ADMIN_PASSWORD=AdminPass123!

# MCP
MCP_SERVER_URL=http://127.0.0.1:8000/mcp/
MCP_TOKEN=your_mcp_access_token

# Knowledge
AGNO_KNOWLEDGE_PGVECTOR_TABLE=security_knowledge_vectors
AGNO_POSTGRES_KNOWLEDGE_TABLE=agno_knowledge
AGNO_KNOWLEDGE_NAME=security_knowledge
AGNO_KNOWLEDGE_TOP_K=5
AGNO_KNOWLEDGE_CHUNK_SIZE=1200
AGNO_KNOWLEDGE_CHUNK_OVERLAP=160
AGNO_KNOWLEDGE_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
AGNO_KNOWLEDGE_EMBEDDING_DIMENSIONS=512
AGNO_KNOWLEDGE_RERANK_MODEL=BAAI/bge-reranker-base
AGNO_KNOWLEDGE_RERANK_ENABLED=true

# OAuth, optional
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
MICROSOFT_OAUTH_CLIENT_ID=
MICROSOFT_OAUTH_CLIENT_SECRET=
MICROSOFT_OAUTH_TENANT=common

# External security data, optional
ACL_USERNAME=
ACL_PASSWORD=
TOKEN=
```

人工验收 admin 账号：

```text
Email: admin@example.com
Password: AdminPass123!
Role: admin
```

该账号不是硬编码默认账号。只有 `.env` 设置了 `AGNO_BOOTSTRAP_ADMIN_EMAIL` 和 `AGNO_BOOTSTRAP_ADMIN_PASSWORD` 后，API 启动时才会创建或提升为 admin。

## 数据库初始化

Ubuntu 本地 PostgreSQL 示例：

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo pg_ctlcluster 16 main start
```

创建数据库、schema 和 pgvector：

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

API 启动会自动确保以下对象存在：

- FastAPI Users 的 `user`、`oauth_account` 表。
- `role` 字段。
- bootstrap admin 账号。
- app/audit/session archive 等应用表。
- MCP token/config/cache 表。
- Agno session、trace、knowledge 相关表在对应功能首次使用时创建。

## 启动

安装后端依赖：

```bash
uv sync
```

安装前端依赖：

```bash
cd frontend
/home/shenss/.bun/bin/bun install
```

启动 API：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端开发服务：

```bash
cd frontend
/home/shenss/.bun/bin/bun run dev
```

开发访问：

```text
http://localhost:5173
```

生产构建：

```bash
cd frontend
/home/shenss/.bun/bin/bun run build
```

构建产物写入 `source/`，由 FastAPI 静态服务托管。

## 常用 API

- `GET /api/health`：健康检查。
- `POST /api/auth/register`：注册。
- `POST /api/auth/jwt/login`：登录并返回 Bearer JWT。
- `POST /api/auth/logout`：登出并写入审计日志。
- `GET /api/auth/users/me`：当前用户。
- `POST /api/chat`：Agent 流式对话。
- `GET /api/chat/sessions`：当前用户会话列表，admin 可跨用户。
- `GET /api/chat/sessions/{session_id}`：会话历史。
- `DELETE /api/chat/sessions/{session_id}`：软归档会话。
- `GET /api/traces`：Trace 列表。
- `GET /api/traces/{trace_id}`：Trace 详情。
- `GET /api/audit/logs`：审计日志，admin only。
- `GET /api/knowledge`：知识库状态。
- `POST /api/knowledge/documents/text`：写入文本知识。
- `POST /api/knowledge/documents/file`：写入本地文件。
- `POST /api/knowledge/search`：检索知识库。
- `GET /api/mcp/config` / `POST /api/mcp/config`：MCP 服务配置。
- `GET /api/mcp/tokens` / `POST /api/mcp/tokens/issue`：MCP token。
- `GET /api/skills` / `PUT /api/skills/{name}/toggle`：Skills。
- `POST /api/cve/search` / `POST /api/cve/update`：CVE。
- `POST /api/asset/search`：资产。
- `POST /api/url2md/parse`：URL 转 Markdown。
- `GET /api/os/*`：AgentOS 控制面数据。

## 数据更新

从旧 MySQL 迁移：

```bash
uv run migrate-mysql-to-postgres
```

更新 CVE：

```bash
uv run update-cve
```

更新资产：

```bash
uv run update-ip-asset
```

定时任务示例：

```bash
0 8 * * * cd /home/shenss/python/Agno-AIOS && ./scripts/run_update_cve.sh >> logs/cron_cve.log 2>&1
0 3 * * * cd /home/shenss/python/Agno-AIOS && uv run update-ip-asset >> logs/cron_asset.log 2>&1
```

## 开发与验证

Python 检查：

```bash
uv run ruff check .
uv run ty check .
uv run python -m unittest discover api/tests
```

前端检查：

```bash
cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

Playwright smoke：

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
cd frontend
/home/shenss/.bun/bin/bunx playwright screenshot --full-page http://127.0.0.1:8000 ../.playwright-cli/agno-aios.png
```

## 运行时文件

以下文件属于本地运行状态，不应提交：

- `.env`
- `logs/`
- `data/config/` 中的本地运行配置文件
- `.playwright-check/`
- `frontend/dist-test/`
- `*.db`
- `.run_update_cve.lock`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`

`source/` 是前端生产构建输出。本仓库当前由 FastAPI 直接托管该目录，执行前端 build 后会更新其中的 hash 文件。
