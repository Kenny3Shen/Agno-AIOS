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
from api.services.chat_run_events import (
    approval_rejection_reason,
    metric_values,
    source_items,
    tool_update,
)
from api.services.chat_settings import get_chat_settings_async
from api.utils.pagination import pagination_meta


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





async def _query_sessions_page(
    *,
    include_archived: bool,
    owner_user_id: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """SQL page of session rows with optional archive filter."""
    from sqlalchemy import func, or_, select

    db = get_async_agno_postgres_db()
    table = await db._get_table(table_type="sessions")
    if table is None:
        return [], 0

    stmt = select(table)
    if owner_user_id is not None:
        stmt = stmt.where(table.c.user_id == owner_user_id)
    if not include_archived:
        # JSONB bool/string/missing -> treat only explicit true as archived.
        stmt = stmt.where(
            or_(
                table.c.metadata.is_(None),
                ~table.c.metadata.contains({"agno_aios_archived": True}),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.alias())
    order_col = func.coalesce(table.c.updated_at, table.c.created_at)
    page_stmt = (
        stmt.order_by(order_col.desc().nullslast(), table.c.session_id.desc())
        .limit(limit)
        .offset((page - 1) * limit)
    )

    async with db.async_session_factory() as session:
        total_count = int(await session.scalar(count_stmt) or 0)
        result = await session.execute(page_stmt)
        rows = [dict(row._mapping) for row in result.fetchall()]
    return rows, total_count


async def get_all_sessions_async(
    *,
    include_archived: bool = False,
    owner_user_id: str | None = None,
    include_runs: bool = False,
    page: int = 1,
    limit: int = 500,
) -> dict[str, Any]:
    """Read session summaries with DB-level page/limit.

    Returns Agno-style ``{data, meta}``. Archive filtering uses
    ``metadata @> {"agno_aios_archived": true}`` so totals stay accurate beyond
    the previous 500-row window.
    """
    await ensure_agno_postgres_tables_async()
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 500), 500))
    rows, total_count = await _query_sessions_page(
        include_archived=include_archived,
        owner_user_id=owner_user_id,
        page=safe_page,
        limit=safe_limit,
    )
    sessions = _project_session_rows(rows, include_runs=include_runs, already_sorted=True)
    return {
        "data": sessions,
        "meta": pagination_meta(
            page=safe_page,
            limit=safe_limit,
            total_count=total_count,
        ),
    }


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
    already_sorted: bool = False,
) -> list[dict[str, Any]]:
    if not already_sorted:
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



def _history_run_status(value: object, tools: object) -> str:
    """Map Agno run status values onto chat UI statuses."""
    raw = str(value or "").strip()
    normalized = raw.lower()
    if normalized in {"paused", "pending"}:
        status = "paused"
    elif normalized in {"cancelled", "canceled"}:
        status = "cancelled"
    elif normalized in {"error", "failed"}:
        status = "failed"
    elif normalized in {"running", "started", "streaming"}:
        status = "streaming"
    else:
        status = "completed"

    if status != "paused":
        return status

    # Keep waiting-for-approval only while a confirmation tool is still unresolved.
    if isinstance(tools, list):
        waiting = False
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            confirmed = tool.get("confirmed")
            requires_confirmation = bool(tool.get("requires_confirmation"))
            approval_type = str(tool.get("approval_type") or "")
            has_approval = bool(tool.get("approval_id"))
            if not (requires_confirmation or approval_type == "required" or has_approval):
                continue
            if confirmed is True or confirmed is False:
                continue
            waiting = True
            break
        if not waiting:
            return "completed"
    return "paused"


def _history_approval_id(tools: object) -> str | None:
    if not isinstance(tools, list):
        return None
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        approval_id = tool.get("approval_id")
        if isinstance(approval_id, str) and approval_id.strip():
            return approval_id.strip()
    return None


