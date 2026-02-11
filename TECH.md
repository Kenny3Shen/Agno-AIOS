# 安全运营中台技术预研报告

## 1. W5-SOAR 预研
调研 W5-SOAR 是否符合工作流编排需求

### 技术架构
W5-SOAR 的核心逻辑位于 `core/` 目录下，采用插件化与事件驱动的设计思想。

- `core/auto/`：自动化编排内核。负责工作流节点的拓扑排序执行、状态管理及异步调度。其内部使用 `apscheduler` 处理定时与周期性任务。
- `core/model/`：基于 `SQLAlchemy` 的数据模型层。定义了 Workflow (剧本), Timer (定时器), Variablen (变量) 等核心实体。
- `core/utils/`：底层工具链。包含文件处理、时间格式化、随机数生成等基础功能。
- `core/view/`：Web 控制台的 API 逻辑，处理前端页面的交互请求。
### 执行流程
当一个工作流被触发（Webhook）时，内核会：

1. 从数据库读取流程图 JSON。
2. 将节点解析为待执行序列。
3. 动态加载对应的 apps/ 模块代码。
4. 为节点注入上下文变量（Context Variables）。
高代码定制
W5 支持通过“应用”形式扩展节点能力。
  每个应用位于 apps/ 目录下，包含：

- app.json（required）：定义节点名称、图标、所属类别、入参规格 (args)。
{
  "name": "CVE-POC",
  "action": [{"name": "获取 POC", "func": "get_poc"}],
  "args": {"get_poc": [{"key": "data", "type": "text"}]}
}
- main/run.py(required)：业务逻辑实现。（注：通过Agent调用Webhook传递参数 json 时，json 有可能存在二次编码，最好判断json.loads(data)后的类型）
async def get_poc(data: str):
    data = json.loads(data)
    if isinstance(data, str):
        data = json.loads(data)

    # 逻辑实现

    return {"status": 0, "result": "执行成功后的数据"}
- readme.md (required)：参考文档
- icon.png (optional): 图标
前端展示
主要展示如何通过Webhook调用工作流并传递参数，以及后续节点如何解析参数
[图片]

1. 先查看Webhook ID：84488800-fa7c-11f0-8c8c-93c8eb47efc2

[图片]
2. 查看我们需要什么参数，右键点击CVE-POC节点
[图片]
[图片]
3. 那么Webhook需要传递的参数就是{"query":"xxx", "size":1-50}
import httpx
import os

headers = {"Content-Type": "application/json"}

data = {
    "key": os.getenv("W5_SOAR_TOKEN"),  # w5 token
    "uuid": "84488800-fa7c-11f0-8c8c-93c8eb47efc2",  # webhook id
    "data": {"query": "n8n"},  # 传参
}

resp = httpx.post(
    "<http://localhost:8888/api/v1/w5/webhook>",  # api
    headers=headers,
    json=data,
    verify=False,
)
print(resp.json())
{'code': 0, 'data': {'only_id': '202602101902374067293185'}, 'msg': 'Success'}
[图片]
接口适配
由于原生W5-SOAR缺少部分API，需要进行二次开发补充API，最终得到下面的API

- api_get_workflow_list（获取可用工作流）
- api_get_webhook_param（获取工作流参数）
- api_webhook（调用工作流）
- api_get_webhook_result（查询结果）
基于上面的API，可以开发一套 MCP Tools 供 Agent 调用工作流 （见2.2）
小结
通过少量的 API 二次开发，W5-SOAR 可以具备成熟的 MCP 服务化能力 与 插件化扩展能力。通过 MCP 层的适配，不仅保留了传统 SOAR 的编排优势，还赋予了其与大语言模型 (LLM) 生态直接交互的能力。

2. MCP Server 预研
MCP Server 技术选型
后端架构

- FastMCP (v3.0.0b1): 作为核心 MCP 框架，用于定义 tools 和 resources，支持异步操作和多实例挂载。
- Starlette: 高性能 ASGI 框架，用于构建管理 API 和静态文件服务。
前端开发
- Vue 3 (Composition API): 响应式前端框架。
MCP Server 实现
聚合mcp服务并实现统一管理
  - main_mcp 作为主服务，控制鉴权和HTTP服务能力的提供
  - 在启动阶段解析配置文件，通过 main_mcp.mount() 动态构建功能子集，实现管理不同 MCP 服务的启用。
  - 当用户在管理后台切换子MCP服务状态后，系统会自动销毁旧的 FastMCP 实例并重新实例化新的应用。
