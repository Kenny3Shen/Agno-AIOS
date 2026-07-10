# T.A.I.S (Trinity AI Security)

T.A.I.S 是一个 AI-powered SDLC security automation 项目，围绕 Discover、Remediate、Close 三位一体的安全闭环构建。

系统把漏洞与暴露面发现、Agent 辅助处置、Trace 观测、MCP 工具、本地 Skills、知识库检索、CVE 情报、URL 采集、审计日志和运行配置收敛到一个需要认证的工作台中。

## 文档

- [领域词汇表](./CONTEXT.md)
- [架构说明](./docs/architecture.md)
- [运行说明](./docs/operations.md)
- [安全模型](./docs/security.md)
- [开发工作流](./docs/development.md)
- [路线图](./docs/roadmap.md)
- [架构决策记录](./docs/adr/0001-react-mainline.md)

旧版 Vue + Element Plus 已保留在 `vue` 分支；`master` 作为 React 19 + TanStack + Ant Design v6 新版主线。

## 技术栈

- 前端：React 19、TypeScript、Vite 8/Rolldown、TanStack Router/Query、Ant Design v6、Ant Design X、i18next、UnoCSS、Bun。
- 后端：FastAPI、FastAPI Users、SQLAlchemy Async、Pydantic Settings、Uvicorn、psycopg、httpx、Polars、loguru。
- Agent Runtime：OpenAI-compatible models、AsyncPostgresDb、Tracing、PgVector Knowledge、LocalSkills、MCPTools。
- MCP：FastMCP，同进程挂载到 FastAPI 的 `/mcp/`，由应用 lifespan 启停运行时。
- 数据库：PostgreSQL + pgvector，按应用、运行时、MCP、知识库 schema 分域。
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
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
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

如果 API 不在默认 `8000`，启动前端开发服务时设置：

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8001 /home/shenss/.bun/bin/bun run dev
```

PostgreSQL 初始化、环境变量、生产式静态资源托管和数据更新任务见 [运行说明](./docs/operations.md)。

## 常用命令

Python 检查：

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
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
```

## 项目结构

```text
.
├── api/                 # FastAPI app、routes、services、auth、MCP runtime、tasks、tests
├── frontend/            # React 19 + TanStack + Ant Design 工作台
├── source/              # FastAPI 托管的前端生产构建
├── scripts/             # 运维脚本
├── docs/                # 新版架构、运行、安全、开发、路线图、ADR
├── CONTEXT.md           # 领域词汇表
├── README.md
├── pyproject.toml
└── uv.lock
```

## 安全原则

后端是安全边界。前端权限检查只用于隐藏导航和控件，改善体验；所有受保护的 API 操作都必须在后端执行权限检查和资源归属检查。见 [安全模型](./docs/security.md)。
