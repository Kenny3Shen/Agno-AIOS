from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg_pool import AsyncConnectionPool

from api.services.postgres_store import app_schema


async def search_cves(
    pool: AsyncConnectionPool[Any],
    query: str,
    source: str | None = None,
    page: int = 1,
    size: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Search CVEs by CVE ID or description."""
    params: dict[str, Any] = {"query": f"%{query}%"}
    if source:
        params["source"] = source

    params["limit"] = size
    params["offset"] = (page - 1) * size

    async with pool.connection() as conn:
        async with conn.cursor() as cursor:
            table = sql.Identifier(app_schema(), "cves")
            where_clause = (
                sql.SQL(
                    "(cve_id ILIKE %(query)s OR description ILIKE %(query)s) "
                    "AND source = %(source)s"
                )
                if source
                else sql.SQL("(cve_id ILIKE %(query)s OR description ILIKE %(query)s)")
            )
            await cursor.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE ").format(table)
                + where_clause,
                params,
            )
            count_result = await cursor.fetchone()
            total = int(count_result["count"]) if count_result else 0

            await cursor.execute(
                sql.SQL(
                    """
                SELECT id, cve_id, description, github_url, source, create_time
                FROM {}
                WHERE {}
                ORDER BY id DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """
                ).format(table, where_clause),
                params,
            )
            return list(await cursor.fetchall()), total
