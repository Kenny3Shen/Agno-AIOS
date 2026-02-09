# AgentOS 安全智能体平台 — 技术报告

> 日期：2026-02-07 | 版本：v1.0

---

## 一、架构概览

AgentOS 是一个面向安全运营场景的 AI Agent 平台，采用 **单 Agent + 多 Skill + MCP Tools** 架构，将大语言模型的推理能力与安全领域知识（威胁情报数据库、SOAR 剧本引擎）深度融合，实现从情报检索到自动化处置的闭环。

```
┌──────────────────────────────────────────────────────────────┐
│                     Vue 3 Frontend                           │
│   Session Sidebar │ Streaming Chat │ Markdown Render          │
└──────────┬───────────────────────────────────────────────────┘
           │ SSE (text/event-stream)
┌──────────▼───────────────────────────────────────────────────┐
│                     FastAPI Backend                           │
│   /api/chat (stream)  │  /api/chat/sessions  │  /api/settings│
└──────────┬───────────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────────┐
│               Agno Agent Runtime                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ LocalSkills │  │  MCP Tools   │  │   SqliteDb Session  │  │
│  │ (.skills/)  │  │ (Streamable) │  │  (security_agent.db)│  │
│  └──────┬──────┘  └──────┬───────┘  └─────────────────────┘  │
│         │                │                                   │
│  ┌──────▼──────┐  ┌──────▼────────────────────┐              │
│  │SKILL.md SOP │  │ w5-soar / octomation      │              │
│  │Python脚本    │   │ playbook_invoke_method()  │              │
│  └──────┬──────┘  └───────────────────────────┘              │
│         │                                                     │
│  ┌──────▼──────────────────┐                                  │
│  │ MySQL (dynamic_monitor) │                                  │
│  │ 威胁情报数据库           │                                  │
│  └─────────────────────────┘                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、为何选择 Agno 框架

### 2.1 核心设计理念：让模型做编排

在调研了 LangChain、CrewAI、AutoGen 等主流 Agent 框架后，最终选择 **Agno** 作为底层运行时，核心原因如下：

| 维度 | Agno | LangChain/LangGraph | CrewAI |
|------|------|---------------------|--------|
| **编排方式** | 模型自主编排（指令驱动） | 需手動定义状态图/链 | 预设角色+流程 |
| **复杂度** | 极低，仅需写 Skill + Prompt | 高，需理解 DAG/State Machine | 中，需定义 Task/Crew |
| **MCP 支持** | 原生内置 `MCPTools` | 需额外适配 | 不支持 |
| **Skill 热加载** | `LocalSkills` 文件夹即加载 | 不支持 | 不支持 |
| **会话持久化** | 内置 `SqliteDb` | 需手动集成 | 需手动集成 |
| **依赖量** | 轻量 (~50 deps) | 重量 (200+ deps) | 中量 |

### 2.2 "编排由模型完成"的哲学

传统 Agent 框架（如 LangGraph）要求开发者定义精确的执行图、状态转移和条件分支。这在安全运营场景中存在明显弊端：

1. **场景高度动态**：安全分析师的提问模式千变万化，"查询 CVE-2025-xxxx 的利用情况并执行对应剧本" 这类复合任务无法用静态 DAG 覆盖。
2. **维护成本高**：每新增一个能力，都需要修改编排逻辑、增加节点与边。

Agno 的方案截然不同：**只需提供能力（Skills + MCP Tools），由基座大模型根据用户意图自行决定调用顺序和参数组合**。开发者的工作简化为：

- 编写 **SKILL.md** 描述能力边界和 SOP
- 编写 **Python 脚本** 提供数据访问
- 通过 **MCP Server** 暴露外部工具

模型本身就是任务编排引擎。

### 2.3 轻量接入

将现有的 Team（多 Agent 协作）架构重构为单 Agent 后，核心代码仅约 30 行：

```python
security_agent = Agent(
    name="安全运营助手",
    instructions=[AGENT_INSTRUCTIONS],
    model=_build_model(),
    tools=[mcp_tools],                          # MCP 工具
    skills=Skills(loaders=[LocalSkills(".skills")]),  # 本地技能
    db=SqliteDb("security_agent.db"),            # 会话持久化
    add_history_to_context=True,
    num_history_runs=5,
    update_memory_on_run=True, # Automatic memory management
)
```

新增能力只需在 `.skills/` 下创建文件夹，无需改动任何 Agent 代码。

---

## 三、技术难点与解决方案

### 3.1 Skill 的设计与实现（核心难点）

#### 3.1.1 打通数据层与 API 层

Skill 体系的核心挑战在于：**如何让 LLM 安全、高效地访问私有数据源**。

以 `threat-trace-skill` 为例，需要解决以下问题：

| 问题 | 解决方案 |
|------|---------|
| LLM 无法直连 MySQL | 封装为独立 Python 脚本（`recall.py`、`finegrain.py`），Agent 通过 `get_skill_script` 调用 |
| 数据库连接池生命周期 | 使用 `aiomysql.Pool` 全局单例 + `close_pool.py` 显式释放 |
| 查询参数注入风险 | 使用参数化 SQL（`%s` 占位符），禁止字符串拼接 |
| 结果集过大影响 Token | 两阶段检索：`recall` 返回轻量摘要 → `finegrain` 按需获取详情 |
| 时效性控制 | 引入 `--days` 参数（默认 90 天），使用 `DATE_SUB(NOW(), INTERVAL %s DAY)` 时间窗口过滤 |

**两阶段检索模式**是关键设计：

```
用户查询 "Notepad++ 威胁情报"
    │
    ▼