[图片]
剧本执行模块（SOAR 剧本）
    工作流平台适配 (W5 & Octomation): 为了屏蔽底层 API 差异，定义了统一的 Adapter 类。MCP 层只需调用标准的 MCP 服务。这样只需在剧本平台新建剧本即可自动发现新增剧本，无需修改MCP服务端。目前将剧本平台的 API 抽象为 4 大基本 MCP 能力：
    - `list_workflows(platform)` 获取候选剧本（redis）-> 剧本摘要和ID
    - `get_method_params(method_id)` 获取参数定义 (redis)
    - `invoke_method(method_id, params)` 发起执行
    - `get_exec_result(exec_id)` 获取结果
@playbook_mcp.tool()
async def list_workflows(platform: str) -> dict:
    """获取剧本列表"""

@playbook_mcp.tool()
async def get_method_params(platform: str, method_id: str) -> dict:
    """获取剧本所需参数"""

@playbook_mcp.tool()
async def invoke_method(
    platform: str, method_id: str, params: dict | None = None
) -> dict:
    """调用剧本方法"""

@playbook_mcp.tool()
async def get_exec_result(platform: str, exec_id: str) -> dict:
    """查询剧本执行结果"""
AI Agent 模块
    负责添加 Hi-Agent 提供的 MCP 服务和一些复杂的Agent的API接口。
hiagent_mcp = create_proxy(
    "<https://hiagent.x-peng.com/api/proxy/mcp?api_key=your-api-key>"
)
agent_mcp.mount(hiagent_mcp)
基础工具模块
    负责提供一些常用 Tools，如：飞书通知、发送邮件等
@basic_mcp.tool()
async def send_feishu_notify(
    feishu_webhook_url: str,
    title: str,
    content_md: str,
    template: str = "blue",
) -> dict:
    """发送飞书机器人通知
    Args:
        feishu_webhook_url: 飞书机器人 Webhook URL
        title: 标题
        content_md: 内容
    Returns:
        dict: 发送结果
    """
    # 实现逻辑
3. 中台Agent预研
暂时无法在飞书文档外展示此内容
核心设计理念：让模型自主编排，我们只负责业务定义和能力支持
维度
Agno
LangChain/LangGraph
CrewAI
编排方式
模型自主编排（指令驱动）
需定义状态图/链
预设角色+流程
复杂度
低，仅需写 Skill + Prompt
也可以手动实现工作流
高，需理解 DAG/State Machine
中，需定义 Task/Crew
MCP 支持
原生内置 MCPTools
需额外适配
不支持
Skill 热加载
LocalSkills 文件夹即加载
不支持
不支持
会话持久化
内置 SqliteDb等数据库集成
需手动集成
需手动集成
依赖量
轻量 (~50 deps)
重量 (200+ deps)
中量
模型本身就是任务编排引擎
  传统 Agent 框架（如 LangGraph）要求开发者定义精确的执行图、状态转移和条件分支。这在安全运营场景中存在明显弊端：

  1. 场景高度动态：静态 DAG 无法覆盖新增业务。
  2. 维护成本高：每新增一个能力，都需要修改编排逻辑、增加节点与边。
解决方案
  只提供能力（Skills + MCP Tools），由基座大模型根据用户意图自行决定调用顺序和参数组合。开发者的工作简化为：

- 编写 SKILL.md 描述能力边界和 SOP，规范工作流或提供解决思路
- 编写 Scripts 脚本 提供专家能力和数据访问，隔离敏感操作
- 通过 MCP Server 使用预设剧本和基础工具
轻量接入
- 基础工具由 MCPTools 提供
- 专家能力由 .skills/ 文件夹提供
- 支持会话管理
- 支持上下文管理、记忆模块、上下文压缩等常用技巧
async with MCPTools(
    transport="streamable-http",
    url=f"{MCP_SERVER_URL}?token={MCP_TOKEN}",
    timeout_seconds=20,
) as mcp_tools:
    security_agent = Agent(
        name="安全运营助手",
        instructions=[AGENT_INSTRUCTIONS],
        model=_build_model(),
        tools=[mcp_tools],                          # MCP 工具
        skills=Skills(loaders=[LocalSkills(".skills")]),  # 本地技能
        db=SqliteDb("security_agent.db"),            # 会话持久化
        add_history_to_context=True, # 添加上下文
        num_history_runs=5,        # 上下文窗口设置
        update_memory_on_run=True, # 自动记忆管理
        #compress_tool_results=True, # 上下文压缩
        #learning=True              # 启用学习
      )

