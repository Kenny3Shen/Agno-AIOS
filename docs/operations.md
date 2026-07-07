# 运行说明

本文描述当前仓库在本地和简单服务器环境中的运行方式。

## 环境要求

- WSL2 Ubuntu 24.04 或 Linux。
- Python 3.12 或更新版本。
- `uv`。
- Bun。当前仓库默认 `/home/shenss/.bun/bin/bun` 可用。
- PostgreSQL 15 或 16，并安装 pgvector。

## 环境变量

后端通过 Pydantic settings 从 `.env` 读取配置，部分运行时路径也会直接读取 process environment。基础配置形态如下：

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=agno_aios
POSTGRES_PASSWORD=agno_aios
POSTGRES_DB=agno_aios

AGNO_APP_SCHEMA=app
AGNO_DB_SCHEMA=agno
AGNO_MCP_SCHEMA=mcp
AGNO_KNOWLEDGE_SCHEMA=knowledge

AUTH_JWT_SECRET=replace-with-long-random-secret
AUTH_RESET_PASSWORD_SECRET=replace-with-long-random-secret
AUTH_VERIFICATION_SECRET=replace-with-long-random-secret
AUTH_OAUTH_STATE_SECRET=replace-with-long-random-secret
AUTH_TOKEN_LIFETIME_SECONDS=3600
AUTH_COOKIE_SECURE=false

MCP_SERVER_URL=http://127.0.0.1:8000/mcp/
MCP_TOKEN=replace-with-mcp-token
```

Knowledge RAG 参数可通过控制面临时调整，但 `/api/knowledge/settings/rag` 只更新当前 API process 的 environment overrides 并清理 runtime caches。需要跨重启保留时，把对应 `AGNO_KNOWLEDGE_*` 环境变量写入部署配置或 `.env`，不要依赖该 API 作为持久配置存储。

可选 bootstrap admin 只由显式环境变量控制：

```bash
AGNO_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
AGNO_BOOTSTRAP_ADMIN_PASSWORD=AdminPass123!
```

两者都存在时，API 启动会创建或提升该用户为 admin。没有同时配置这两个变量时，系统没有硬编码默认 admin。

## PostgreSQL 初始化

Ubuntu 本地示例：

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo pg_ctlcluster 16 main start
```

创建 database、schemas 和 pgvector：

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

API 也会在启动或功能首次使用时懒创建需要的 schemas 和 tables。

## 安装

后端：

```bash
uv sync
```

前端：

```bash
cd frontend
/home/shenss/.bun/bin/bun install
```

修改 `frontend/package.json` 时使用 Bun 命令：

```bash
cd frontend
/home/shenss/.bun/bin/bun add <package>
/home/shenss/.bun/bin/bun remove <package>
```

## 开发模式运行

API：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

前端开发服务：

```bash
cd frontend
/home/shenss/.bun/bin/bun run dev
```

访问：

```text
http://localhost:5173
```

阶段性验证使用预发端口 `8001`，避免和本地默认开发 API 冲突：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

如果前端开发服务需要连接 `8001`，设置：

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8001 /home/shenss/.bun/bin/bun run dev
```

## 生产式静态资源托管

构建前端资源：

```bash
cd frontend
/home/shenss/.bun/bin/bun run build
```

Vite 会把构建产物写入 `source/`。FastAPI app 在 `source/` 存在时托管 `source/`，否则托管 `frontend/dist`。

运行托管静态资源的 API：

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

访问：

```text
http://localhost:8000
```

## 数据更新

Console scripts 定义在 `pyproject.toml`。当前运维脚本只包含 CVE 数据更新：

```bash
uv run update-cve
```

Cron 示例：

```cron
0 8 * * * cd /home/shenss/python/Agno-AIOS && ./scripts/run_update_cve.sh >> logs/cron_cve.log 2>&1
```

## 运行时文件

以下文件和目录是本地运行状态，不应当作源码文档：

- `.env`
- `logs/`
- `tmp/`
- `data/config/`
- `.playwright-cli/`
- `frontend/dist-test/`
- `*.db`
- `tmp/run_update_cve.lock`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`

`source/` 是当前由 FastAPI 托管的前端生产构建产物。

## 快速检查

后端健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

预发端口检查：

```bash
curl http://127.0.0.1:8001/api/health
```

MCP endpoint 需要有效 token：

```bash
curl 'http://127.0.0.1:8000/mcp/?token=YOUR_MCP_TOKEN'
```

如果 Chat 能回答但 tools 或 knowledge 不可用，优先检查 `MCP_SERVER_URL`、`MCP_TOKEN`、model configuration、enabled skills 和 PostgreSQL connectivity。
