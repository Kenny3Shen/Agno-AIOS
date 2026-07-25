#!/usr/bin/env python3
"""IP blacklist threat-intel lookup against the control-plane table."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

psycopg: Any | None = None
sql: Any | None = None

try:
    import psycopg as _psycopg
    from psycopg import sql as _sql
except Exception:  # pragma: no cover - optional runtime dependency guard
    pass
else:
    psycopg = _psycopg
    sql = _sql


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists() and (parent / "api").is_dir():
            return parent
    return Path.cwd()


ROOT = _repo_root()
load_dotenv(ROOT / ".env", override=True)

_IP_RE = re.compile(
    r"^(?:(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?|[0-9a-fA-F:]+(?:/\d{1,3})?)$"
)


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


def _dsn() -> str:
    url = _env("POSTGRES_URL") or _env("DATABASE_URL")
    if url:
        return url
    host = _env("POSTGRES_HOST", "127.0.0.1")
    port = _env("POSTGRES_PORT", "5432")
    user = _env("POSTGRES_USER", "postgres")
    password = _env("POSTGRES_PASSWORD", "")
    db = _env("POSTGRES_DB", "tais")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _schema() -> str:
    return _env("AGNO_DB_SCHEMA") or _env("TAIS_AGNO_APP_SCHEMA") or "app"


async def search_async(query: str, limit: int) -> dict[str, Any]:
    if psycopg is None or sql is None:
        return {
            "query": query,
            "matched_total": 0,
            "hits": [],
            "error": "psycopg not available",
        }
    q = (query or "").strip()
    if not q:
        return {"query": q, "matched_total": 0, "hits": [], "error": "empty query"}

    schema = _schema()
    table = sql.Identifier(schema, "ip_blacklist")
    # Exact first for IP/CIDR-shaped input; otherwise ILIKE.
    exact = bool(_IP_RE.match(q.split()[0]))
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.cursor() as cur:
            if exact:
                await cur.execute(
                    sql.SQL(
                        """
                    SELECT indicator, indicator_type, source, list_name, description,
                           last_seen::text, updated_at::text
                    FROM {}
                    WHERE indicator = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """
                    ).format(table),
                    (q.split()[0], limit),
                )
            else:
                pattern = f"%{q}%"
                await cur.execute(
                    sql.SQL(
                        """
                    SELECT indicator, indicator_type, source, list_name, description,
                           last_seen::text, updated_at::text
                    FROM {}
                    WHERE indicator ILIKE %s
                       OR description ILIKE %s
                       OR list_name ILIKE %s
                       OR source ILIKE %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """
                    ).format(table),
                    (pattern, pattern, pattern, pattern, limit),
                )
            rows = await cur.fetchall()
            await cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(table)
                + sql.SQL(
                    " WHERE indicator = %s"
                    if exact
                    else " WHERE indicator ILIKE %s OR description ILIKE %s OR list_name ILIKE %s OR source ILIKE %s"
                ),
                (q.split()[0],) if exact else (pattern, pattern, pattern, pattern),
            )
            total_row = await cur.fetchone()
            total = int(total_row[0]) if total_row else 0

    hits = [
        {
            "indicator": r[0],
            "indicator_type": r[1],
            "source": r[2],
            "list_name": r[3],
            "description": r[4],
            "last_seen": r[5],
            "updated_at": r[6],
        }
        for r in rows
    ]
    return {
        "query": q,
        "matched_total": total,
        "hits": hits,
        "verdict": "命中" if hits else "未命中",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="IP blacklist intel lookup")
    parser.add_argument("--query", required=True, help="IP, CIDR, or keyword")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    result = asyncio.run(search_async(args.query, max(1, min(args.limit, 100))))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
