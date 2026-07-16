"""Shared Trace row lookups used by list/overview projections."""

from __future__ import annotations

from typing import Any

from api.services.postgres_store import get_async_agno_postgres_db


async def batch_traces_by_run_ids(run_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Load one trace row per run_id in a single traces-table query.

    Prefer the newest ``start_time`` when a run has multiple traces. Returns
    plain dict rows suitable for list/overview projection (no Agno models).
    """
    safe_ids = [str(run_id).strip() for run_id in run_ids if str(run_id or "").strip()]
    if not safe_ids:
        return {}

    from sqlalchemy import select

    db = get_async_agno_postgres_db()
    table = await db._get_table(table_type="traces")
    if table is None:
        return {}

    # DISTINCT ON (run_id): one row per run, newest start first.
    stmt = (
        select(table)
        .where(table.c.run_id.in_(safe_ids))
        .distinct(table.c.run_id)
        .order_by(table.c.run_id, table.c.start_time.desc())
    )

    by_run: dict[str, dict[str, Any]] = {}
    async with db.async_session_factory() as session:
        result = await session.execute(stmt)
        for row in result.mappings():
            data = dict(row)
            run_key = str(data.get("run_id") or "").strip()
            if not run_key:
                continue
            by_run[run_key] = data
    return by_run
