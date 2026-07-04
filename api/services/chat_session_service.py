from typing import Any

from psycopg import sql

from api.auth.permissions import actor_id, assert_owned_resource
from api.services.audit_service import record_audit_event
from api.services.postgres_store import (
    agno_schema,
    app_schema,
    coerce_json_value,
    ensure_agno_postgres_tables,
    postgres_connect,
)


def _archive_table() -> sql.Identifier:
    return sql.Identifier(app_schema(), "chat_session_archives")


def ensure_chat_session_archive_table() -> None:
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(app_schema())
                )
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL DEFAULT '',
                        archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        reason TEXT NOT NULL DEFAULT '',
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                    """
                ).format(_archive_table())
            )


def is_session_archived(session_id: str) -> bool:
    ensure_chat_session_archive_table()
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT 1 FROM {} WHERE session_id = %s").format(
                    _archive_table()
                ),
                (session_id,),
            )
            return cursor.fetchone() is not None


def get_session_owner(session_id: str) -> str | None:
    ensure_agno_postgres_tables()
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT user_id FROM {} WHERE session_id = %s").format(
                    sql.Identifier(agno_schema(), "agno_sessions")
                ),
                (session_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return str(row.get("user_id") or "")


def _is_archived_metadata(value: Any) -> bool:
    metadata = coerce_json_value(value or {})
    if not isinstance(metadata, dict):
        return False
    return metadata.get("agno_aios_archived") is True


def archive_session(
    session_id: str,
    user_id: str | None = None,
    *,
    actor: Any | None = None,
) -> bool:
    """Soft-archive a chat session without deleting Agno runs or traces."""
    ensure_agno_postgres_tables()
    ensure_chat_session_archive_table()
    archived_by = actor_id(actor) if actor is not None else (user_id or "").strip()

    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT session_id, user_id FROM {} WHERE session_id = %s"
                ).format(sql.Identifier(agno_schema(), "agno_sessions")),
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            session_user_id = str(row.get("user_id") or archived_by)
            if actor is not None:
                assert_owned_resource(
                    actor,
                    owner_user_id=session_user_id,
                    resource_name="Session",
                )
            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (session_id, user_id, archived_at, metadata)
                    VALUES (%s, %s, now(), jsonb_build_object('archived_by', %s::text))
                    ON CONFLICT (session_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        archived_at = now(),
                        metadata = EXCLUDED.metadata
                    """
                ).format(_archive_table()),
                (session_id, session_user_id, archived_by),
            )
            cursor.execute(
                sql.SQL(
                    """
                    UPDATE {}
                    SET metadata = coalesce(metadata, '{{}}'::jsonb)
                        || jsonb_build_object(
                            'agno_aios_archived', true,
                            'agno_aios_archived_by', %s::text,
                            'agno_aios_archived_at', now()
                        )
                    WHERE session_id = %s
                    """
                ).format(sql.Identifier(agno_schema(), "agno_sessions")),
                (archived_by, session_id),
            )
            if actor is not None:
                record_audit_event(
                    actor,
                    action="session.archive",
                    resource_type="session",
                    resource_id=session_id,
                )
            return True


def get_all_sessions(
    *,
    include_archived: bool = False,
    owner_user_id: str | None = None,
    include_runs: bool = False,
) -> list[dict[str, Any]]:
    """从 PostgreSQL 读取所有会话摘要。"""
    ensure_agno_postgres_tables()
    ensure_chat_session_archive_table()
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                SELECT
                    s.session_id,
                    s.created_at,
                    s.updated_at,
                    s.user_id,
                    s.runs,
                    s.metadata,
                    a.archived_at
                FROM {} AS s
                LEFT JOIN {} AS a ON a.session_id = s.session_id
                WHERE (%s
                    OR (
                        a.session_id IS NULL
                        AND coalesce(s.metadata ->> 'agno_aios_archived', 'false') <> 'true'
                    ))
                    AND (%s::text IS NULL OR s.user_id = %s::text)
                LIMIT 500
                """
                ).format(
                    sql.Identifier(agno_schema(), "agno_sessions"),
                    _archive_table(),
                ),
                (include_archived, owner_user_id, owner_user_id),
            )
            rows = cursor.fetchall()

    return _project_session_rows(rows, include_runs=include_runs)


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
            "archived": bool(row.get("archived_at"))
            or _is_archived_metadata(row.get("metadata")),
            "archived_at": row.get("archived_at"),
        }
        if include_runs:
            session["runs"] = runs if isinstance(runs, list) else []
        sessions.append(session)
    return sessions


def get_session_messages(session_id: str, *, actor: Any | None = None) -> list[dict[str, str]]:
    """从 PostgreSQL 读取指定会话的用户/助手消息列表。"""
    ensure_agno_postgres_tables()
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT user_id, runs FROM {} WHERE session_id = %s").format(
                    sql.Identifier(agno_schema(), "agno_sessions")
                ),
                (session_id,),
            )
            row = cursor.fetchone()

    if not row:
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
