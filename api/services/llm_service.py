import os
from typing import Any, AsyncIterator, cast
from dotenv import load_dotenv
from textwrap import dedent
from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools
from agno.run.agent import RunEvent
from agno.skills import Skills, LocalSkills

load_dotenv(override=True)


def _get_env(key: str, default: str = "") -> str:
    """优先从 os.environ 读取（支持运行时动态修改），回退到默认值"""
    return os.environ.get(key, default)


def _build_model() -> OpenAILike:
    return OpenAILike(
        id=_get_env("LLM_EP", "gpt-3.5-turbo"),
        api_key=_get_env("LLM_API_KEY"),
        base_url=_get_env("LLM_URL"),
    )


AGENT_INSTRUCTIONS = dedent("""\
    你是安全运营助手，具备 **威胁情报分析** 和 **安全剧本执行** 两大核心能力。

    ---
    ## 一、威胁情报分析

    使用 `threat-trace-skill` 技能检索、分析并汇报网络威胁情报。

    ---
    ## 二、安全剧本执行

    使用 `playbook-skill` 技能和 MCP 工具调用安全自动化剧本（w5-soar / octomation）。

    ---
    ## 三、通知与上报

    若用户要求"发送通知"或"上报"，使用 `basic_send_feishu_notify` 工具。
    
    ---
    ## 四、行为准则

    - **依数行事**：仅使用工具和脚本提供的数据事实，严禁虚构信息。
    - **信息不足时**：先提 1-3 个关键澄清问题，再执行。
    - **专业客观**：保持情报分析的严谨性和客观性，避免主观臆断。
    - **闭环响应**：确保每个任务都有明确的结论或下一步建议。
""")


dependencies = {
    "feishu_webhook_url": _get_env("FEISHU_WEBHOOK_URL"),
}


DB_FILE = "security_agent.db"


def get_all_sessions() -> list[dict]:
    """从 security_agent.db 读取所有会话摘要"""
    import sqlite3
    import json

    if not os.path.exists(DB_FILE):
        return []
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT session_id, created_at, updated_at, runs "
            "FROM agno_sessions ORDER BY updated_at DESC"
        )
        sessions: list[dict] = []
        for sid, created, updated, runs_raw in cur.fetchall():
            preview = ""
            try:
                runs_str = json.loads(runs_raw)
                runs = json.loads(runs_str) if isinstance(runs_str, str) else runs_str
                if runs and isinstance(runs[0], dict):
                    inp = runs[0].get("input", {})
                    if isinstance(inp, dict):
                        preview = inp.get("input_content", "")[:80]
                    elif isinstance(inp, str):
                        preview = inp[:80]
            except Exception:
                pass
            sessions.append(
                {
                    "session_id": sid,
                    "preview": preview.strip() or "新对话",
                    "created_at": created,
                    "updated_at": updated,
                }
            )
        return sessions
    finally:
        conn.close()


def get_session_messages(session_id: str) -> list[dict]:
    """从 security_agent.db 读取指定会话的用户/助手消息列表"""
    import sqlite3
    import json

    if not os.path.exists(DB_FILE):
        return []
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT runs FROM agno_sessions WHERE session_id = ?", (session_id,)
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return []

        runs_str = json.loads(row[0])
        runs = json.loads(runs_str) if isinstance(runs_str, str) else runs_str

        messages: list[dict] = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            # 用户消息
            inp = run.get("input", {})
            user_text = ""
            if isinstance(inp, dict):
                user_text = inp.get("input_content", "")
            elif isinstance(inp, str):
                user_text = inp
            if user_text.strip():
                messages.append({"role": "user", "content": user_text.strip()})
            # 助手回复
            content = run.get("content", "")
            if isinstance(content, str) and content.strip():
                messages.append({"role": "assistant", "content": content.strip()})
        return messages
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """删除指定会话"""
    import sqlite3

    if not os.path.exists(DB_FILE):
        return False
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM agno_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def stream_chat_with_agent(
    message: str, session_id: str | None = None
) -> AsyncIterator[str]:
    """流式聊天，使用单个 Agent 统一处理安全运营任务"""
    async with MCPTools(
        transport="streamable-http",
        url=f"{_get_env('MCP_SERVER_URL')}?token={_get_env('MCP_TOKEN')}",
        timeout_seconds=20,
        refresh_connection=True,
    ) as mcp_tools:
        security_agent = Agent(
            name="安全运营助手",
            role="安全运营综合专家",
            description="集威胁情报分析与安全剧本执行于一体的安全运营助手，可完成情报检索、深度分析和自动化处置全流程。",
            instructions=[AGENT_INSTRUCTIONS],
            model=_build_model(),
            tools=[mcp_tools],
            skills=Skills(loaders=[LocalSkills(".skills")]),
            db=SqliteDb(DB_FILE),
            dependencies=dependencies,
            add_dependencies_to_context=True,
            add_history_to_context=True,
            update_memory_on_run=True,
            num_history_runs=5,
            markdown=True,
        )

        async for event in security_agent.arun(
            message, session_id=session_id, stream=True
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