def _project_history_content(run: dict[str, object], status: str) -> str:
    """Prefer non-stale assistant text; after HITL resume, fall back to tool outcomes."""
    content = run.get("content")
    content_text = content.strip() if isinstance(content, str) else ""
    tools_value = run.get("tools")
    tools: list[Any] = tools_value if isinstance(tools_value, list) else []
    confirmed = [
        tool
        for tool in tools
        if isinstance(tool, dict) and tool.get("confirmed") is True and tool.get("result") not in (None, "")
    ]
    rejected = [
        tool
        for tool in tools
        if isinstance(tool, dict) and (tool.get("confirmed") is False or tool.get("tool_call_error") is True)
    ]
    waiting_markers = ("等待管理员审批", "i have tools to execute, but i need confirmation")
    stale = content_text.casefold()
    is_stale = any(marker in stale for marker in waiting_markers)
    has_admin_reason = "Rejected by administrator" in content_text or "拒绝原因" in content_text
    if rejected and status != "paused" and (not content_text or is_stale or not has_admin_reason):
        admin_reason = approval_rejection_reason(run)
        notes = [str(tool.get("confirmation_note") or "").strip() for tool in rejected]
        if admin_reason:
            notes.append(f"Rejected by administrator: {admin_reason}")
        if notes and not has_admin_reason:
            lines_out = ["## HITL 请求未执行"]
            for tool in rejected:
                name = str(tool.get("tool_name") or "tool")
                note = str(tool.get("confirmation_note") or "").strip()
                if admin_reason and (not note or note == "Tool call was rejected"):
                    note = f"Rejected by administrator: {admin_reason}"
                note = note or "Tool call was rejected"
                args = tool.get("tool_args") if isinstance(tool.get("tool_args"), dict) else {}
                lines_out.append(f"- **工具**：`{name}`")
                if isinstance(args, dict) and args.get("target"):
                    lines_out.append(f"- **目标**：`{args.get('target')}`")
                lines_out.append(f"- **拒绝原因**：{note}")
            lines_out.append("")
            lines_out.append("管理员已拒绝该 HITL 请求；工具未执行。")
            return chr(10).join(lines_out)
    if confirmed and status != "paused" and (not content_text or is_stale):
        lines_out = ["## HITL 工具已执行"]
        for tool in confirmed:
            name = str(tool.get("tool_name") or "tool")
            result = tool.get("result")
            lines_out.append(f"- **工具**：`{name}`")
            lines_out.append(f"- **结果**：`{result}`")
        lines_out.append("")
        lines_out.append("管理员审批已处理；以上结果来自审批恢复后的工具执行记录。")
        return chr(10).join(lines_out)
    return content_text


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
        tools_value_for_gate = run.get("tools")
        has_tool_results = isinstance(tools_value_for_gate, list) and any(
            isinstance(tool, dict)
            and (
                (tool.get("confirmed") is True and tool.get("result") not in (None, ""))
                or tool.get("confirmed") is False
                or tool.get("tool_call_error") is True
                or str(tool.get("confirmation_note") or "").strip()
            )
            for tool in tools_value_for_gate
        )
        if (isinstance(content, str) and content.strip()) or has_tool_results:
            tools_value = run.get("tools")
            raw_tools: list[Any] = tools_value if isinstance(tools_value, list) else []
            status = _history_run_status(run.get("status"), raw_tools)
            tool_status = "running" if status == "paused" else "completed"
            tools = (
                [
                    tool_update(
                        tool,
                        tool_status,
                        include_raw_io=chat_settings.show_raw_tool_io,
                    )
                    for tool in raw_tools
                ]
                if chat_settings.show_thought_chain
                else []
            )
            followups = run.get("followups")
            message: dict[str, Any] = {
                "id": run_id,
                "role": "assistant",
                "content": _project_history_content(cast(dict[str, object], run), status) or (content.strip() if isinstance(content, str) else ""),
                "final": True,
                "run_id": run_id,
                "session_id": session_id,
                "status": status,
                "metrics": metric_values(run.get("metrics")),
                "sources": source_items(run.get("citations")) or source_items(run.get("references")),
                "tools": tools,
                "followups": [item for item in followups if isinstance(item, str)] if isinstance(followups, list) else [],
            }
            approval_id = _history_approval_id(raw_tools)
            if approval_id:
                message["approval_id"] = approval_id
            if chat_settings.show_raw_reasoning:
                reasoning = run.get("reasoning") or run.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning.strip():
                    message["reasoning"] = reasoning.strip()
                elif isinstance(reasoning, list):
                    joined = "".join(str(item) for item in reasoning if isinstance(item, str)).strip()
                    if joined:
                        message["reasoning"] = joined
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