recall.py --keywords "Notepad++" --days 90
    │ 返回 [{id: 42343, title: "..."}, {id: 42189, title: "..."}, ...]
    ▼
Agent 自主筛选相关 ID
    │
    ▼
finegrain.py --ids "42343,42189,42085,42002"
    │ 返回完整 description、url、public_time
    ▼
Agent 合成情报报告
```

这种设计让 Agent 能够先"概览"再"深挖"，避免一次性拉取大量数据消耗 Token，同时保留了 LLM 对中间结果的审查和筛选能力。

#### 3.1.2 SKILL.md 即 SOP

每个 Skill 目录下的 `SKILL.md` 既是元数据也是操作手册：

```yaml
---
name: threat-trace-skill
description: 威胁情报检索与分析技能
---
```

YAML frontmatter 用于 Agno 的 `LocalSkills` 加载器自动发现和注册，Markdown 正文作为 Agent 的执行指南注入上下文。这意味着：

- **非开发人员**可以通过编辑 Markdown 调整 Agent 行为
- **SOP 与代码同仓**，版本管理天然一致
- **新增 Skill** 只需创建 `<skill-name>/SKILL.md` + 对应脚本，零代码改动

#### 3.1.3 MCP Tools 集成

剧本执行能力通过 MCP（Model Context Protocol）协议接入：

```python
async with MCPTools(
    transport="streamable-http",
    url=f"{MCP_SERVER_URL}?token={MCP_TOKEN}",
    timeout_seconds=20,
) as mcp_tools:
    agent = Agent(tools=[mcp_tools], ...)
