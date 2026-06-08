import os
import json
from typing import Any, AsyncIterator, cast
from dotenv import load_dotenv
from textwrap import dedent
from pathlib import Path
from urllib.parse import urlencode
from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools
from agno.run.agent import RunEvent
from agno.skills import Skills, LocalSkills
from agno.tracing import setup_tracing
from api.services.model_config_service import get_model_for_run
from api.services.knowledge_service import agno_knowledge_retriever

load_dotenv(override=True)
# Set up database for traces
db = SqliteDb(db_file=os.environ.get("AGNO_TRACE_DB_FILE", "tmp/traces.db"))
# Enable tracing (call once at startup)
setup_tracing(db=db)


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

    当用户询问制度、处置规范、历史报告、资产说明、漏洞研判资料或要求基于已沉淀资料回答时，优先调用 `search_knowledge_base` 检索内部知识库。
    若知识库没有命中，必须明确说明"未检索到内部知识库依据"，再使用其他工具或通用推理补充。
    
    ---
    ## 五、行为准则

    - **依数行事**：仅使用工具和脚本提供的数据事实，严禁虚构信息。
    - **信息不足时**：先提 1-3 个关键澄清问题，再执行。
    - **专业客观**：保持情报分析的严谨性和客观性，避免主观臆断。
    - **闭环响应**：确保每个任务都有明确的结论或下一步建议。
""")


dependencies = {
    "feishu_webhook_url": _get_env("FEISHU_WEBHOOK_URL"),
}


SKILLS_DIR = Path(".skills")
SKILLS_CONFIG_FILE = Path("tmp/skills_config.json")


def _load_skills_config() -> dict[str, bool]:
    """加载 skills 启用/禁用配置"""
    if SKILLS_CONFIG_FILE.exists():
        try:
            return json.loads(SKILLS_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _build_enabled_skills() -> Skills | None:
    """根据配置构建仅启用的 Skills 加载器；全部禁用时返回 None"""
    cfg = _load_skills_config()
    if not SKILLS_DIR.is_dir():
        return None

    enabled_dirs: list[str] = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        # 默认启用
        if cfg.get(entry.name, True):
            enabled_dirs.append(str(entry))

    if not enabled_dirs:
        return None
    return Skills(loaders=[LocalSkills(d) for d in enabled_dirs])


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
    message: str, session_id: str | None = None, model_id: str | None = None
) -> AsyncIterator[str]:
    """流式聊天，使用单个 Agent 统一处理安全运营任务"""
    async with MCPTools(
        transport="streamable-http",
        url=_build_mcp_url(),
        timeout_seconds=20,
    ) as mcp_tools:
        security_agent = Agent(
            name="安全运营助手",
            role="安全运营综合专家",
            description="集威胁情报分析与安全剧本执行于一体的安全运营助手，可完成情报检索、深度分析和自动化处置全流程。",
            instructions=[AGENT_INSTRUCTIONS],
            model=_build_model(model_id),
            tools=[mcp_tools],
            knowledge_retriever=agno_knowledge_retriever,
            search_knowledge=True,
            add_search_knowledge_instructions=True,
            skills=_build_enabled_skills(),
            db=SqliteDb(DB_FILE),
            dependencies=dependencies,
            add_dependencies_to_context=True,
            add_history_to_context=True,
            update_memory_on_run=True,
            num_history_runs=5,
            add_datetime_to_context=True,
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
