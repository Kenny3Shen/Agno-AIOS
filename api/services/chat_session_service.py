from datetime import UTC, datetime
from typing import Any, cast

from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from agno.session.workflow import WorkflowSession
from api.auth.claims import actor_id
from api.auth.ownership import assert_owned_resource
from api.services.audit_service import record_audit_event_async
from api.services.postgres_store import (
    coerce_json_value,
    ensure_agno_postgres_tables_async,
    get_async_agno_postgres_db,
)
from api.services.chat_run_events import metric_values, source_items, tool_update
from api.services.chat_settings import get_chat_settings_async


ARCHIVED_METADATA_KEY = "agno_aios_archived"
ARCHIVED_BY_METADATA_KEY = "agno_aios_archived_by"
ARCHIVED_AT_METADATA_KEY = "agno_aios_archived_at"
TITLE_METADATA_KEY = "agno_aios_title"


async def is_session_archived_async(session_id: str) -> bool:
    await ensure_agno_postgres_tables_async()
    session = await get_async_agno_postgres_db().get_session(
        session_id,
        deserialize=False,
    )
    if not isinstance(session, dict):
        return False
    return _is_archived_metadata(session.get("metadata"))


async def get_session_owner_async(session_id: str) -> str | None:
    await ensure_agno_postgres_tables_async()
    session = await get_async_agno_postgres_db().get_session(
        session_id,
        deserialize=False,
    )
    if not isinstance(session, dict):
        return None
    return str(session.get("user_id") or "")


def _is_archived_metadata(value: Any) -> bool:
    metadata = coerce_json_value(value or {})
    if not isinstance(metadata, dict):
        return False
    return metadata.get(ARCHIVED_METADATA_KEY) is True


async def archive_session(
    session_id: str,
    user_id: str | None = None,
    *,
    actor: Any | None = None,
) -> bool:
    """Soft-archive a chat session without deleting Agno runs or traces."""
    await ensure_agno_postgres_tables_async()
    archived_by = actor_id(actor) if actor is not None else (user_id or "").strip()
    db = get_async_agno_postgres_db()
    session_row = await db.get_session(session_id, deserialize=False)
    if not isinstance(session_row, dict):
        return False

    session_user_id = str(session_row.get("user_id") or archived_by)
    if actor is not None:
        assert_owned_resource(
            actor,
            owner_user_id=session_user_id,
            resource_name="Session",
        )

    session: Any = await db.get_session(session_id)
    if not hasattr(session, "metadata"):
        return False
    metadata = coerce_json_value(getattr(session, "metadata", None) or {})
    if not isinstance(metadata, dict):
        metadata = {}
    session.metadata = {
        **metadata,
        ARCHIVED_METADATA_KEY: True,
        ARCHIVED_BY_METADATA_KEY: archived_by,
        ARCHIVED_AT_METADATA_KEY: datetime.now(UTC).isoformat(),
    }
    await db.upsert_session(cast(AgentSession | TeamSession | WorkflowSession, session))

    if actor is not None:
        await record_audit_event_async(
            actor,
            action="session.archive",
            resource_type="session",
            resource_id=session_id,
        )
    return True


async def rename_session(
    session_id: str,
    title: str,
    *,
    actor: Any | None = None,
) -> dict[str, Any] | None:
    """Set a user-owned session title in Agno session metadata."""
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("会话标题不能为空")
    if len(normalized_title) > 120:
        raise ValueError("会话标题不能超过 120 个字符")

    await ensure_agno_postgres_tables_async()
    db = get_async_agno_postgres_db()
    row = await db.get_session(session_id, deserialize=False)
    if not isinstance(row, dict):
        return None
    if actor is not None:
        assert_owned_resource(
            actor,
            owner_user_id=str(row.get("user_id") or ""),
            resource_name="Session",
        )
    session: Any = await db.get_session(session_id)
    if not hasattr(session, "metadata"):
        return None
    metadata = coerce_json_value(getattr(session, "metadata", None) or {})
    if not isinstance(metadata, dict):
        metadata = {}
    session.metadata = {**metadata, TITLE_METADATA_KEY: normalized_title}
    await db.upsert_session(cast(AgentSession | TeamSession | WorkflowSession, session))
    if actor is not None:
        await record_audit_event_async(
            actor,
            action="session.rename",
            resource_type="session",
            resource_id=session_id,
            metadata={"title_length": len(normalized_title)},
        )
    return {
        "session_id": session_id,
        "title": normalized_title,
        "preview": _preview_from_runs(coerce_json_value(row.get("runs"))) or "新对话",
    }


