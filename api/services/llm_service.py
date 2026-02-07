import os
from typing import Any, AsyncIterator, cast
from dotenv import load_dotenv
from textwrap import dedent
from agno.agent import Agent
from agno.team import Team
from agno.models.openai import OpenAILike
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools
from agno.run.agent import RunEvent
from agno.skills import Skills, LocalSkills

load_dotenv(override=True)
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8889/mcp")
MCP_TOKEN = os.getenv("W5_SOAR_TOKEN", "dev-token")
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "30"))


dependencies = {
    "feishu_webhook_url": os.getenv("FEISHU_WEBHOOK_URL", ""),
}


def _build_model() -> OpenAILike:
    return OpenAILike(
        id=os.getenv("LLM_EP", "gpt-3.5-turbo"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_URL"),
        # extra_body={"thinking": {"type": "disabled"}},
        # extra_body={"enable_thinking": False},
    )


async def _connect_mcp_tools() -> MCPTools:
    mcp_tools = MCPTools(
        transport="streamable-http",
        url=f"{MCP_SERVER_URL}?token={MCP_TOKEN}",
        timeout_seconds=20,
    )
    await mcp_tools.connect()

    return mcp_tools


async def stream_chat_with_agent(message: str) -> AsyncIterator[str]:
    """流式聊天，使用 Team 协调多个 Agent"""
    shared_mcp = await _connect_mcp_tools()
    try:
        # 威胁情报分析 Agent
        threat_trace_agent = Agent(
            name="威胁情报分析师",
            role="威胁情报检索与分析专家",
            instructions=[
                dedent("""\
                你是一名专业的威胁情报分析专家（Threat Intelligence Analyst）。

                ### 核心任务
                使用 `threat-trace-skill` 检索、分析并汇报网络威胁情报。
                
                ### 工作流程
                1. 优先调用 `get_skill_instructions` 获取技能的完整 SOP。
                2. 严格执行“意图解析 -> 多级检索 -> 精准评估 -> 详细溯源 -> 情报合成”的步骤。
                3. 使用 `get_skill_script` 执行对应的 Python 脚本来获取数据：
                   - 概要检索：`scripts/recall.py --keywords "关键词"`
                   - 详情获取：`scripts/finegrain.py --ids "ID列表"`
                4. 分析完成后，必须向协作团队提供结构化的分析报告。
                
                ### 通知要求
                - 如果用户明确要求“发送通知”或“上报”，请使用 `basic_send_feishu_notify` 工具。
                - 汇报内容应包含分析出的 TTPs、威胁等级和来源链接。
                - 请在成功发送通知后，向团队反馈执行状态结果概况。
                """),
            ],
            model=_build_model(),
            tools=[],
            skills=Skills(
                loaders=[
                    LocalSkills(
                        ".skills/threat-trace-skill",
                    )
                ]
            ),
            markdown=True,
        )

        # 安全剧本执行 Agent
        playbook_agent = Agent(
            name="剧本执行专家",
            role="安全自动化剧本执行与编排专家",
            instructions=[
                dedent("""\
                你是安全剧本执行专家，专注于执行和管理安全自动化剧本。
                你可以调用 w5-soar (w5) / octomation (oct) / hi-agent 平台的安全自动化剧本。

                ### 任务解析
                - 能从用户描述中抽取意图、目标对象、条件与期望输出
                - 能判断是否需要剧本支持（不是所有任务都要执行）
                - 信息不足时先提1-3个关键澄清问题再执行

                ### 剧本选择
                - 先调用 playbook_list_workflows(platform) 获取候选剧本
                - 根据名称或描述匹配最合适的剧本
                - 无匹配时向用户说明，并请求补充或改用其他平台

                ### 参数理解与校验
                - 调用 playbook_get_method_params(method_id) 获取参数定义
                - 对必填参数进行校验，不完整则向用户提问
                - 提供默认值的参数可自行填写并说明

                ### 执行与结果处理
                - 通过 playbook_invoke_method(method_id, params) 发起执行
                - 使用 playbook_get_exec_result(exec_id) 获取结果
                - 结果需要结构化摘要给用户（成功/失败 + 关键输出 + 下一步建议）

                ### 异常处理
                - 平台未实现或不可用：明确提示 + 备选方案
                - 参数不足：明确列出缺失项
                - 执行失败：提供日志或错误信息并建议下一步


                ### 注意事项
                通常需要返回任务 ID 以便用户后续查询执行结果。
                对于 hi-agent 平台，其余 playbook_ 前缀的方法均可直接调用。
                """)
            ],
            model=_build_model(),
            tools=[shared_mcp],
            markdown=True,
        )

        # 创建安全运营 Team
        security_team = Team(
            name="安全运营团队",
            role="安全运营团队协调者",
            description="由各种安全专家组成的安全运营团队，协同完成威胁分析和响应处置任务。",
            instructions=[
                dedent("""
                你是安全运营团队的协调者。

                ### 协作逻辑
                - **威胁分析流程**：当用户或其他专家需要获取某些威胁情报报告时，指派“威胁情报分析师”进行检索和深度分析。
                - **剧本调用流程**：当用户或其他专家需要执行安全自动化剧本时，指派“剧本执行专家”负责剧本的选择、参数准备和执行。
                - **闭环要求**：确保所有分析内容都有明确的回应，若需要飞书通知，必须确认通知工具已被调用。

                ### 汇报格式
                最后汇总给用户的内容应包含：情报概要、专家研判结论以及已执行的操作（如：已发送飞书通知）。
                """),
            ],
            members=[threat_trace_agent, playbook_agent],
            model=_build_model(),
            tools=[],
            db=SqliteDb("security_team.db"),
            dependencies=dependencies,
            add_dependencies_to_context=True,
            add_history_to_context=True,
            num_history_runs=5,
            markdown=True,
        )

        # 使用 Team 执行任务
        async for event in security_team.arun(message, stream=True):
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
    finally:
        await shared_mcp.close()
