# Agno AIOS AI 信息安全中台

Agno AIOS 是一个面向安全运营场景的 AI 信息安全中台。系统基于 FastAPI、Vue 3、Agno、FastMCP 和 ChromaDB，把 CVE 情报、资产画像、网页情报解析、Agent 对话、运行观测、MCP 工具中枢、Skills 能力包和基础 RAG 知识库整合到同一个主服务中。

当前目标不是做一个通用聊天页面，而是构建可持续扩展的安全 Agent 工作台：安全人员可以在一个界面内完成情报查询、漏洞研判、资产排查、剧本调用、知识检索和运行观测。

## 核心能力

- **AI 安全助手**：基于 Agno Agent 的流式对话，支持模型切换、会话历史、MCP 工具、Skills 和知识库检索。
- **CVE 情报**：按 CVE 编号、应用名或关键词检索漏洞记录和 PoC 来源。
- **资产搜索**：基于指纹或 IP 查询资产画像。
- **URL 转 Markdown**：抓取网页正文并转换为 Markdown，便于情报沉淀。
- **运行观测**：查看 Agent Trace/Span、耗时、错误和运行链路。
- **态势总览**：展示 Agent 运行成功率、耗时分布和错误态势。
- **MCP 工具中枢**：FastMCP 与主 API 同进程运行，支持服务开关、Token 和 Hi-Agent MCP 接入。
- **Skills 管理**：启用、禁用和查看本地 `api/agent/skills/` 能力包。
- **RAG 知识库**：基于 ChromaDB 的本地知识库，Agent 可通过 `search_knowledge_base` 检索内部资料。

## 技术栈

- 前端：Vue 3、TypeScript、Element Plus、UnoCSS、Vite/Rolldown、markdown-it、highlight.js。
- 后端：FastAPI、Uvicorn、aiomysql、httpx、Polars、loguru、python-dotenv。
- Agent：Agno、OpenAILike、LocalSkills、SqliteDb、Tracing、ChromaDB RAG。
- MCP：FastMCP，同进程 ASGI 挂载。
- 包管理：uv、Bun。

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
├── frontend/                   # Vue 3 + TypeScript + UnoCSS 前端源码
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
- Bun 1.3+ 或 Node.js 18+
- MySQL 5.7+

## 快速启动

安装后端依赖：

```bash
uv sync
```

安装前端依赖：

```bash
cd frontend
bun install
```

启动后端：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端开发服务：

```bash
cd frontend
bun run dev
```

开发访问地址：

```text
http://localhost:5173
```

生产构建前端：

```bash
cd frontend
bun run build
```

构建产物会输出到仓库根目录 `source/`，并由 FastAPI 静态资源服务托管。

## 配置说明

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
AGNO_SKILLS_DIR=api/agent/skills
AGNO_SKILLS_CONFIG_FILE=tmp/skills_config.json

# RAG 知识库，可选
AGNO_KNOWLEDGE_CHROMA_PATH=tmp/chroma
AGNO_KNOWLEDGE_INDEX_FILE=tmp/knowledge_docs.json
AGNO_KNOWLEDGE_COLLECTION=security_knowledge
AGNO_KNOWLEDGE_TOP_K=5
```

模型参数不再通过 `LLM_*` 环境变量维护。启动服务后进入 **系统配置 -> 模型路由**，配置 API Key、Base URL、Model ID、启用状态和默认模型。运行时配置会保存到：

```text
tmp/model_config.json
```

MCP 配置和 Token 会保存到：

```text
tmp/mcp/mcp_config.toml
tmp/mcp/mcp_tokens.db
```

知识库文件会保存到：

```text
tmp/chroma
tmp/knowledge_docs.json
```

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

## 数据更新

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
- 使用 `SqliteDb` 保存会话和运行记录。
- 使用 Agno tracing 记录运行链路。
- 通过 `knowledge_retriever` 接入 ChromaDB 知识库。

Agent 在以下场景会优先检索知识库：

- 内部制度和处置规范。
- 历史报告和研判结论。
- 资产说明和业务背景。
- 漏洞风险研判资料。
- 用户明确要求基于已沉淀资料回答。

## RAG 知识库

当前知识库是基础可运行版本，默认使用本地哈希 embedding，不依赖外部 embedding API。该实现适合先跑通 Agent RAG 链路；生产环境建议升级为 OpenAI-compatible embedding、BGE、bge-m3 或企业内部向量服务。

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
6. 执行 `uv run ruff check .`、`ty check .` 和 `bun run build`。

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
- `POST /api/chat`：Agent 流式对话。
- `GET /api/chat/sessions`：会话列表。
- `GET /api/chat/sessions/{session_id}`：会话历史。
- `DELETE /api/chat/sessions/{session_id}`：删除会话。
- `POST /api/cve/search`：CVE 查询。
- `POST /api/cve/update`：更新 CVE 数据。
- `POST /api/asset/search`：资产查询。
- `POST /api/url2md/parse`：URL 转 Markdown。
- `GET /api/settings` / `PUT /api/settings`：系统配置。
- `GET /api/models` / `PUT /api/models`：模型配置。
- `GET /api/traces` / `GET /api/traces/{trace_id}`：运行观测。
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
ty check .
uv run ruff check .
uv run ruff format .
```

前端构建检查：

```bash
cd frontend
bun run build
```

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
- 完成 ChromaDB 基础知识库接入。
- 完成前后端暗黑模式、信息架构和核心页面可读性优化。

### 阶段二：Agent 能力增强

目标是让 Agent 从“能调用工具”升级为“能稳定完成任务”。

- 将单 Agent 拆分为情报分析 Agent、资产研判 Agent、处置剧本 Agent 和知识库研判 Agent。
- 引入 Agno Team，支持多 Agent 协同。
- 增加结构化输出，用 Pydantic 固定漏洞研判、资产风险和处置建议格式。
- 增加 session summary、长期 memory 和用户偏好记忆。
- 增加 tool call guardrail，限制危险操作和未授权 PoC 指令。

### 阶段三：RAG 知识库增强

目标是让内部知识成为 Agent 的稳定上下文来源。

- 把本地哈希 embedding 替换为可配置 embedding 模型。
- 支持 Markdown、PDF、HTML、CSV、JSON、网页和 Git 仓库导入。
- 支持 metadata filters，例如业务线、资产组、漏洞类型、报告来源、时间范围。
- 引入 reranker，提高长文档和相似漏洞检索质量。
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
- 修复前端构建环境依赖一致性，确保 `bun run build` 可稳定输出到 `source/`。
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
