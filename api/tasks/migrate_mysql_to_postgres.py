from __future__ import annotations

import json
from typing import Any

from psycopg import sql
from sqlalchemy.dialects import postgresql

from api.mcp.config import (
    HIAGENT_CACHE_TABLE,
    MCP_TOKENS_TABLE,
    init_mcp_postgres_tables,
    upsert_hiagent_exec_record,
    upsert_token_record,
)
from api.services.mysql_store import mysql_connect
from api.services.postgres_store import (
    agno_schema,
    app_schema,
    coerce_json_value,
    ensure_agno_postgres_tables,
    ensure_app_tables,
    get_agno_postgres_db,
    mcp_schema,
    postgres_connect,
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


def _mysql_table_exists(table_name: str) -> bool:
    try:
        conn = mysql_connect()
    except Exception:
        raise
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE %s", (table_name,))
            return cursor.fetchone() is not None
    finally:
        conn.close()


def _mysql_rows(table_name: str) -> list[dict[str, Any]]:
    if not _mysql_table_exists(table_name):
        return []
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_name}")
            return list(cursor.fetchall())
    finally:
        conn.close()


def _postgres_count(schema: str, table_name: str) -> int:
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {}").format(
                    sql.Identifier(schema, table_name)
                )
            )
            row = cursor.fetchone()
            return int(row["count"]) if row else 0


def _decode_agno_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for column in AGNO_JSON_COLUMNS.get(table_name, set()):
        if column in decoded:
            decoded[column] = coerce_json_value(decoded[column])
    if "duration_ms" in decoded and decoded["duration_ms"] is not None:
        decoded["duration_ms"] = int(round(float(decoded["duration_ms"])))
    return decoded


def migrate_cves() -> dict[str, Any]:
    ensure_app_tables()
    rows = _mysql_rows("cves")
    migrated = 0
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cves_table = sql.Identifier(app_schema(), "cves")
            for row in rows:
                cursor.execute(
                    sql.SQL(
                        """
                    INSERT INTO {}
                        (id, cve_id, description, github_url, source, create_time)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cve_id, github_url) DO UPDATE SET
                        description = EXCLUDED.description,
                        source = EXCLUDED.source,
                        create_time = EXCLUDED.create_time,
                        updated_at = now()
                    """,
                    ).format(cves_table),
                    (
                        row.get("id"),
                        row.get("cve_id"),
                        row.get("description") or "",
                        row.get("github_url"),
                        row.get("source"),
                        row.get("create_time"),
                    ),
                )
                migrated += 1
            cursor.execute(
                sql.SQL(
                    """
                SELECT setval(
                    pg_get_serial_sequence({}, 'id'),
                    COALESCE((SELECT MAX(id) FROM {}), 1),
                    true
                )
                """
                ).format(sql.Literal(f"{app_schema()}.cves"), cves_table)
            )
    return {
        "source": len(rows),
        "migrated": migrated,
        "target": _postgres_count(app_schema(), "cves"),
    }


def _ensure_agno_table(table_type: str):
    db = get_agno_postgres_db()
    get_table = getattr(db, "_get_table")
    return get_table(table_type=table_type, create_table_if_not_found=True)


def _upsert_agno_rows(
    table_name: str,
    table_type: str,
    pk_columns: list[str],
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    db = get_agno_postgres_db()
    table = _ensure_agno_table(table_type)
    count = 0
    with db.Session() as session, session.begin():
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
            session.execute(stmt)
            count += 1
    return count


def migrate_agno_tables() -> dict[str, Any]:
    ensure_agno_postgres_tables()
    summary: dict[str, Any] = {}
    for table_name, (table_type, pk_columns) in AGNO_TABLES.items():
        rows = _mysql_rows(table_name)
        migrated = _upsert_agno_rows(table_name, table_type, pk_columns, rows)
        summary[table_name] = {
            "source": len(rows),
            "migrated": migrated,
            "target": _postgres_count(agno_schema(), table_name),
        }
    return summary


def migrate_mcp_tables() -> dict[str, Any]:
    init_mcp_postgres_tables()
    token_rows = _mysql_rows(MCP_TOKENS_TABLE)
    for row in token_rows:
        upsert_token_record(row)

    hiagent_rows = _mysql_rows(HIAGENT_CACHE_TABLE)
    for row in hiagent_rows:
        upsert_hiagent_exec_record(row)

    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                SELECT setval(
                    pg_get_serial_sequence({}, 'id'),
                    COALESCE((SELECT MAX(id) FROM {}), 1),
                    true
                )
                """
                ).format(
                    sql.Literal(f"{mcp_schema()}.{MCP_TOKENS_TABLE}"),
                    sql.Identifier(mcp_schema(), MCP_TOKENS_TABLE),
                )
            )

    return {
        MCP_TOKENS_TABLE: {
            "source": len(token_rows),
            "migrated": len(token_rows),
            "target": _postgres_count(mcp_schema(), MCP_TOKENS_TABLE),
        },
        HIAGENT_CACHE_TABLE: {
            "source": len(hiagent_rows),
            "migrated": len(hiagent_rows),
            "target": _postgres_count(mcp_schema(), HIAGENT_CACHE_TABLE),
        },
    }


def main() -> dict[str, Any]:
    return {
        "cves": migrate_cves(),
        "agno": migrate_agno_tables(),
        "mcp": migrate_mcp_tables(),
    }


def run() -> None:
    print(json.dumps(main(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    run()
