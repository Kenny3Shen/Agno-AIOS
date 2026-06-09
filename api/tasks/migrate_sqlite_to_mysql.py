from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy.dialects import mysql

from api.mcp.config import (
    HIAGENT_CACHE_TABLE,
    MCP_TOKENS_TABLE,
    init_mcp_mysql_tables,
    upsert_hiagent_exec_record,
    upsert_token_record,
)
from api.services.mysql_store import coerce_json_value, get_agno_mysql_db, mysql_connect

LEGACY_SESSION_DB = Path(os.getenv("AGNO_LEGACY_SESSION_DB", "security_agent.db"))
LEGACY_TRACE_DB = Path(os.getenv("AGNO_LEGACY_TRACE_DB", "tmp/traces.db"))
LEGACY_MCP_TOKENS_DB = Path(
    os.getenv("AGNO_LEGACY_MCP_TOKENS_DB", "tmp/mcp/mcp_tokens.db")
)
LEGACY_HIAGENT_CACHE_DB = Path(
    os.getenv("AGNO_LEGACY_HIAGENT_CACHE_DB", "tmp/mcp/hiagent_cache.db")
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


def _sqlite_table_exists(db_path: Path, table_name: str) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _sqlite_rows(db_path: Path, table_name: str) -> list[dict[str, Any]]:
    if not _sqlite_table_exists(db_path, table_name):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table_name}")]
    finally:
        conn.close()


def _decode_agno_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for column in AGNO_JSON_COLUMNS.get(table_name, set()):
        if column in decoded:
            decoded[column] = coerce_json_value(decoded[column])
    if "duration_ms" in decoded and decoded["duration_ms"] is not None:
        decoded["duration_ms"] = int(round(float(decoded["duration_ms"])))
    return decoded


def _ensure_agno_table(table_type: str):
    db = get_agno_mysql_db()
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
    db = get_agno_mysql_db()
    table = _ensure_agno_table(table_type)
    count = 0
    with db.Session() as session, session.begin():
        for row in rows:
            decoded = _decode_agno_row(table_name, row)
            stmt = mysql.insert(table).values(decoded)
            update_values = {
                column: stmt.inserted[column]
                for column in decoded
                if column not in pk_columns
            }
            if update_values:
                stmt = stmt.on_duplicate_key_update(**update_values)
            session.execute(stmt)
            count += 1
    return count


def _mysql_count(table_name: str) -> int:
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
            return int(cursor.fetchone()["count"])
    finally:
        conn.close()


def migrate_agno_sqlite() -> dict[str, Any]:
    summary: dict[str, Any] = {}
    sources = {
        LEGACY_SESSION_DB: ["agno_schema_versions", "agno_sessions", "agno_memories"],
        LEGACY_TRACE_DB: ["agno_schema_versions", "agno_traces", "agno_spans"],
    }
    for db_path, table_names in sources.items():
        for table_name in table_names:
            table_type, pk_columns = AGNO_TABLES[table_name]
            rows = _sqlite_rows(db_path, table_name)
            migrated = _upsert_agno_rows(table_name, table_type, pk_columns, rows)
            key = f"{db_path}:{table_name}"
            summary[key] = {
                "source": len(rows),
                "migrated": migrated,
                "target": _mysql_count(table_name),
            }
    return summary


def migrate_mcp_sqlite() -> dict[str, Any]:
    init_mcp_mysql_tables()
    token_rows = _sqlite_rows(LEGACY_MCP_TOKENS_DB, "tokens")
    for row in token_rows:
        upsert_token_record(row)

    hiagent_rows = _sqlite_rows(LEGACY_HIAGENT_CACHE_DB, "hiagent_exec_cache")
    for row in hiagent_rows:
        upsert_hiagent_exec_record(row)

    return {
        "tokens": {
            "source": len(token_rows),
            "migrated": len(token_rows),
            "target": _mysql_count(MCP_TOKENS_TABLE),
        },
        "hiagent_exec_cache": {
            "source": len(hiagent_rows),
            "migrated": len(hiagent_rows),
            "target": _mysql_count(HIAGENT_CACHE_TABLE),
        },
    }


def main() -> dict[str, Any]:
    return {
        "agno": migrate_agno_sqlite(),
        "mcp": migrate_mcp_sqlite(),
    }


def run() -> None:
    print(json.dumps(main(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
