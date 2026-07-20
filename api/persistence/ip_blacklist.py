"""IP blacklist threat-intel store (control-plane table)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    MetaData,
    Table,
    Text,
    delete,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

IP_BLACKLIST_TABLE = "ip_blacklist"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def ip_blacklist_table() -> Table:
    table = Table(
        IP_BLACKLIST_TABLE,
        _metadata(),
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("indicator", Text, nullable=False),
        Column("indicator_type", Text, nullable=False, server_default="cidr"),
        Column("source", Text, nullable=False),
        Column("list_name", Text, nullable=False, server_default=""),
        Column("description", Text, nullable=False, server_default=""),
        Column("first_seen", DateTime(timezone=True)),
        Column("last_seen", DateTime(timezone=True)),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    Index("idx_ip_blacklist_indicator", table.c.indicator)
    Index("idx_ip_blacklist_source", table.c.source)
    Index(
        "uq_ip_blacklist_indicator_source",
        table.c.indicator,
        table.c.source,
        unique=True,
    )
    return table


_table_once = AsyncOnce()


async def _create_table() -> None:
    await ensure_control_plane_schema_current()


async def ensure_ip_blacklist_table() -> None:
    await _table_once.run(_create_table)


async def search_ip_blacklist_rows(
    *,
    query: str,
    source: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_ip_blacklist_table()
    safe_page = max(1, int(page or 1))
    safe_size = min(200, max(1, int(size or 20)))
    normalized_query = (query or "").strip()
    table = ip_blacklist_table()
    filters = []
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                table.c.indicator.ilike(pattern),
                table.c.description.ilike(pattern),
                table.c.list_name.ilike(pattern),
            )
        )
    if source:
        filters.append(table.c.source == source)

    count_stmt = select(func.count()).select_from(table)
    rows_stmt = select(
        table.c.id,
        table.c.indicator,
        table.c.indicator_type,
        table.c.source,
        table.c.list_name,
        table.c.description,
        table.c.first_seen,
        table.c.last_seen,
        table.c.updated_at,
    )
    if filters:
        count_stmt = count_stmt.where(*filters)
        rows_stmt = rows_stmt.where(*filters)
    rows_stmt = (
        rows_stmt.order_by(desc(table.c.updated_at), desc(table.c.id))
        .limit(safe_size)
        .offset((safe_page - 1) * safe_size)
    )

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = [dict(row) for row in (await conn.execute(rows_stmt)).mappings().all()]
    return rows, total


async def lookup_ip_blacklist(
    *,
    indicator: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Exact indicator match (IP or CIDR string as stored)."""
    await ensure_ip_blacklist_table()
    needle = (indicator or "").strip()
    if not needle:
        return []
    table = ip_blacklist_table()
    stmt = (
        select(
            table.c.id,
            table.c.indicator,
            table.c.indicator_type,
            table.c.source,
            table.c.list_name,
            table.c.description,
            table.c.first_seen,
            table.c.last_seen,
            table.c.updated_at,
        )
        .where(table.c.indicator == needle)
        .order_by(desc(table.c.updated_at))
        .limit(min(100, max(1, int(limit or 20))))
    )
    async with get_async_control_plane_engine().begin() as conn:
        return [dict(row) for row in (await conn.execute(stmt)).mappings().all()]


async def upsert_ip_blacklist_rows(rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    await ensure_ip_blacklist_table()
    now = datetime.now(UTC)
    table = ip_blacklist_table()
    values: list[dict[str, Any]] = []
    for row in rows:
        indicator = str(row.get("indicator") or "").strip()
        source = str(row.get("source") or "").strip()
        if not indicator or not source:
            continue
        values.append(
            {
                "indicator": indicator,
                "indicator_type": str(row.get("indicator_type") or "cidr").strip() or "cidr",
                "source": source,
                "list_name": str(row.get("list_name") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "first_seen": row.get("first_seen") or now,
                "last_seen": row.get("last_seen") or now,
                "updated_at": now,
            }
        )
    if not values:
        return 0
    stmt = insert(table).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.indicator, table.c.source],
        set_={
            "indicator_type": stmt.excluded.indicator_type,
            "list_name": stmt.excluded.list_name,
            "description": stmt.excluded.description,
            "last_seen": stmt.excluded.last_seen,
            "updated_at": now,
        },
    )
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(stmt)
    return max(int(result.rowcount or 0), 0)


async def delete_ip_blacklist_missing_for_source(
    *,
    source: str,
    keep_indicators: Sequence[str],
) -> int:
    """Remove rows for *source* whose indicators are not in *keep_indicators*."""
    source_key = (source or "").strip()
    if not source_key:
        return 0
    await ensure_ip_blacklist_table()
    table = ip_blacklist_table()
    keep = {str(item).strip() for item in keep_indicators if str(item).strip()}
    async with get_async_control_plane_engine().begin() as conn:
        if not keep:
            result = await conn.execute(delete(table).where(table.c.source == source_key))
            return max(int(result.rowcount or 0), 0)
        # Chunk NOT IN for large lists.
        existing = (
            await conn.execute(
                select(table.c.indicator).where(table.c.source == source_key)
            )
        ).scalars().all()
        to_delete = [item for item in existing if item not in keep]
        if not to_delete:
            return 0
        deleted = 0
        chunk = 1_000
        for index in range(0, len(to_delete), chunk):
            part = to_delete[index : index + chunk]
            result = await conn.execute(
                delete(table).where(
                    table.c.source == source_key,
                    table.c.indicator.in_(part),
                )
            )
            deleted += max(int(result.rowcount or 0), 0)
        return deleted
