import os
from textwrap import dedent
from typing import AsyncIterator, Any, cast
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.run.agent import RunEvent
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools

load_dotenv(override=True)

instructions = dedent(
    """你是一个网络安全专家，负责回答与 CVE、漏洞与攻防相关的问题。
    要求：
    - 优先调用工具获取事实与证据，再进行总结与建议。
    - 回答要简洁、结构化，必要时给出可执行建议。
    - 不确定时明确说明不确定，并建议下一步。
    """
)


def _build_model() -> OpenAILike:
    return OpenAILike(
        id=os.getenv("LLM_EP", "gpt-3.5-turbo"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_URL"),
        extra_body={"thinking": {"type": "disabled"}},
    )


async def stream_chat_with_agent(message: str) -> AsyncIterator[str]:
    """流式聊天，返回增量内容"""
    async with MCPTools(
        transport="sse",
        url="http://localhost:8000/mcp/",
    ) as mcp_tools:
        agent = Agent(
            name="安全助手",
            instructions=dedent(
                """你是一个网络安全专家，负责回答与 CVE、漏洞与攻防相关的问题。
                        要求：
                        - 优先调用工具获取事实与证据，再进行总结与建议。
                        - 回答要简洁、结构化，必要时给出可执行建议。
                        - 不确定时明确说明不确定，并建议下一步。
                    """,
            ),
            model=_build_model(),
            tools=[mcp_tools],
            db=SqliteDb("agent.db"),
            add_history_to_context=True,
            #markdown=True,
        )
        async for event in agent.arun(message, stream=True):
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
