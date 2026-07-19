from __future__ import annotations

from api.utils.async_once import AsyncOnce

from functools import lru_cache
from typing import Any

from agno.db.postgres import AsyncPostgresDb

from api.config import get_settings
from api.utils.json import JSONDecodeError, loads


def app_schema() -> str:
    return get_settings().agno_app_schema


def agno_schema() -> str:
    return get_settings().agno_db_schema


def mcp_schema() -> str:
    return get_settings().agno_mcp_schema


def knowledge_schema() -> str:
    return get_settings().agno_knowledge_schema


def postgres_sqlalchemy_url() -> str:
    return get_settings().postgres_sqlalchemy_url


def postgres_async_sqlalchemy_url() -> str:
    return get_settings().postgres_async_sqlalchemy_url


@lru_cache(maxsize=1)
def get_async_agno_postgres_db() -> AsyncPostgresDb:
    return AsyncPostgresDb(
        db_url=postgres_async_sqlalchemy_url(),
        db_schema=agno_schema(),
        session_table="agno_sessions",
        memory_table="agno_memories",
        traces_table="agno_traces",
        spans_table="agno_spans",
        versions_table="agno_schema_versions",
    )


@lru_cache(maxsize=1)
def get_async_knowledge_postgres_db() -> AsyncPostgresDb:
    return AsyncPostgresDb(
        db_url=postgres_async_sqlalchemy_url(),
        db_schema=knowledge_schema(),
        knowledge_table=get_settings().agno_postgres_knowledge_table,
        versions_table="agno_schema_versions",
    )


_agno_postgres_tables_once = AsyncOnce()


async def _create_agno_postgres_tables_async() -> None:
    db = get_async_agno_postgres_db()
    get_table = getattr(db, "_get_table")
    for table_type in ("versions", "sessions", "memories", "traces", "spans"):
        await get_table(table_type=table_type, create_table_if_not_found=True)


async def ensure_agno_postgres_tables_async() -> None:
    await _agno_postgres_tables_once.run(_create_agno_postgres_tables_async)


def coerce_json_value(value: Any) -> Any:
    """Unwrap nested JSON strings up to 3 levels; leave plain text unchanged."""
    current = value
    for _ in range(3):
        if not isinstance(current, str):
            return current
        try:
            current = loads(current)
        except (JSONDecodeError, TypeError, ValueError):
            return current
    return current


async def ensure_app_tables_async() -> None:
    """Compatibility name for the Alembic-only control-plane readiness check.

    New deployments must execute ``alembic upgrade head`` outside the API
    process.  Retaining this narrow wrapper avoids a disruptive import churn
    while guaranteeing that the old startup path cannot perform DDL.
    """
    from api.persistence.migrations import ensure_control_plane_schema_current

    await ensure_control_plane_schema_current()
