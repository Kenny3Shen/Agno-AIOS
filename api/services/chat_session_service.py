from datetime import UTC, datetime
from typing import Any, Literal, cast

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
from api.services.chat_settings_service import get_chat_settings_async
from api.utils.pagination import pagination_meta


ARCHIVED_METADATA_KEY = "agno_aios_archived"
ARCHIVED_BY_METADATA_KEY = "agno_aios_archived_by"
ARCHIVED_AT_METADATA_KEY = "agno_aios_archived_at"
TITLE_METADATA_KEY = "agno_aios_title"



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


async def unarchive_session(
    session_id: str,
    user_id: str | None = None,
    *,
    actor: Any | None = None,
) -> bool:
    """Clear soft-archive flags so the session returns to recents."""
    await ensure_agno_postgres_tables_async()
    actor_user = actor_id(actor) if actor is not None else (user_id or "").strip()
    db = get_async_agno_postgres_db()
    session_row = await db.get_session(session_id, deserialize=False)
    if not isinstance(session_row, dict):
        return False

    session_user_id = str(session_row.get("user_id") or actor_user)
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
    next_meta = {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            ARCHIVED_METADATA_KEY,
            ARCHIVED_BY_METADATA_KEY,
            ARCHIVED_AT_METADATA_KEY,
        }
    }
    # Explicit false is treated as not archived by list filters (contains true only).
    next_meta[ARCHIVED_METADATA_KEY] = False
    session.metadata = next_meta
    await db.upsert_session(cast(AgentSession | TeamSession | WorkflowSession, session))

    if actor is not None:
        await record_audit_event_async(
            actor,
            action="session.unarchive",
            resource_type="session",
            resource_id=session_id,
        )
    return True