async def get_all_sessions_async(
    *,
    include_archived: bool = False,
    owner_user_id: str | None = None,
    include_runs: bool = False,
) -> list[dict[str, Any]]:
    """Read session summaries through Agno AsyncPostgresDb."""
    await ensure_agno_postgres_tables_async()
    result: Any = await get_async_agno_postgres_db().get_sessions(
        user_id=owner_user_id,
        limit=500,
        page=1,
        deserialize=False,
    )
    rows = cast(list[dict[str, Any]], result[0] if isinstance(result, tuple) else result)
    visible_rows = [
        row for row in rows if include_archived or not _is_archived_metadata(row.get("metadata"))
    ]

    return _project_session_rows(visible_rows, include_runs=include_runs)


def _sort_time(row: dict[str, Any]) -> float:
    value = row.get("updated_at") or row.get("created_at") or 0
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return float(timestamp())
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _preview_from_runs(runs: Any) -> str:
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], dict):
        return ""
    inp = runs[0].get("input", {})
    if isinstance(inp, dict):
        return str(inp.get("input_content") or "")[:80]
    if isinstance(inp, str):
        return inp[:80]
    return ""


def _project_session_rows(
    rows: list[dict[str, Any]],
    *,
    include_runs: bool,
) -> list[dict[str, Any]]:
    rows.sort(key=_sort_time, reverse=True)
    sessions: list[dict[str, Any]] = []
    for row in rows:
        runs = coerce_json_value(row.get("runs"))
        preview = _preview_from_runs(runs)
        session = {
            "session_id": row.get("session_id"),
            "user_id": row.get("user_id"),
            "preview": preview.strip() or "新对话",
            "title": _title_metadata(row.get("metadata")),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "archived": _is_archived_metadata(row.get("metadata")),
            "archived_at": _archived_at_metadata(row.get("metadata")),
        }
        if include_runs:
            session["runs"] = runs if isinstance(runs, list) else []
        sessions.append(session)
    return sessions


async def get_session_messages_async(
    session_id: str,
    *,
    actor: Any | None = None,
) -> list[dict[str, Any]]:
    """Read chat messages for one session through Agno AsyncPostgresDb."""
    await ensure_agno_postgres_tables_async()
    row = await get_async_agno_postgres_db().get_session(session_id, deserialize=False)
    if not isinstance(row, dict):
        return []

    if actor is not None:
        assert_owned_resource(
            actor,
            owner_user_id=str(row.get("user_id") or ""),
            resource_name="Session",
        )

    runs = coerce_json_value(row.get("runs"))
    if not isinstance(runs, list):
        return []

    chat_settings = await get_chat_settings_async()
    messages: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            continue
        inp = run.get("input", {})
        user_text = ""
        if isinstance(inp, dict):
            user_text = str(inp.get("input_content") or "")
        elif isinstance(inp, str):
            user_text = inp
        run_id = str(run.get("run_id") or f"history-{index}")
        if user_text.strip():
            messages.append({"id": f"{run_id}:user", "role": "user", "content": user_text.strip(), "final": True, "session_id": session_id})

        content = run.get("content", "")
        if isinstance(content, str) and content.strip():
            raw_tools = run.get("tools")
            tools = (
                [
                    tool_update(
                        tool,
                        "completed",
                        include_raw_io=chat_settings.show_raw_tool_io,
                    )
                    for tool in raw_tools
                ]
                if chat_settings.show_thought_chain and isinstance(raw_tools, list)
                else []
            )
            followups = run.get("followups")
            message = {
                "id": run_id,
                "role": "assistant",
                "content": content.strip(),
                "final": True,
                "run_id": run_id,
                "session_id": session_id,
                "status": str(run.get("status") or "completed"),
                "metrics": metric_values(run.get("metrics")),
                "sources": source_items(run.get("citations")) or source_items(run.get("references")),
                "tools": tools,
                "followups": [item for item in followups if isinstance(item, str)] if isinstance(followups, list) else [],
            }
            if chat_settings.show_raw_reasoning:
                reasoning = run.get("reasoning") or run.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning.strip():
                    message["reasoning"] = reasoning.strip()
                elif isinstance(reasoning, list):
                    content = "".join(str(item) for item in reasoning if isinstance(item, str)).strip()
                    if content:
                        message["reasoning"] = content
            messages.append(message)
    return messages


def _archived_at_metadata(value: Any) -> str:
    metadata = coerce_json_value(value or {})
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get(ARCHIVED_AT_METADATA_KEY) or "")


def _title_metadata(value: Any) -> str | None:
    metadata = coerce_json_value(value or {})
    if not isinstance(metadata, dict):
        return None
    title = metadata.get(TITLE_METADATA_KEY)
    return title.strip() if isinstance(title, str) and title.strip() else None
