from IPython.utils.text import dedent
import os
from typing import Any, AsyncIterator, cast
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools
from agno.skills import Skills, LocalSkills
from agno.run.agent import RunEvent

load_dotenv(override=True)
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8889/mcp")
MCP_TOKEN = os.getenv("W5_SOAR_TOKEN", "dev-token")


def _build_model() -> OpenAILike:
    return OpenAILike(
        id=os.getenv("LLM_EP", "gpt-3.5-turbo"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_URL"),
        extra_body={"thinking": {"type": "disabled"}},
    )


playbook_agent_mcp = MCPTools(
    transport="streamable-http",
    url=f"{MCP_SERVER_URL}?token={MCP_TOKEN}",
    include_tools=[
        "playbook_list_workflows",
        "playbook_get_method_params",
        "playbook_invoke_method",
        "playbook_get_exec_result",
    ],
)

playbook_agent = Agent(
    name="剧本执行Agent",
    instructions=[
        "你是剧本执行Agent，专注执行已编排的步骤.",
        "你目前可以调用 w5-soar / octomation 平台的安全自动化剧本。",
        "优先使用技能库与 MCP 工具完成任务，并给出可验证的结果。",
        "当用户需要调用具体工具或技能时，准确执行并反馈结果，如：",
        "查询剧本能力->调用list_workflows；查询剧本调用结果->调用get_exec_result；",
        "输出结构化：结论 + 证据/输出字段 + 下一步建议。",
    ],
    model=_build_model(),
    tools=[playbook_agent_mcp],
    skills=Skills(
        loaders=[LocalSkills(path=".skills/playbook-skill")],
    ),
    db=SqliteDb("playbook_agent.db"),
    add_history_to_context=True,
    markdown=True,
)

threat_trace_mcp = MCPTools(
    transport="streamable-http",
    url=f"{MCP_SERVER_URL}?token={MCP_TOKEN}",
    include_tools=[
        "basic_get_threat_info",
        "basic_send_feishu_notify",
    ],
)

threat_trace_agent = Agent(
    name="威胁追踪Agent",
    instructions=[
        dedent("""\
            你是一名专业的威胁情报分析专家（Threat Intelligence Analyst）。你的任务是利用现有的工具检索、分析并汇报网络威胁情报。

            ### 角色定位
            你是安全运营中心 (SOC) 的情报分析核心，专注于处理来自数据库 dynamic_monitor 的原始情报，提取攻击指示器 (IOCs)、攻击者动机及战术手段 (TTPs)。

            ### 数据资产
            你拥有访问以下情报字段的权限：
            - `id`: 唯一标识符
            - `title`: 威胁事件简述
            - `description`: 完整情报描述（含技术细节）
            - `url`: 情报来源追溯链接
            - `public_time`: 发布时间（格式：YYYY-MM-DD）

            ### 标准作业程序 (SOP)
            1. **意图解析**：从用户查询中识别关键特征词（如组织名、CVE编号、恶意代码家族等）。
            2. **多级检索**：
               - **候选发现**：通过 `basic_get_threat_info` 检索概要信息。如：SELECT id, title FROM dynamic_monitor WHERE title LIKE '%关键词%' OR description LIKE '%关键词%' ORDER BY public_time DESC LIMIT 10;
               - **查询逻辑**：匹配 `title` 或 `description` 中的关键词，按 `public_time` 降序排列，通常取前 10 条。
            3. **精准评估**：从候选列表中剔除不相关或高度重复的信息，确保结果的独特性。
            4. **详细溯源**：针对筛选出的关键 `id` 调用工具获取 `url` 和 `description` 等核心详情。如: SELECT description, url, public_time FROM dynamic_monitor WHERE id IN (id1, id2, ...);
            5. **情报合成**：将散乱的信息整合为逻辑严密的分析报告。

            ### 报告输出要求
            - **[情报总结]**：一句话概括当前的威胁态势。
            - **[深度研判]**：以列表或表格形式展示关键事件，提取 TTPs 或影响范围。
            - **[来源参考]**：清晰列出关联的 `url` 和发布日期。
            
            ### 行为准则
            - **依数行事**：仅使用数据库提供的事实，严禁虚构情报（No hallucinations）。
            - **反馈建议**：若无匹配结果，说明分析点并给出调整搜索意图的建议（如“尝试更具体的攻击组织代号”）。
            - **专业客观**：保持情报分析的严谨性，不带主观偏见。\
        """)
    ],
    model=_build_model(),
    # db=SqliteDb("threat_trace_agent.db"),
    tools=[threat_trace_mcp],
    # add_history_to_context=True,
    # markdown=True,
)


async def stream_chat_with_agent(message: str) -> AsyncIterator[str]:
    """流式聊天，返回增量内容"""
    async for event in security_agent.arun(message, stream=True):
        event_type: str | None = None
        content: Any = None
        if isinstance(event, dict):
            event_dict = cast(dict[str, Any], event)
            event_type = event_dict.get("event")
            content = event_dict.get("content")
        else:
            event_type = getattr(event, "event", None)
            content = getattr(event, "content", None)

        if (
            event_type == RunEvent.run_content.value
            and isinstance(content, str)
            and content
        ):
            yield content
