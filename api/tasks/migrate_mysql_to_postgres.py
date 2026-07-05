from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy.dialects import postgresql

from api.mcp.config import (
    MCP_TOKENS_TABLE,
    init_mcp_postgres_tables,
    upsert_token_record,
)
from api.persistence.cves import count_cve_rows, reset_cve_id_sequence, upsert_cve_row
from api.persistence.mcp import reset_token_id_sequence
from api.services.mysql_store import mysql_connect_async
from api.services.postgres_store import (
    agno_schema,
    coerce_json_value,
    ensure_agno_postgres_tables_async,
    get_async_agno_postgres_db,
    get_postgres_pool,
    mcp_schema,
)

AGNO_JSON_COLUMNS = {
    "agno_sessions": {
        "session_data",
        "agent_data",
        "team_data",
        "workflow_data",
        "metadata",
        "runs",
        "summary",
    },
    "agno_memories": {"memory", "topics"},
    "agno_spans": {"attributes"},
}

AGNO_TABLES = {
    "agno_schema_versions": ("versions", ["table_name"]),
    "agno_sessions": ("sessions", ["session_id"]),
    "agno_memories": ("memories", ["memory_id"]),
    "agno_traces": ("traces", ["trace_id"]),
    "agno_spans": ("spans", ["span_id"]),
}


async def _mysql_table_exists(table_name: str) -> bool:
    try:
        conn = await mysql_connect_async()
    except Exception:
        raise
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SHOW TABLES LIKE %s", (table_name,))
            return await cursor.fetchone() is not None
    finally:
        conn.close()
        ensure_closed = getattr(conn, "ensure_closed", None)
        if callable(ensure_closed):
            await ensure_closed()


async def _mysql_rows(table_name: str) -> list[dict[str, Any]]:
    if not await _mysql_table_exists(table_name):
        return []
    conn = await mysql_connect_async()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM {table_name}")
            return list(await cursor.fetchall())
    finally:
        conn.close()
        ensure_closed = getattr(conn, "ensure_closed", None)
        if callable(ensure_closed):
            await ensure_closed()


async def _postgres_count(schema: str, table_name: str) -> int:
    from psycopg import sql

    pool = await get_postgres_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {}").format(
                    sql.Identifier(schema, table_name)
                )
            )
            row = await cursor.fetchone()
            return int(row["count"]) if row else 0


def _decode_agno_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for column in AGNO_JSON_COLUMNS.get(table_name, set()):
        if column in decoded:
            decoded[column] = coerce_json_value(decoded[column])
    if "duration_ms" in decoded and decoded["duration_ms"] is not None:
        decoded["duration_ms"] = int(round(float(decoded["duration_ms"])))
    return decoded


async def migrate_cves() -> dict[str, Any]:
    rows = await _mysql_rows("cves")
    migrated = 0
    for row in rows:
        await upsert_cve_row(row)
        migrated += 1
    await reset_cve_id_sequence()
    return {
        "source": len(rows),
        "migrated": migrated,
        "target": await count_cve_rows(),
    }


async def _ensure_agno_table(table_type: str):
    db = get_async_agno_postgres_db()
    get_table = getattr(db, "_get_table")
    return await get_table(table_type=table_type, create_table_if_not_found=True)


async def _upsert_agno_rows(
    table_name: str,
    table_type: str,
    pk_columns: list[str],
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    db = get_async_agno_postgres_db()
    table = await _ensure_agno_table(table_type)
    count = 0
    async with db.db_engine.begin() as conn:
        for row in rows:
            decoded = _decode_agno_row(table_name, row)
            stmt = postgresql.insert(table).values(decoded)
            update_values = {
                column: stmt.excluded[column]
                for column in decoded
                if column not in pk_columns
            }
            if update_values:
                stmt = stmt.on_conflict_do_update(
                    index_elements=pk_columns,
                    set_=update_values,
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)
            await conn.execute(stmt)
            count += 1
    return count


async def migrate_agno_tables() -> dict[str, Any]:
    await ensure_agno_postgres_tables_async()
    summary: dict[str, Any] = {}
    for table_name, (table_type, pk_columns) in AGNO_TABLES.items():
        rows = await _mysql_rows(table_name)
        migrated = await _upsert_agno_rows(table_name, table_type, pk_columns, rows)
        summary[table_name] = {
            "source": len(rows),
            "migrated": migrated,
            "target": await _postgres_count(agno_schema(), table_name),
        }
    return summary


async def migrate_mcp_tables() -> dict[str, Any]:
    await init_mcp_postgres_tables()
    token_rows = await _mysql_rows(MCP_TOKENS_TABLE)
    for row in token_rows:
        await upsert_token_record(row)

    await reset_token_id_sequence()

    return {
        MCP_TOKENS_TABLE: {
            "source": len(token_rows),
            "migrated": len(token_rows),
            "target": await _postgres_count(mcp_schema(), MCP_TOKENS_TABLE),
        },
    }


async def main() -> dict[str, Any]:
    return {
        "cves": await migrate_cves(),
        "agno": await migrate_agno_tables(),
        "mcp": await migrate_mcp_tables(),
    }


def run() -> None:
    print(json.dumps(asyncio.run(main()), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    run()
