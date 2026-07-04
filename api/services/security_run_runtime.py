import os
from textwrap import dedent
from typing import Any, AsyncIterator, cast
from urllib.parse import urlencode

from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.run.agent import RunEvent
from agno.skills import LocalSkills, Skills
from agno.tools.mcp import MCPTools
from loguru import logger

from api.services.knowledge_service import get_knowledge_base
from api.services.model_config_service import get_model_for_run
from api.services.postgres_store import get_agno_postgres_db
from api.services.skill_service import get_enabled_skill_dirs


def _get_env(key: str, default: str = "") -> str:
    """优先从 os.environ 读取（支持运行时动态修改），回退到默认值"""
    return os.environ.get(key, default)


def _build_model(model_id: str | None = None) -> OpenAILike:
    model = get_model_for_run(model_id)
    return OpenAILike(
        id=model["model_id"],
        api_key=model["api_key"],
        base_url=model["base_url"],
    )


def _get_mcp_token() -> str:
    return (_get_env("MCP_TOKEN") or _get_env("MCP_Token")).strip()


def _build_mcp_url() -> str:
    base_url = _get_env("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp/").strip()
    token = _get_mcp_token()
    if not base_url:
        raise RuntimeError("MCP_SERVER_URL 未配置，请在 .env 或系统配置中设置 MCP 服务地址。")
    if not token:
        raise RuntimeError("MCP_TOKEN 未配置，请在 .env 或系统配置中设置 MCP 访问 Token。")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': token})}"


AGENT_INSTRUCTIONS = dedent("""\
    你是安全运营助手，具备 **威胁情报分析** 和 **安全剧本执行** 两大核心能力。
    ---
    ## 一、威胁情报分析

    使用 `threat-trace-skill` 技能检索、分析并汇报网络威胁情报。
    使用 `darknet-trace-skill` 技能获取暗网相关情报线索。

    ---
    ## 二、安全剧本执行

    使用 `playbook-skill` 技能和 MCP 工具调用安全自动化剧本（w5-soar / octomation / hi-agent）。

    ---
    ## 三、通知与上报

    若用户要求"发送通知"或"上报"，使用 `basic_send_feishu_notify` 工具。

    ---
    ## 四、内部知识库

    当用户询问制度、处置规范、历史报告、资产说明、漏洞研判资料或要求基于已沉淀资料回答时，主动调用 `search_knowledge_base` 检索内部知识库。
    复杂问题应拆成 2-3 个检索 query 多次检索，综合 PgVector 向量召回和 rerank 后的结果回答。
    使用知识库命中内容时，需要在回答中标明来源标题或 source；不要把未命中的内容伪装成内部知识。
    若知识库没有命中，必须明确说明"未检索到内部知识库依据"，再使用其他工具或通用推理补充。
    
    ---
    ## 五、行为准则

    - **依数行事**：仅使用工具和脚本提供的数据事实，严禁虚构信息。
    - **信息不足时**：先提 1-3 个关键澄清问题，再执行。
    - **专业客观**：保持情报分析的严谨性和客观性，避免主观臆断。
    - **闭环响应**：确保每个任务都有明确的结论或下一步建议。
""")

SAFE_FALLBACK_INSTRUCTIONS = dedent("""\
    你是安全防御运营助手。当前模型服务拦截了完整 Agent 上下文，因此你正在无工具模式下回答。

    工作边界：
    - 只处理授权环境中的防御、安全运营、排查、治理、总结和规划任务。
    - 不编造工具结果、内部数据、知识库命中或执行状态。
    - 如果问题需要 MCP、Skills、知识库或历史上下文，明确说明当前降级模式无法调用这些能力，并给出可执行的人工排查步骤。
    - 回答保持简洁、结构化、可操作。
""")

PROVIDER_BLOCK_MARKERS = (
    "your request was blocked",
    "request was blocked",
    "blocked by",
    "content was blocked",
)


dependencies = {
    "feishu_webhook_url": _get_env("FEISHU_WEBHOOK_URL"),
}


def _build_enabled_skills() -> Skills | None:
    """根据配置构建仅启用的 Skills 加载器；全部禁用时返回 None"""
    enabled_dirs = [str(skill_dir) for skill_dir in get_enabled_skill_dirs()]
    if not enabled_dirs:
        return None
    return Skills(loaders=[LocalSkills(d) for d in enabled_dirs])


def _is_provider_block_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in PROVIDER_BLOCK_MARKERS)


async def _stream_agent_content(
    agent: Any,
    message: str,
    *,
    session_id: str | None,
    user_id: str | None,
) -> AsyncIterator[str]:
    async for event in agent.arun(
        message,
        session_id=session_id,
        user_id=(user_id or "anonymous").strip() or "anonymous",
        stream=True,
    ):
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


def _build_fallback_agent(model_id: str | None = None) -> Agent:
    return Agent(
        id="security-operations",
        name="安全防御助手",
        role="安全防御运营助手",
        description="无工具模式下的安全防御运营助手。",
        instructions=[SAFE_FALLBACK_INSTRUCTIONS],
        model=_build_model(model_id),
        db=get_agno_postgres_db(),
        add_datetime_to_context=True,
        markdown=True,
    )


def _build_security_agent(
    mcp_tools: MCPTools,
    *,
    model_id: str | None,
    knowledge_owner_user_id: str | None,
) -> Agent:
    return Agent(
        id="security-operations",
        name="安全运营助手",
        role="安全运营综合专家",
        description="集威胁情报分析与安全剧本执行于一体的安全运营助手，可完成情报检索、深度分析和自动化处置全流程。",
        instructions=[AGENT_INSTRUCTIONS],
        model=_build_model(model_id),
        tools=[mcp_tools],
        knowledge=get_knowledge_base(),
        knowledge_filters={"user_id": knowledge_owner_user_id}
        if knowledge_owner_user_id
        else None,
        search_knowledge=True,
        add_search_knowledge_instructions=True,
        skills=_build_enabled_skills(),
        db=get_agno_postgres_db(),
        dependencies=dependencies,
        add_dependencies_to_context=True,
        add_history_to_context=True,
        update_memory_on_run=True,
        num_history_runs=5,
        add_datetime_to_context=True,
        markdown=True,
    )


async def stream_chat_with_agent(
    message: str,
    session_id: str | None = None,
    model_id: str | None = None,
    user_id: str | None = None,
    knowledge_owner_user_id: str | None = None,
) -> AsyncIterator[str]:
    """流式聊天，使用单个 Agent 统一处理安全运营任务"""
    try:
        async with MCPTools(
            transport="streamable-http",
            url=_build_mcp_url(),
            timeout_seconds=20,
        ) as mcp_tools:
            security_agent = _build_security_agent(
                mcp_tools,
                model_id=model_id,
                knowledge_owner_user_id=knowledge_owner_user_id,
            )

            async for chunk in _stream_agent_content(
                security_agent,
                message,
                session_id=session_id,
                user_id=user_id,
            ):
                yield chunk
    except Exception as exc:
        if not _is_provider_block_error(exc):
            raise
        logger.warning("模型服务拦截完整 Agent 上下文，切换到无工具降级模式: {}", exc)
        yield "模型服务拦截了完整 Agent 上下文，已切换到无工具安全模式。\n\n"
        fallback_agent = _build_fallback_agent(model_id)
        async for chunk in _stream_agent_content(
            fallback_agent,
            message,
            session_id=session_id,
            user_id=user_id,
        ):
            yield chunk
