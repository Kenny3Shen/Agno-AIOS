# Agno AIOS

Agno AIOS 是一个面向安全运营的控制面和 AI 安全运营平台，基于 FastAPI、Vue、Agno、FastMCP、PostgreSQL 和 pgvector 构建。

系统把 Agent 对话、会话、Trace 观测、MCP 工具、本地 Skills、知识库检索、CVE 情报、URL 采集、审计日志、设置和 AgentOS 控制视图收敛到一个需要认证的工作台中。

## 文档

- [领域词汇表](./CONTEXT.md)
- [架构说明](./docs/architecture.md)
- [运行说明](./docs/operations.md)
- [安全模型](./docs/security.md)
- [开发工作流](./docs/development.md)
- [路线图](./docs/roadmap.md)
- [架构决策记录](./docs/adr/)

## 技术栈

- 前端：Vue 3、TypeScript、Vite/Rolldown、Element Plus、Pinia、vue-i18n、markdown-it、highlight.js、Mermaid、Bun。
- 后端：FastAPI、FastAPI Users、SQLAlchemy Async、Pydantic Settings、Uvicorn、psycopg、httpx、Polars、loguru。
- Agent Runtime：Agno、OpenAI-compatible models、PostgresDb、Tracing、PgVector Knowledge、LocalSkills、MCPTools。
- MCP：FastMCP，同进程挂载到 FastAPI 的 `/mcp/`。
- 数据库：PostgreSQL + pgvector，按 `app`、`agno`、`mcp`、`knowledge` schema 分域。
- 工具链：uv、ruff、ty、Bun、Playwright。

## 快速启动

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

访问：

```text
http://localhost:5173
```

PostgreSQL 初始化、环境变量、生产式静态资源托管和数据更新任务见 [运行说明](./docs/operations.md)。

## 常用命令

Python 检查：

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests
```

前端检查：

```bash
cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

数据更新脚本：

```bash
uv run update-cve
uv run migrate-mysql-to-postgres
```

## 项目结构

```text
.
├── api/                 # FastAPI app、routes、services、auth、MCP runtime、tasks、tests
├── frontend/            # Vue 控制面
├── source/              # FastAPI 托管的前端生产构建
├── scripts/             # 运维脚本
├── docs/                # 架构、运行、安全、开发、路线图、ADR
├── CONTEXT.md           # 领域词汇表
├── README.md
├── pyproject.toml
└── uv.lock
```

## 安全原则

后端是安全边界。前端权限检查只用于隐藏导航和控件，改善体验；所有受保护的 API 操作都必须在后端执行权限检查和资源归属检查。见 [安全模型](./docs/security.md)。
