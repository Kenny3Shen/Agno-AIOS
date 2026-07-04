# Agno AIOS

Agno AIOS 是面向安全运营的控制面，把 Agent 对话、可观测性、工具编排、本地技能、知识检索、安全数据和访问控制组合在一个操作员工作台中。

## 语言

### 产品

**控制面**:
操作员访问 Chat、Trace、Skills、MCP 配置、Knowledge、安全数据和治理视图的工作台。
_避免_: 门户、控制台

**安全运营助手**:
面向 Agent 的助手；在完整运行时可用时，它可以使用已启用的知识库、Skills 和 MCP 工具回答安全运营问题。
_避免_: 聊天机器人、通用助手

**AgentOS 控制视图**:
围绕 Agent、Team、Workflow、Memory、Metrics、Evaluation、Approvals 和 Scheduler 数据构建的控制面视图。
_避免_: AgentOS 后端

### 界面语言

**Stat Strip**:
页面标题与主要工作区之间的一组紧凑摘要，用于让操作员快速判断当前模块的规模、健康度或关键配置状态。它只承载数量、状态和关键配置摘要，不承载操作按钮、长说明、表单状态或搜索结果数量。
_避免_: 统计方框区、KPI Dashboard、Toolbar

**Stat Chip**:
Stat Strip 中的单项摘要，通常由标签和值组成，可带状态语义，但不承载主要操作或复杂解释。它使用紧凑的 8px 小方块形态，不使用 pill 圆角。
_避免_: Card、Badge、Metric Card、Pill

### Agent Runtime

**Chat Session**:
归属于用户的一段连续对话历史，可在同一线程下包含多次 agent run。
_避免_: 把 Conversation 当作安全边界

**Run**:
Session 中一次 agent、team 或 workflow 执行。
_避免_: Trace

**Trace**:
一次完整 agent、team 或 workflow 执行对应的可观测性记录。
_避免_: Session log

**Span**:
Trace 内部的单个操作，例如 agent step、模型调用、工具调用或检索。
_避免_: Event

**Workflow**:
由 Agno 运行的可重复编排管线，通过明确步骤把 Agent、Team、函数或嵌套 Workflow 串联、分支、循环或并行执行。
_避免_: 通用自动化、触发器链

**Workflow Step**:
Workflow 内的执行或控制单元，可委派给 executor，也可表达顺序组合、条件、路由、循环或并行分支。
_避免_: Node、任务卡片

**Executor**:
Workflow Step 使用的可运行组件，包括 Agent、Team、自定义函数或嵌套 Workflow。
_避免_: Skill、动作处理器

**Workflow Session**:
Workflow 的持久化执行历史，记录完整 run、步骤结果、session data 和共享 session state。
_避免_: Chat Session、Workflow summary

**Memory**:
与用户或 agent 上下文关联的持久化 agent 记忆。
_避免_: Knowledge

### 工具与知识

**Skill**:
可启用或禁用，并可加载到助手运行时中的本地能力包。
_避免_: Plugin

**MCP Service**:
通过集成 MCP endpoint 暴露的已挂载工具服务。
_避免_: 外部 API

**MCP Token**:
用于授权访问 MCP endpoint 的 bearer-style token。
_避免_: 用户会话 token

**Hi-Agent**:
注册到系统中的外部 MCP-compatible endpoint，供 playbook 工具发现和调用远程工具。
_避免_: 内置 MCP service

**Knowledge Document**:
加入知识库、带用户范围的来源条目。
_避免_: File、chunk

**Knowledge Base**:
可被助手通过检索使用的内部文档集合。
_避免_: Memory

### 安全数据

**CVE Intelligence**:
控制面中可检索的漏洞记录和 exploit 引用。
_避免_: 把 CVE database 当作授权来源

**Asset Query**:
按 IP 或 fingerprint 查询已配置资产数据源的动作。
_避免_: Inventory owner

**URL Collection**:
抓取 URL 并把内容转换为 Markdown 供操作员使用的过程。
_避免_: Knowledge ingestion

### 访问与审计

**Actor**:
正在执行动作的已认证用户。
_避免_: Account

**Role**:
分配给 actor 的粗粒度访问类别：admin、user 或 guest。
_避免_: Permission

**Permission**:
后端 route 执行动作前检查的细粒度能力字符串。
_避免_: Role

**Resource Ownership**:
非 admin actor 只能访问归属于自己用户身份的用户资源这一规则。
_避免_: Session ID secrecy

**Audit Log**:
安全相关用户动作的追加式记录，例如登录、登出、配置变更、知识库变更、MCP 变更、Skill 变更和管理员操作。
_避免_: Application log

**Bootstrap Admin**:
API 启动时在显式配置 bootstrap credentials 后创建或提升的初始 admin 身份。
_避免_: Default admin
