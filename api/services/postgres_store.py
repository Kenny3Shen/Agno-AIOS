from __future__ import annotations

import json
import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator, cast
from urllib.parse import quote_plus

import psycopg
from agno.db.postgres import PostgresDb
from dotenv import load_dotenv
from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

load_dotenv(override=True)


def postgres_host() -> str:
    return os.getenv("POSTGRES_HOST") or os.getenv("AGNO_POSTGRES_HOST", "localhost")


def postgres_port() -> int:
    raw = os.getenv("POSTGRES_PORT") or os.getenv("AGNO_POSTGRES_PORT", "5432")
    try:
        return int(raw)
    except ValueError:
        return 5432


def postgres_user() -> str:
    return os.getenv("POSTGRES_USER") or os.getenv("AGNO_POSTGRES_USER", "agno_aios")


def postgres_password() -> str:
    return os.getenv("POSTGRES_PASSWORD") or os.getenv("AGNO_POSTGRES_PASSWORD", "agno_aios")


def postgres_database() -> str:
    return os.getenv("POSTGRES_DB") or os.getenv("AGNO_POSTGRES_DB", "agno_aios")


def app_schema() -> str:
    return os.getenv("AGNO_APP_SCHEMA", "app")


def agno_schema() -> str:
    return os.getenv("AGNO_DB_SCHEMA", "agno")


def mcp_schema() -> str:
    return os.getenv("AGNO_MCP_SCHEMA", "mcp")


def knowledge_schema() -> str:
    return os.getenv("AGNO_KNOWLEDGE_SCHEMA", "knowledge")


def postgres_dsn() -> str:
    explicit_url = os.getenv("AGNO_POSTGRES_URL") or os.getenv("POSTGRES_URL")
    if explicit_url:
        return explicit_url
    return (
        f"postgresql://{quote_plus(postgres_user())}:{quote_plus(postgres_password())}"
        f"@{postgres_host()}:{postgres_port()}/{quote_plus(postgres_database())}"
    )


def postgres_sqlalchemy_url() -> str:
    explicit_url = os.getenv("AGNO_POSTGRES_SQLALCHEMY_URL")
    if explicit_url:
        return explicit_url
    return postgres_dsn().replace("postgresql://", "postgresql+psycopg://", 1)


def postgres_label(schema: str, table_name: str) -> str:
    return f"postgres:{postgres_database()}.{schema}.{table_name}"


@contextmanager
def postgres_connect() -> Iterator[Connection[dict[str, Any]]]:
    conn = cast(
        Connection[dict[str, Any]],
        psycopg.connect(
            postgres_dsn(),
            row_factory=cast(Any, dict_row),
            autocommit=True,
        ),
    )
    try:
        yield conn
    finally:
        conn.close()


_async_pool: AsyncConnectionPool[Any] | None = None


async def get_postgres_pool() -> AsyncConnectionPool[Any]:
    global _async_pool
    if _async_pool is None:
        _async_pool = AsyncConnectionPool(
            conninfo=postgres_dsn(),
            kwargs={"row_factory": cast(Any, dict_row), "autocommit": True},
            open=False,
        )
        await _async_pool.open()
    return _async_pool


async def close_postgres_pool() -> None:
    global _async_pool
    if _async_pool is not None:
        await _async_pool.close()
        _async_pool = None


@lru_cache(maxsize=1)
def get_agno_postgres_db() -> PostgresDb:
    return PostgresDb(
        db_url=postgres_sqlalchemy_url(),
        db_schema=agno_schema(),
        session_table="agno_sessions",
        memory_table="agno_memories",
        traces_table="agno_traces",
        spans_table="agno_spans",
        versions_table="agno_schema_versions",
    )


@lru_cache(maxsize=1)
def get_knowledge_postgres_db() -> PostgresDb:
    return PostgresDb(
        db_url=postgres_sqlalchemy_url(),
        db_schema=knowledge_schema(),
        knowledge_table=os.getenv("AGNO_POSTGRES_KNOWLEDGE_TABLE", "agno_knowledge"),
        versions_table="agno_schema_versions",
    )


def ensure_agno_postgres_tables() -> None:
    db = get_agno_postgres_db()
    get_table = getattr(db, "_get_table")
    for table_type in ("versions", "sessions", "memories", "traces", "spans"):
        get_table(table_type=table_type, create_table_if_not_found=True)


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


def ensure_app_tables() -> None:
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            for schema in (app_schema(), agno_schema(), mcp_schema(), knowledge_schema()):
                cursor.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        sql.Identifier(schema)
                    )
                )
            cves_table = sql.Identifier(app_schema(), "cves")
            cursor.execute(
                sql.SQL(
                    """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    cve_id TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    github_url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    create_time TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_cves_cve_url UNIQUE (cve_id, github_url)
                )
                """
                ).format(cves_table)
            )
            cursor.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS idx_cves_cve_id ON {} (cve_id)"
                ).format(cves_table)
            )
            cursor.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS idx_cves_source ON {} (source)"
                ).format(cves_table)
            )
            cursor.execute(
                sql.SQL(
                    """
                CREATE INDEX IF NOT EXISTS idx_cves_search
                ON {}
                USING gin (to_tsvector('simple', cve_id || ' ' || coalesce(description, '')))
                """
                ).format(cves_table)
            )