### 核心挑战与工程化实践

在将人类专家的安全经验抽象为 AI Agent 生产力的过程中，项目在底层架构设计上解决了四个维度的核心挑战：

- **安全业务定义（原子化与语义对齐）**
  - **挑战**：传统安全分析 SOP 通常以非结构化文档或碎片化经验形式存在，描述模糊（如“检查异常流量”），LLM 难以直接执行。
  - **解决**：在 `SKILL.md` 中构建**结构化指令指南**。通过明确的阶段划分（如：特征提取 -> 响应关联 -> 环境研判 -> 响应决策），将模糊业务转化为 LLM 可理解的**逻辑状态机**。这使得 SOP 既是供人阅读的文档，也是 Agent 执行过程中的“策略底座”。

- **数据安全访问（隔离与凭据管理）**
  - **挑战**：Agent 作为一个高频自动化的实体，如果直接持有高权限 API Token 并在上下文中流转，存在凭据泄露或权限溢出的风险。
  - **解决**：设计了**脚本代理机制（Script Proxy）**。Agent 不直接触达底层数据库或私有平台，而是通过调用受限的 Python 脚本进行“中间人查询”。敏感凭据（如私有 API Key）仅保留在本地环境变量中，脚本仅向 Agent 返回非敏感的 JSON 数据。这种“**存算分离**”的设计确保了 Agent 始终在预设的安全边界内运行。

- **数据有效获取（噪声过滤与分级检索）**
  - **挑战**：安全日志原文包含大量无关元数据，直接透传会导致严重的 Token 浪费和注意力分散。
  - **解决**：实施**数据语义压缩**策略。在脚本代理层执行业务级清洗，过滤针对性字段，仅保留核心 Payload 和上下文关联条目。同时，采用“**概览检索 -> 按需深挖**”的分级检索模式，在信息完整性与计算资源消耗之间取得了最优平衡。

- **数据有效分析（证据闭环与结果验证）**
  - **挑战**：LLM 的推理过程如果不加约束，容易产生“结论先行”的幻觉，缺乏可审计的证据链。
  - **解决**：在 SOP 中强制要求**证据闭环（Evidence-Based Reasoning）**。Agent 被要求在输出格式中包含 `evidence` 字段，显式引用源数据中的关键证据（如特定的 HTTP 头、攻击 Payload 偏移或原文链接）。通过将“研判结论”与“支撑依据”强解耦，确保了分析结果的可验证性，为后续自动化响应提供了高置信度的数据支撑。

SKILL实现
threat-trace-skill：威胁情报态势分析
 从用户查询中识别关键特征词（如组织名、CVE编号或组件、恶意代码家族等），通过scripts查询数据库资料
问题
解决方案
数据安全访问：查询参数注入风险
封装为独立 Python 脚本（recall.py、finegrain.py），Agent 通过scripts 使用脚本使用参数化 SQL（%s 占位符），禁止字符串拼接，禁止直接输入SQL语句
数据有效获取：结果集过大影响 Token
两阶段检索：recall 返回轻量摘要 → finegrain 按需获取详情 → 总结

数据有效分析
SOP 规范约束，强制要求为引用的情报附上数据来源
两阶段检索模式：
用户查询 "Everest 勒索组织的威胁情报"
    │
    ▼
recall.py --keywords "Everest" --days 90
    │ 返回 [{id: 42343, title: "..."}, {id: 42189, title: "..."}, ...]
    ▼
Agent 根据 title 筛选相关 ID
    │
    ▼
finegrain.py --ids "42343,42189,42085,42002"
    │ 返回完整 description、url、public_time
    ▼
Agent 分析情报报告
中台Agent使用threat-trace-skill能力
[图片]
[图片]
[图片]
playbook-skill：MCP Tools 调用规范
规定剧本的调用逻辑
---

name: playbook-skill
description: 使用安全自动化剧本完成处置、排查与验证任务
---

# 基本能力

  1. `playbook_list_workflows(platform)` 获取候选剧本 (w5-soar / octomation)
  2. `playbook_get_method_params(method_id)` 获取参数定义
  3. `playbook_invoke_method(method_id, params)` 发起执行
  4. `playbook_get_exec_result(exec_id)` 获取结果
  
