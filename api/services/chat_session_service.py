from datetime import UTC, datetime
from typing import Any, cast

from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from agno.session.workflow import WorkflowSession
from api.auth.permissions import actor_id, assert_owned_resource
from api.services.audit_service import record_audit_event_async
from api.services.postgres_store import (
    coerce_json_value,
    ensure_agno_postgres_tables_async,
    get_async_agno_postgres_db,
)


ARCHIVED_METADATA_KEY = "agno_aios_archived"
ARCHIVED_BY_METADATA_KEY = "agno_aios_archived_by"
ARCHIVED_AT_METADATA_KEY = "agno_aios_archived_at"


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
) -> list[dict[str, str]]:
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

    messages: list[dict[str, str]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        inp = run.get("input", {})
        user_text = ""
        if isinstance(inp, dict):
            user_text = str(inp.get("input_content") or "")
        elif isinstance(inp, str):
            user_text = inp
        if user_text.strip():
            messages.append({"role": "user", "content": user_text.strip()})

        content = run.get("content", "")
        if isinstance(content, str) and content.strip():
            messages.append({"role": "assistant", "content": content.strip()})
    return messages


def _archived_at_metadata(value: Any) -> str:
    metadata = coerce_json_value(value or {})
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get(ARCHIVED_AT_METADATA_KEY) or "")
