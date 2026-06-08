# Agno AIOS AI 信息安全中台

Agno AIOS 是一个基于 FastAPI、Vue 3、Agno 和 FastMCP 的 AI 信息安全中台。系统把 CVE 情报、资产画像、网页情报解析、Agent 对话、运行观测、Skills 管理和 MCP 工具中枢整合到同一个主服务中，不再依赖独立 MCP-Server 进程。

## 核心功能

- **AI 安全助手**：流式 Agent 对话，可在输入框旁选择模型，支持会话历史。
- **CVE 情报**：按 CVE 编号、应用名或关键词检索漏洞与 PoC 来源。
- **资产搜索**：基于指纹或 IP 查询资产画像。
- **URL 转 Markdown**：解析网页正文并转换为 Markdown。
- **运行观测**：基于 Agno Trace/Span 数据查看运行链路、耗时和错误。
- **态势总览**：展示 Agent 运行成功率、耗时分布和错误态势。
- **MCP 工具中枢**：同进程 FastMCP 服务开关、Token 和 Hi-Agent MCP 管理。
- **Skills 管理**：启用、禁用和查看本地 `.skills/` 能力包。

## 项目结构

```text
.
├── api/
│   ├── main.py                 # FastAPI 应用入口
│   ├── routes/                 # API 路由
│   ├── services/               # 业务逻辑
│   ├── mcp/                    # 内置 FastMCP 运行时
│   │   ├── server.py           # MCP ASGI 入口
│   │   ├── config.py           # MCP 配置、Token、Hi-Agent 状态
│   │   └── tools/              # 内置 MCP 工具模块
│   ├── models/                 # Pydantic 数据模型
│   ├── utils/                  # 数据库与数据处理工具
│   └── data/                   # CVE/资产数据缓存
├── .skills/                    # Agent 可加载的本地技能
├── frontend/                   # Vue 3 + TypeScript + UnoCSS 前端源码
├── source/                     # 前端生产构建输出，供 FastAPI 托管
├── config.toml                 # 数据源配置
├── update_cve.py               # CVE 数据更新脚本
├── update_ip_asset.py          # IP 资产数据更新脚本
├── update_utils.py             # 数据更新公共逻辑
├── run_update_cve.sh           # CVE 定时更新包装脚本
├── pyproject.toml              # Python 依赖与项目配置
└── README.md
```

## 环境要求

- Python 3.12+
- uv
- Bun 1.3+ 或 Node.js 18+
- MySQL 5.7+

## 安装

```bash
uv sync

cd frontend
bun install
```

## 配置

创建 `.env` 文件或设置环境变量：

```bash
# MySQL
MYSQL_TEST_HOST=localhost
MYSQL_TEST_USER=root
MYSQL_TEST_PASSWORD=your_password
MYSQL_TEST_DATABASE=cve_db
MYSQL_TEST_PORT=3306

# ACL 资产数据更新
ACL_USERNAME=your_username
ACL_PASSWORD=your_password

# 日志
LOG_LEVEL=INFO
LOG_DIR=logs

# Agent / MCP
MCP_SERVER_URL=http://127.0.0.1:8000/mcp/
MCP_TOKEN=your_mcp_access_token
AGENT_TIMEZONE=Asia/Shanghai
```

模型参数不再通过 `LLM_*` 环境变量维护。启动服务后进入 **系统配置 -> 模型路由**，配置 API Key、Base URL、Model ID、启用状态和默认模型；运行时配置会保存到 `tmp/model_config.json`。

## 数据库初始化

```sql
CREATE DATABASE cve_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE cve_db;

CREATE TABLE IF NOT EXISTS cves (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cve_id VARCHAR(255) NOT NULL,
    description TEXT,
    github_url VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL,
    create_time DATETIME,
    UNIQUE KEY unique_cve_url (cve_id, github_url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 启动

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

开发前端：

```bash
cd frontend
bun run dev
```

访问 `http://localhost:5173`。

生产构建：

```bash
cd frontend
bun run build
```

前端产物会输出到仓库根目录 `source/`，由后端静态资源服务托管。

## MCP 工具中枢

MCP 已完全整合进主 API 进程：

- MCP 协议入口：`/mcp/`
- 管理 API：`/api/mcp/*`
- 配置文件：`tmp/mcp/mcp_config.toml`
- Token 数据库：`tmp/mcp/mcp_tokens.db`
- 访问方式：`Authorization: Bearer <token>` 或 `/mcp/?token=<token>`

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
5. 在 `frontend/src/components/McpManage.vue` 的服务卡片列表中增加该服务。
6. 执行 `uv run ruff check .` 和 `bun run build`。