```

MCP 的优势在于：

- 工具定义由服务端动态提供，Agent 侧无需硬编码
- 支持 Streamable HTTP 传输，适合跨网络调用
- 工具签名自动转换为 LLM Function Calling 格式

#### 3.1.4 `intranet-ip-skill`：NDR 告警研判能力

`intranet-ip-skill` 提供对 **内网 NDR 告警** 的自动化研判能力，核心逻辑在 `.skills/intranet-ip-skill/agent.py` 中实现。该能力以 **doc_id** 为输入，通过 NDR 平台 API 拉取告警原始数据并完成清洗、结构化，然后交给专用 Agent 进行误报/真实/可疑判定。

**关键设计点：**

- **数据源打通**：
  - `get_data_from_doc_id(doc_id)` 使用 JSON-RPC 调用 `AlarmService.GetAlarmDocument`
  - 通过 `NDR_API_URL` 与 `NDR_API_TOKEN` 访问，避免 Agent 直接暴露内部凭据
- **字段清洗与语义压缩**：
  - 只保留告警研判必要字段（`name`、`cve_list`、`payload`、`http_details` 等）
  - 组装 `attacker_ip_port` / `victim_ip_port`，提高研判可读性
- **协议感知**：
  - 若存在 HTTP 协议详情，提取 `req_header/req_body/resp_status/resp_body`
  - 其他协议则保持 `protocol_details` 原样，避免丢失关键上下文
- **误报研判 SOP**：
  - 指令中明确三步分析框架：攻击特征匹配 → 响应分析 → 上下文判断
  - 输出标准化 Markdown（`verdict/confidence/analysis/evidence/suggestion`）便于复核与处置

**能力边界说明：**

- 该 Skill **只负责单条告警的深度分析**，不负责批量告警拉取与聚合
- 数据访问与清洗是核心价值点，避免 LLM 处理冗余字段导致噪声放大

#### 3.1.5 核心挑战：SOP 数字化与数据层打通

在构建这些安全技能的过程中，项目面临的最底层困难在于如何将人类专家的安全能力转化为机器可执行的指令流，并确保数据流的透明与安全：

1. **安全业务定义（标准化与语义对齐）**
    - **挑战**：安全分析 SOP 通常存在于非结构化文档或专家大脑中，充满模糊描述（如“检查异常流量”）。
    - **解决**：在 `SKILL.md` 中强制使用结构化的 Markdown 指令指南。通过明确的阶段划分（如：特征匹配 -> 响应分析 -> 环境研判），将模糊业务转化为 LLM 可理解的逻辑状态机。这使得 SOP 既是供人阅读的文档，也是 Agent 执行过程中的“策略底座”。

2. **数据安全访问（隔离与凭据管理）**
    - **挑战**：Agent 作为一个高频自动化的实体，如果直接持有高权限 API Token 并在上下文中流转，存在泄露或权限溢出风险。
    - **解决**：设计了**脚本代理机制（Script Proxy）**。Agent 不直接与底层数据库或私有平台通信，而是通过调用受限的 Python 脚本进行“中间人查询”。敏感凭据（如私有 API Key）仅保留在本地环境变量中，脚本仅向 Agent 返回经过脱敏后的 JSON 数据。这种“存算分离”的设计确保了 Agent 始终在预设的安全边界内运行。

3. **数据有效获取（噪声过滤与分级检索）**
    - **挑战**：安全日志原文包含大量无关元数据，直接喂给 LLM 会导致严重的 Token 浪费和注意力分散（Lost in the Middle）。
    - **解决**：实施**数据语义压缩策略**。在脚本层执行业务级清洗，过滤掉 90% 的冗余网络字段，仅保留核心 Payload 和上下文关联条目。同时，采用“概览检索 -> 按需深挖”的分级检索模式（如 `threat-trace-skill` 的设计），在信息完整性与计算资源消耗之间取得了最优平衡。

4. **数据有效分析（逻辑链条与证据闭环）**
    - **挑战**：LLM 的推理过程如果不加约束，容易产生“结论先行”的幻觉，缺乏可审计的证据链。
    - **解决**：在 SOP 中强制要求 **证据闭环（Evidence-Based Reasoning）**。Agent 被要求在输出的 `evidence` 字段中显式引用源数据中的关键证据（如特定的 HTTP 头或攻击 Paylod 偏移）。通过将“研判结论”与“支撑依据”强制解耦，确保了分析结果的可验证性，为后续自动化响应提供了高置信度的数据支撑。

---

### 3.2 流式对话与会话持久化

#### 3.2.1 SSE 流式传输

前端通过 `fetch` + `ReadableStream` 实现 Server-Sent Events 消费：

```
Browser ──POST /api/chat──▶ FastAPI ──async for──▶ Agent.arun(stream=True)
         ◀──SSE chunks────            ◀──RunEvent──
```

后端使用 Agno 的 `arun(stream=True)` 异步生成器，仅提取 `RunEvent.run_content` 事件的文本内容，过滤掉 Tool Call 等内部事件，确保前端只收到可展示的 Markdown 文本。

#### 3.2.2 会话存储与历史加载

Agno 内置的 `SqliteDb` 自动持久化 Agent 的每次对话到 `agno_sessions` 表。但其存储格式为**双重 JSON 编码**（JSON 字符串内嵌套 JSON），需要特殊解码：

```python
runs_str = json.loads(runs_raw)          # 第一层：字符串
runs = json.loads(runs_str)              # 第二层：实际数组
# 从 runs[i].input.input_content 提取用户消息
# 从 runs[i].content 提取助手回复
```

这使得前端可以：

- 侧边栏展示历史会话列表（预览文本 + 时间戳）
- 点击恢复完整对话上下文
- 支持删除会话

---

### 3.3 前端 Flex 布局的高度约束链

这是本次开发中遇到的最隐蔽的 CSS 问题。

#### 问题现象

聊天消息区域无限向下扩展，超出视口高度，滚动条不生效。

#### 根因分析

Flex 子元素的 `overflow-y: auto` 生效的前提是：**从根容器到该元素的每一层 flex 容器都必须有明确的高度约束**。

问题出在两处：

1. **根容器使用 `min-h-screen` 而非 `h-screen`**

   `min-height: 100vh` 表示最小高度为视口，但允许内容撑大。当消息增多时，整个页面高度被撑开，`overflow-hidden` 永远不会触发。

   修复：改为 `h-screen`（`height: 100vh`），创建固定高度容器。

2. **Vue `<component>` 标签的 class 合并问题**

   ```html
   <component :is="activeComponent" class="h-full min-h-0 flex flex-col" />
   ```

   Vue 3 会将 `<component>` 上的 class 合并到子组件根元素。LlmChat 的根元素本身是 `flex`（水平方向），合并后变成 `flex flex-col`（垂直方向），导致侧边栏和聊天区域纵向堆叠。

   修复：移除 `flex flex-col`，仅保留 `h-full min-h-0`。

#### 正确的高度约束链

```
html/body (默认)
└─ #app div          h-screen overflow-hidden        ← 固定视口高度
   └─ main           flex-1 flex flex-col overflow-hidden
      └─ 内容容器     flex-1 overflow-hidden flex flex-col min-h-0
         └─ 卡片容器   h-full flex flex-col min-h-0 overflow-hidden
            └─ LlmChat  flex flex-row h-full min-h-0  ← 水平布局
               ├─ 侧边栏  w-56 flex-shrink-0
               └─ 聊天区  flex-1 flex flex-col min-h-0
                  ├─ 顶部栏  flex-shrink-0
                  ├─ 消息区  flex-1 overflow-y-auto min-h-0  ← 滚动生效
                  └─ 输入框  flex-shrink-0