async def get_session_summary_async(
    session_id: str,
    *,
    actor: Any | None = None,
) -> dict[str, Any] | None:
    """Return one list-style session projection (title, type, workflow_id, …).

    Used for deep links when the session is outside the loaded recents window.
    """
    await ensure_agno_postgres_tables_async()
    row = await get_async_agno_postgres_db().get_session(session_id, deserialize=False)
    if not isinstance(row, dict):
        return None
    if actor is not None:
        assert_owned_resource(
            actor,
            owner_user_id=str(row.get("user_id") or ""),
            resource_name="Session",
        )
    session_row = cast(dict[str, Any], row)
    projected = _project_session_rows([session_row], include_runs=False, already_sorted=True)
    return projected[0] if projected else None


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
    archived_only: bool = False,
    owner_user_id: str | None,
    page: int,
    limit: int,
    q: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """SQL page of session rows with optional archive filter and text search."""
    from sqlalchemy import func, or_, select

    db = get_async_agno_postgres_db()
    table = await db._get_table(table_type="sessions")
    if table is None:
        return [], 0

    stmt = select(table)
    if owner_user_id is not None:
        stmt = stmt.where(table.c.user_id == owner_user_id)
    if archived_only:
        # Only sessions explicitly marked archived in metadata.
        stmt = stmt.where(table.c.metadata.contains({"agno_aios_archived": True}))
    elif not include_archived:
        # JSONB bool/string/missing -> treat only explicit true as archived.
        stmt = stmt.where(
            or_(
                table.c.metadata.is_(None),
                ~table.c.metadata.contains({"agno_aios_archived": True}),
            )
        )

    needle = (q or "").strip()
    if needle:
        from sqlalchemy import String, cast

        pattern = f"%{needle}%"
        # Title lives in JSONB metadata; session_id is the durable key;
        # runs JSON includes first-turn input used for list previews.
        # Cap runs text to keep ILIKE off multi-MB session payloads.
        title_expr = table.c.metadata[TITLE_METADATA_KEY].astext
        runs_text = func.left(cast(table.c.runs, String), 4000)
        stmt = stmt.where(
            or_(
                table.c.session_id.ilike(pattern),
                title_expr.ilike(pattern),
                runs_text.ilike(pattern),
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


async def list_sessions_async(
    *,
    include_archived: bool = False,
    archived_only: bool = False,
    owner_user_id: str | None = None,
    include_runs: bool = False,
    page: int = 1,
    limit: int = 40,
    q: str | None = None,
) -> dict[str, Any]:
    """Read a page of session summaries (Agno-style data/meta).

    Returns Agno-style ``{data, meta}``. Archive filtering uses
    ``metadata @> {"agno_aios_archived": true}`` so totals stay accurate beyond
    the previous 500-row window. ``archived_only`` returns only archived rows
    (implies archive filter; ignores ``include_archived``). Optional ``q``
    matches session_id, custom title metadata, or runs JSON text (preview input).
    """
    await ensure_agno_postgres_tables_async()
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 40), 500))
    # archived_only wins over include_archived for explicit archived inbox pages.
    effective_include = True if archived_only else include_archived
    rows, total_count = await _query_sessions_page(
        include_archived=effective_include,
        archived_only=archived_only,
        owner_user_id=owner_user_id,
        page=safe_page,
        limit=safe_limit,
        q=q,
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


def _session_type_from_row(row: dict[str, Any]) -> str:
    """Normalize Agno session type for list/recents (agent | team | workflow)."""
    raw = row.get("session_type")
    if raw is not None and str(raw).strip():
        value = raw.value if hasattr(raw, "value") else raw
        text = str(value).strip().lower()
        if text in {"agent", "team", "workflow"}:
            return text
    if row.get("workflow_id"):
        return "workflow"
    if row.get("team_id"):
        return "team"
    if row.get("agent_id"):
        return "agent"
    return "agent"


def _preview_from_runs(runs: Any) -> str:
    """Best-effort list preview from the **latest** run input (chat + workflow).

    Session ``runs`` grow over multi-turn chats; the last top-level entry best
    reflects the recents list. Callers should already filter child member runs.
    """
    if not isinstance(runs, list) or not runs:
        return ""
    run: dict[str, Any] | None = None
    for item in reversed(runs):
        if isinstance(item, dict):
            run = cast(dict[str, Any], item)
            break
    if run is None:
        return ""
    candidates: list[Any] = [
        run.get("input"),
        run.get("content"),
        run.get("message"),
        run.get("input_content"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
        if isinstance(value, dict):
            for key in ("input_content", "content", "message", "input", "text", "query"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()[:80]
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
        session_type = _session_type_from_row(row)
        top_runs: list[dict[str, Any]] = []
        if isinstance(runs, list):
            for run in runs:
                if isinstance(run, dict) and not _is_child_member_run(run):
                    top_runs.append(run)
        preview = _preview_from_runs(top_runs or runs).strip()
        if not preview:
            preview = "工作流运行" if session_type == "workflow" else "新对话"
        workflow_id = str(row.get("workflow_id") or "").strip() or None
        agent_id = str(row.get("agent_id") or "").strip() or None
        team_id = str(row.get("team_id") or "").strip() or None
        session = {
            "session_id": row.get("session_id"),
            "user_id": row.get("user_id"),
            "session_type": session_type,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "team_id": team_id,
            "preview": preview,
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




_MISSING = object()


def _history_runtime_tool_surface(
    run: dict[str, object],
) -> tuple[bool | None, bool | None, list[str] | None | object, bool | None]:
    """Extract enable_tools / lean_mode / skill_names / search_knowledge from metadata.

    Returns:
        (enable_tools, lean_mode, skill_names, search_knowledge)
        skill_names uses ``_MISSING`` when runtime metadata is absent.
        lean_mode is **auto-intent lite only** (tools on + empty skill list), not tools-off.
        search_knowledge is the **effective** mount (false on lean / tools-off).
    """
    metadata = coerce_json_value(run.get("metadata") or {})
    if not isinstance(metadata, dict):
        return None, None, _MISSING, None
    context = metadata.get("tais_runtime")
    if not isinstance(context, dict):
        return None, None, _MISSING, None

    enable_tools = bool(context.get("enable_tools", True))
    raw_skills = context.get("skill_names", _MISSING)
    skill_names: list[str] | None | object
    if raw_skills is _MISSING:
        skill_names = _MISSING
    elif raw_skills is None:
        skill_names = None
    elif isinstance(raw_skills, list):
        skill_names = [str(item).strip() for item in raw_skills if str(item).strip()]
    else:
        skill_names = _MISSING

    # Auto-lite only when tools are enabled and intent attached no skills.
    if not enable_tools:
        lean_mode = False
    elif skill_names is _MISSING:
        lean_mode = None
    elif isinstance(skill_names, list) and len(skill_names) == 0:
        lean_mode = True
    else:
        lean_mode = False

    requested_search = bool(context.get("search_knowledge", True))
    search_knowledge = bool(
        requested_search and enable_tools and lean_mode is not True
    )
    return enable_tools, lean_mode, skill_names, search_knowledge



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



def _history_user_attachments(run: dict[str, Any]) -> list[dict[str, str]]:
    """Project light attachment cards from Agno run input media."""
    items: list[dict[str, str]] = []
    inp = coerce_json_value(run.get("input"))
    media_sources: list[tuple[str, object]] = []
    if isinstance(inp, dict):
        for key, kind in (
            ("images", "image"),
            ("files", "document"),
            ("audio", "audio"),
            ("audios", "audio"),
            ("videos", "video"),
        ):
            media_sources.append((kind, inp.get(key)))
    for kind, value in media_sources:
        if not isinstance(value, list):
            continue
        for raw in value:
            if not isinstance(raw, dict):
                continue
            name = (
                str(raw.get("filename") or raw.get("name") or raw.get("id") or kind).strip()
                or kind
            )
            mime = str(raw.get("mime_type") or raw.get("mime") or "").strip()
            items.append({"name": name, "mime": mime, "kind": kind})
    # Fallback: T.A.I.S may stash attachment meta on runtime metadata in future.
    metadata = coerce_json_value(run.get("metadata") or {})
    if isinstance(metadata, dict):
        context = metadata.get("tais_runtime")
        if isinstance(context, dict):
            extra = context.get("attachments")
            if isinstance(extra, list):
                for raw in extra:
                    if not isinstance(raw, dict):
                        continue
                    name = str(raw.get("name") or "").strip()
                    if not name:
                        continue
                    items.append(
                        {
                            "name": name,
                            "mime": str(raw.get("mime") or "").strip(),
                            "kind": str(raw.get("kind") or "document").strip() or "document",
                        }
                    )
    # Dedupe by name+kind
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        key = (item["name"], item["kind"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique




def _is_child_member_run(run: object) -> bool:
    """True for Team member runs nested under a leader (have parent_run_id)."""
    if not isinstance(run, dict):
        return False
    return bool(str(run.get("parent_run_id") or "").strip())


def _member_rows(
    run: dict[str, Any],
    *,
    sibling_runs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return member_responses for a Team leader run.

    Prefer ``member_responses`` on the leader. If empty, reconstruct from
    child Agent runs in the same session (``parent_run_id == leader.run_id``),
    so history still shows member tools after storage gaps.
    """
    raw = coerce_json_value(run.get("member_responses"))
    if isinstance(raw, list) and raw:
        return [row for row in raw if isinstance(row, dict)]

    leader_id = str(run.get("run_id") or "").strip()
    if not leader_id or not sibling_runs:
        return []

    reconstructed: list[dict[str, Any]] = []
    for child in sibling_runs:
        if not isinstance(child, dict):
            continue
        if str(child.get("parent_run_id") or "").strip() != leader_id:
            continue
        member_id = str(child.get("agent_id") or "member").strip() or "member"
        member_name = (
            str(child.get("agent_name") or child.get("name") or member_id).strip()
            or member_id
        )
        tools = child.get("tools")
        reconstructed.append(
            {
                "agent_id": member_id,
                "agent_name": member_name,
                "content": child.get("content"),
                "status": child.get("status"),
                "tools": tools if isinstance(tools, list) else [],
            }
        )
    return reconstructed


def _history_team_thoughts(
    run: dict[str, Any],
    *,
    tool_status: Literal["running", "completed", "error"],
    sibling_runs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Project Team member_responses into Chat thought_chain items."""
    thoughts: list[dict[str, Any]] = []
    for member in _member_rows(run, sibling_runs=sibling_runs):
        member_id = str(member.get("agent_id") or "member").strip() or "member"
        member_name = str(member.get("agent_name") or member_id).strip() or member_id
        summary = member.get("content")
        if not isinstance(summary, str) or not summary.strip():
            summary = "完成"
        member_status = str(member.get("status") or "").strip().lower()
        if member_status in {"error", "failed"}:
            status = "error"
        elif member_status in {"cancelled", "canceled"}:
            status = "error"
        elif tool_status == "running":
            status = "running"
        else:
            status = "completed"
        thoughts.append(
            {
                "id": f"member:{member_id}",
                "type": "member",
                "title": f"成员 · {member_name}",
                "status": status,
                "summary": summary.strip()[:280],
            }
        )
    return thoughts


def _history_team_tools(
    run: dict[str, Any],
    *,
    tool_status: Literal["running", "completed", "error"],
    include_raw_io: bool,
    sibling_runs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Project leader + member tools with Team member prefixes for Chat UI."""
    projected: list[dict[str, Any]] = []
    leader_tools = run.get("tools")
    if isinstance(leader_tools, list):
        for tool in leader_tools:
            if isinstance(tool, dict):
                projected.append(
                    tool_update(tool, tool_status, include_raw_io=include_raw_io)
                )
    for member in _member_rows(run, sibling_runs=sibling_runs):
        member_id = str(member.get("agent_id") or "member").strip() or "member"
        member_name = str(member.get("agent_name") or member_id).strip() or member_id
        member_tools = member.get("tools")
        if not isinstance(member_tools, list):
            continue
        for tool in member_tools:
            if not isinstance(tool, dict):
                continue
            row = tool_update(tool, tool_status, include_raw_io=include_raw_io)
            raw_id = str(row.get("id") or "tool")
            raw_name = str(row.get("name") or "工具调用")
            row["id"] = f"member:{member_id}:{raw_id}"
            row["name"] = f"[{member_name}] {raw_name}"
            row["member_id"] = member_id
            row["member_name"] = member_name
            projected.append(row)
    return projected


def _history_run_has_assistant_payload(
    run: dict[str, Any],
    *,
    sibling_runs: list[dict[str, Any]] | None = None,
) -> bool:
    content = run.get("content", "")
    if isinstance(content, str) and content.strip():
        return True
    tools_value = run.get("tools")
    if isinstance(tools_value, list) and any(
        isinstance(tool, dict)
        and (
            (tool.get("confirmed") is True and tool.get("result") not in (None, ""))
            or tool.get("confirmed") is False
            or tool.get("tool_call_error") is True
            or str(tool.get("confirmation_note") or "").strip()
            or tool.get("tool_name")
            or tool.get("tool_call_id")
        )
        for tool in tools_value
    ):
        return True
    for member in _member_rows(run, sibling_runs=sibling_runs):
        member_content = member.get("content")
        if isinstance(member_content, str) and member_content.strip():
            return True
        member_tools = member.get("tools")
        if isinstance(member_tools, list) and member_tools:
            return True
    return False



def _history_member_content_fallback(
    run: dict[str, Any],
    *,
    sibling_runs: list[dict[str, Any]] | None = None,
) -> str:
    """When the Team leader left content empty, use the last member summary."""
    for member in reversed(_member_rows(run, sibling_runs=sibling_runs)):
        content = member.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


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
    dict_runs: list[dict[str, Any]] = [r for r in runs if isinstance(r, dict)]
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            continue
        # Team sessions may store member Agent runs alongside the leader Team run.
        # Member tools/thoughts come from leader.member_responses — skip child rows.
        if _is_child_member_run(run):
            continue
        user_text = _preview_from_runs([run])
        run_id = str(run.get("run_id") or f"history-{index}")
        attachments = _history_user_attachments(cast(dict[str, Any], run))
        if user_text.strip() or attachments:
            user_msg: dict[str, Any] = {
                "id": f"{run_id}:user",
                "role": "user",
                "content": user_text.strip(),
                "final": True,
                "session_id": session_id,
            }
            if attachments:
                user_msg["attachments"] = attachments
            messages.append(user_msg)

        content = run.get("content", "")
        if _history_run_has_assistant_payload(cast(dict[str, Any], run), sibling_runs=dict_runs):
            tools_value = run.get("tools")
            raw_tools: list[Any] = tools_value if isinstance(tools_value, list) else []
            # Include member tools when computing HITL/paused status for Team runs.
            for member in _member_rows(
                cast(dict[str, Any], run), sibling_runs=dict_runs
            ):
                member_tools = member.get("tools")
                if isinstance(member_tools, list):
                    raw_tools = [*raw_tools, *member_tools]
            status = _history_run_status(run.get("status"), raw_tools)
            tool_status: Literal["running", "completed", "error"] = (
                "running" if status == "paused" else "completed"
            )
            if chat_settings.show_thought_chain:
                tools = _history_team_tools(
                    cast(dict[str, Any], run),
                    tool_status=tool_status,
                    include_raw_io=chat_settings.show_raw_tool_io,
                    sibling_runs=dict_runs,
                )
                thought_chain = _history_team_thoughts(
                    cast(dict[str, Any], run),
                    tool_status=tool_status,
                    sibling_runs=dict_runs,
                )
            else:
                tools = []
                thought_chain = []
            followups = run.get("followups")
            message: dict[str, Any] = {
                "id": run_id,
                "role": "assistant",
                "content": (
                    _project_history_content(cast(dict[str, object], run), status)
                    or (content.strip() if isinstance(content, str) else "")
                    or _history_member_content_fallback(
                        cast(dict[str, Any], run), sibling_runs=dict_runs
                    )
                ),
                "final": True,
                "run_id": run_id,
                "session_id": session_id,
                "status": status,
                "metrics": metric_values(run.get("metrics")),
                "sources": source_items(run.get("citations")) or source_items(run.get("references")),
                "tools": tools,
                "followups": [item for item in followups if isinstance(item, str)] if isinstance(followups, list) else [],
            }
            if thought_chain:
                message["thought_chain"] = thought_chain
            approval_id = _history_approval_id(raw_tools)
            if approval_id:
                message["approval_id"] = approval_id
            enable_tools, lean_mode, skill_names, search_knowledge = (
                _history_runtime_tool_surface(cast(dict[str, object], run))
            )
            if enable_tools is not None:
                message["enable_tools"] = enable_tools
            if lean_mode is not None:
                message["lean_mode"] = lean_mode
            if skill_names is not _MISSING:
                message["skill_names"] = skill_names
            if search_knowledge is not None:
                message["search_knowledge"] = search_knowledge
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