## Skills

本地能力放在 `.skills/<skill-name>/`，每个 Skill 至少包含一个 `SKILL.md`。需要稳定执行的数据访问或分析逻辑放入 `scripts/`。

当前内置能力：

- `threat-trace-skill`：威胁情报检索与研判。
- `darknet-trace-skill`：暗网泄露信息态势分析。
- `intranet-ip-skill`：内网告警/资产风险分析。
- `playbook-skill`：安全剧本调用规范。
- `cve-intel-skill`：CVE/应用漏洞情报、PoC 来源和风险态势分析。

新增 Skill 示例：

```text
.skills/example-skill/
├── SKILL.md
└── scripts/
    └── example.py
```

`SKILL.md` 需要包含 YAML frontmatter：

```markdown
---
name: example-skill
description: 示例安全能力，说明触发场景和能力边界。
---

# SOP

1. 明确输入。
2. 调用脚本获取事实。
3. 基于事实输出结论，禁止编造。
```

## CVE 情报 Skill 调用

```bash
uv run python .skills/cve-intel-skill/scripts/cve_intel.py --query CVE-2023-6019 --limit 20
uv run python .skills/cve-intel-skill/scripts/cve_intel.py --query Ray --limit 20 --latest 3
```

脚本优先查询 MySQL `cves` 表；数据库不可用或无命中时回退读取 `api/data/github_cve_cache.csv` 与 `api/data/exploit_db.csv`。

## 数据更新

CVE 数据：

```bash
uv run update_cve.py
uv run update_cve.py --source github
uv run update_cve.py --source exploit-db
```

IP 资产数据：

```bash
uv run update_ip_asset.py
```

定时任务示例：

```bash
# 每天 08:00 更新 CVE 数据
0 8 * * * cd /home/shenss/python/Agno-AIOS && ./run_update_cve.sh >> logs/cron_cve.log 2>&1

# 每天 03:00 更新 IP 资产数据
0 3 * * * cd /home/shenss/python/Agno-AIOS && uv run update_ip_asset.py >> logs/cron_asset.log 2>&1
```

## API 摘要

- `POST /api/chat`：Agent 流式对话。
- `GET /api/chat/sessions`：会话列表。
- `GET /api/chat/sessions/{session_id}`：会话历史。
- `DELETE /api/chat/sessions/{session_id}`：删除会话。
- `POST /api/cve/search`：CVE 查询。
- `POST /api/cve/update`：更新 CVE 数据。
- `POST /api/asset/search`：资产查询。
- `POST /api/url2md/parse`：URL 转 Markdown。
- `GET /api/models` / `PUT /api/models`：模型配置。
- `GET /api/traces` / `GET /api/traces/{trace_id}`：运行观测。
- `GET /api/skills` / `PUT /api/skills/{name}/toggle`：Skills 管理。
- `GET /api/mcp/config` / `POST /api/mcp/config`：MCP 服务开关。
- `GET /api/mcp/tokens` / `POST /api/mcp/tokens/issue` / `POST /api/mcp/tokens/delete`：MCP Token。
- `GET /api/mcp/hiagent` / `POST /api/mcp/hiagent/*`：Hi-Agent MCP 接入。

## 技术栈

- 前端：Vue 3、TypeScript、Element Plus、UnoCSS、Vite(Rolldown)、markdown-it、highlight.js。
- 后端：FastAPI、Uvicorn、aiomysql、httpx、Polars、loguru、python-dotenv。
- Agent：Agno、OpenAILike、LocalSkills、SqliteDb、Tracing。
- MCP：FastMCP，同进程 ASGI 挂载。

## 代码质量

```bash
uv run ruff check .
uv run ruff format .

cd frontend
bun run build
```

## 运行时文件

以下文件属于本地运行状态，不应提交：

- `.env`
- `logs/`
- `tmp/`
- `*.db`
- `__pycache__/`
- `.ruff_cache/`

## 故障排除

- 数据库连接失败：检查 MySQL 服务、`.env`、数据库权限和 `cves` 表。
- 前端无法访问后端：确认 API 运行在 `8000`，开发代理配置在 `frontend/vite.config.ts`。
- MCP 初始化失败：确认主 API 已启动、`MCP_TOKEN` 与中台签发 Token 一致、访问路径为 `/mcp/`。
- 数据更新失败：检查网络、`config.toml` 数据源和 `api/data/` 写入权限。
