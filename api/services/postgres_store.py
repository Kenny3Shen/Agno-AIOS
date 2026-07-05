from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from agno.db.postgres import AsyncPostgresDb

from api.config import get_settings


def postgres_host() -> str:
    return get_settings().postgres_host


def postgres_port() -> int:
    return get_settings().postgres_port


def postgres_user() -> str:
    return get_settings().postgres_user


def postgres_password() -> str:
    return get_settings().postgres_password.get_secret_value()


def postgres_database() -> str:
    return get_settings().postgres_db


def app_schema() -> str:
    return get_settings().agno_app_schema


def agno_schema() -> str:
    return get_settings().agno_db_schema


def mcp_schema() -> str:
    return get_settings().agno_mcp_schema


def knowledge_schema() -> str:
    return get_settings().agno_knowledge_schema


def postgres_dsn() -> str:
    return get_settings().postgres_dsn


def postgres_sqlalchemy_url() -> str:
    return get_settings().postgres_sqlalchemy_url


def postgres_async_sqlalchemy_url() -> str:
    return get_settings().postgres_async_sqlalchemy_url


def postgres_label(schema: str, table_name: str) -> str:
    return f"postgres:{postgres_database()}.{schema}.{table_name}"


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


async def ensure_agno_postgres_tables_async() -> None:
    db = get_async_agno_postgres_db()
    get_table = getattr(db, "_get_table")
    for table_type in ("versions", "sessions", "memories", "traces", "spans"):
        await get_table(table_type=table_type, create_table_if_not_found=True)


def coerce_json_value(value: Any) -> Any:
    current = value
    for _ in range(3):
        if not isinstance(current, str):
            return current
        try:
            current = json.loads(current)
        except Exception:
            return current
    return current


async def ensure_app_tables_async() -> None:
    from sqlalchemy import text
    from sqlalchemy.schema import CreateSchema

    from api.mcp.config import init_mcp_postgres_tables
    from api.persistence.audit_logs import ensure_audit_logs_table_async
    from api.persistence.cves import ensure_cves_table
    from api.persistence.database import get_async_control_plane_engine

    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        for schema in (app_schema(), agno_schema(), mcp_schema(), knowledge_schema()):
            await conn.execute(CreateSchema(schema, if_not_exists=True))

    await ensure_cves_table()
    await ensure_audit_logs_table_async()
    await init_mcp_postgres_tables()