## 任务解析

- 能从用户描述中抽取意图、目标对象、条件与期望输出
- 能判断是否需要剧本支持（不是所有任务都要执行）
- 信息不足时先提1-3个关键澄清问题再执行

## 剧本选择

- 先调用 `list_workflows(platform: str)` 获取候选剧本
- 根据名称或描述匹配最合适的剧本
- 无匹配时向用户说明，并请求补充或改用其他平台

## 参数理解与校验

- 必须调用 `get_method_params(method_id: str)` 获取参数定义
- 对必填参数进行校验，不完整则向用户提问
- 提供默认值的参数可自行填写并说明

## 执行与结果处理

- 通过 `invoke_method(method_id: str, params: dict | None = None)` 发起执行
- 使用 `get_exec_result(exec_id: str)` 获取结果
- 结果需要结构化摘要给用户（成功/失败 + 关键输出 + 下一步建议）

## 异常处理

- 平台未实现或不可用：明确提示 + 备选方案
- 参数不足：明确列出缺失项
- 执行失败：提供日志或错误信息并建议下一步

## 注意事项

你通常需要返回 `任务ID` 以便用户后续查询执行结果。
[图片]
darknet-trace-skill：暗网威胁态势分析
分析国内暗网泄露信息标题，总结数据安全态势
[图片]
[图片]
[图片]
intranet-ip-skill：内网IP风险分析（未完整可用）
资产信息、NDR告警信息等，判断是否需要受到 0 day 威胁，NDR 木马告警进行杀毒
4. 总结
核心设计哲学是 "能力下沉、编排上移"：

- 能力下沉：将数据访问、API 调用等具体能力封装为 Skill 脚本和 MCP 工具，保持接口清晰、职责单一
- 编排上移：将任务规划和工具调用的决策权交给大语言模型，通过精心设计的 Prompt（AGENT_INSTRUCTIONS）和 SOP（SKILL.md）引导模型行为
这种架构的最大优势是可扩展性：新增安全能力不需要修改 Agent 代码或编排逻辑，只需提供 Skill 描述和数据接口。在安全运营这种需求快速变化的场景中，这种"声明式能力注册"的模式显著降低了迭代成本。
附录
踩坑记录

1. 根据 MCP 协议规定，MCP 提供的 Tool name 不允许包含空格。FastMCP 遵循了该协议约束，但Hi-agent提供的 MCP 服务未遵循。
  如下为在 Hi-agent 中注册的一个 Agent（CVE Hunter），使用 Hi-agent 提供的 MCP 链接时出现如下报错（VS Code 调试日志信息）
Tool name validation warning for "CVE Hunter":

- Tool name contains spaces, which may cause parsing issues
- Tool name contains invalid characters: ' '
- Allowed characters are: A-Z, a-z, 0-9, underscore (_), dash (-), and dot (.)
Tool registration will proceed, but this may cause compatibility issues.
Consider updating the tool name to conform to the MCP tool naming standard.
See SEP-986 (<https://modelcontextprotocol.io/specification/2025-11-25/server/tools#tool-names>) for more details.
Session termination failed: 500
  将 Hi-agent 提供的 MCP 链接挂载在本地 FastMCP 服务时
agent_mcp = FastMCP("Agent")
hiagent_mcp = create_proxy(
    "<https://hiagent.x-peng.com/api/proxy/mcp?api_key=xxx>"
)
agent_mcp.mount(hiagent_mcp)
  本地的 FastMCP 服务无法解析该 Tool name，导致链接MCP Server 超时。（该问题在运行时出现）
ERROR    Failed to get tools for <MCPTools name=MCPTools functions=[]>: Timed out while waiting for response to
         ClientRequest. Waited 20.0 seconds.

2. FastMCP 默认在根路径 / 处理握手。直接使用 Starlette 的 Mount 挂载管理后台会导致路由冲突（404/405 错误）。
  在实现了一个底层的 root_app 调度函数。它会检查请求路径：

- 如果路径是 /mcp，则透传给 FastMCP 的 http_app 处理。
- 如果是其他路径，则交给 Starlette 路由处理。

3. Hi-Agent 提供 API 方式接入Agent，需要预先知道变量名，适配难度大，且需要对每个剧本单独适配。工作流类型Agent和对话型Agent的API形式不一样。AI应用平台使用指南V1.0