```

关键规则：

- 每层 flex 容器必须设置 `min-h-0`（覆盖默认的 `min-height: auto`）
- 需要滚动的元素使用 `flex-1 overflow-y-auto min-h-0`
- 不需要收缩的元素使用 `flex-shrink-0`

---

## 四、项目技术栈

| 层 | 技术 | 用途 |
|---|------|------|
| 前端 | Vue 3 + TypeScript | SPA 框架 |
| UI | Element Plus + TailwindCSS | UI 组件 + 原子化样式 |
| Markdown | markdown-it + highlight.js | 流式 Markdown 渲染 + 代码高亮 |
| 构建 | Vite (Rolldown) | 前端打包 |
| 后端 | FastAPI + Uvicorn | HTTP API + SSE |
| Agent | Agno (v2.4+) | 单 Agent 运行时 |
| 模型协议 | MCP (Streamable HTTP) | 外部工具集成 |
| 数据库 | MySQL (aiomysql) | 威胁情报数据源 |
| 会话存储 | SQLite (agno SqliteDb) | Agent 对话持久化 |
| 语言 | Python 3.12 / TypeScript 5.x | 后端/前端 |

---

## 五、目录结构说明

```
.
├── .skills/                          # Skill 能力层
│   ├── threat-trace-skill/           # 威胁情报检索与分析
│   │   ├── SKILL.md                  # SOP + 元数据
│   │   └── scripts/
│   │       ├── base.py               # 数据库连接池
│   │       ├── recall.py             # 关键词概要检索
│   │       ├── finegrain.py          # ID 详情获取
│   │       └── close_pool.py         # 连接池释放
│   ├── playbook-skill/               # SOAR 剧本执行
│   │   └── SKILL.md
│   └── intranet-ip-skill/            # 内网 IP 资产查询
│       ├── SKILL.md
│       └── agent.py                  # NDR 告警研判 Agent
├── api/                              # FastAPI 应用层
│   ├── services/
│   │   └── llm_service.py            # Agent 核心：模型配置、会话管理、流式对话
│   ├── routes/
│   │   ├── chat.py                   # 聊天 API（流式 + 会话 CRUD）
│   │   ├── settings.py               # 运行时配置 API
│   │   ├── cve.py                    # CVE 漏洞查询
│   │   └── asset.py                  # 资产管理
│   └── utils/
│       └── db.py                     # 公共数据库工具
├── frontend/src/                     # Vue 3 前端
│   ├── components/
│   │   ├── LlmChat.vue              # 聊天界面（会话侧边栏 + 流式 Markdown）
│   │   ├── Settings.vue              # 系统配置界面
│   │   ├── CveSearch.vue             # CVE 检索
│   │   └── AssetSearch.vue           # 资产检索
│   ├── composables/
│   │   └── useApi.ts                 # API 封装（SSE 流式消费）
│   └── App.vue                       # 主布局（Flex 高度约束链）
└── security_agent.db                 # Agent 会话持久化数据库
```

---

## 六、后续规划

1. **Skill 扩展**：增加漏洞验证 Skill（集成 Nuclei/XRAY 扫描器）
2. **多模型支持**：通过 Settings 页面动态切换不同 LLM 供应商
3. **权限管理**：基于角色的会话隔离与操作审计
4. **知识库增强**：接入 RAG 管道，支持企业内部安全文档检索
5. **流式工具调用展示**：前端展示 Agent 调用工具的中间过程（Tool Call Events）

---

## 七、总结

AgentOS 的核心设计哲学是 **"能力下沉、编排上移"**：

- **能力下沉**：将数据访问、API 调用等具体能力封装为 Skill 脚本和 MCP 工具，保持接口清晰、职责单一
- **编排上移**：将任务规划和工具调用的决策权交给大语言模型，通过精心设计的 Prompt（AGENT_INSTRUCTIONS）和 SOP（SKILL.md）引导模型行为

这种架构的最大优势是**可扩展性**：新增安全能力不需要修改 Agent 代码或编排逻辑，只需提供 Skill 描述和数据接口。在安全运营这种需求快速变化的场景中，这种"声明式能力注册"的模式显著降低了迭代成本。
