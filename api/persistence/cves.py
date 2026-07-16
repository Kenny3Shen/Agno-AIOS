from __future__ import annotations

from api.utils.async_once import AsyncOnce

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
    UniqueConstraint,
    delete,
    desc,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

CVES_TABLE = "cves"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def cves_table() -> Table:
    table = Table(
        CVES_TABLE,
        _metadata(),
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("cve_id", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("github_url", Text, nullable=False),
        Column("source", Text, nullable=False),
        Column("create_time", DateTime(timezone=True)),
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
        UniqueConstraint("cve_id", "github_url", name="uq_cves_cve_url"),
    )
    Index("idx_cves_cve_id", table.c.cve_id)
    Index("idx_cves_source", table.c.source)
    Index(
        "idx_cves_search",
        func.to_tsvector(
            "simple",
            table.c.cve_id.concat(literal(" ")).concat(
                func.coalesce(table.c.description, "")
            ),
        ),
        postgresql_using="gin",
    )
    return table


_cves_table_once = AsyncOnce()


async def _create_cves_table() -> None:
    table = cves_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_app_schema(), if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)
        for index in table.indexes:
            await conn.run_sync(index.create, checkfirst=True)


async def ensure_cves_table() -> None:
    await _cves_table_once.run(_create_cves_table)


async def search_cve_rows(
    *,
    query: str,
    source: str | None = None,
    page: int = 1,
    size: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_cves_table()
    safe_page = max(1, int(page or 1))
    safe_size = min(200, max(1, int(size or 10)))
    normalized_query = query.strip()
    table = cves_table()
    filters = []
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                table.c.cve_id.ilike(pattern),
                table.c.description.ilike(pattern),
            )
        )
    if source:
        filters.append(table.c.source == source)

    count_stmt = select(func.count()).select_from(table).where(*filters)
    rows_stmt = (
        select(
            table.c.id,
            table.c.cve_id,
            table.c.description,
            table.c.github_url,
            table.c.source,
            table.c.create_time,
        )
        .where(*filters)
        .order_by(desc(table.c.created_at), desc(table.c.id))
        .limit(safe_size)
        .offset((safe_page - 1) * safe_size)
    )

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = [dict(row) for row in (await conn.execute(rows_stmt)).mappings().all()]
    return rows, total


async def insert_new_cve_rows(rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    await ensure_cves_table()
    now = datetime.now(UTC)
    table = cves_table()
    values = [
        {
            "cve_id": row.get("cve_id"),
            "description": row.get("description") or "",
            "github_url": row.get("github_url") or "",
            "source": row.get("source") or "",
            "create_time": row.get("create_time") or now,
        }
        for row in rows
    ]
    stmt = (
        insert(table)
        .values(values)
        .on_conflict_do_nothing(index_elements=[table.c.cve_id, table.c.github_url])
    )
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(stmt)
    return max(int(result.rowcount or 0), 0)


async def delete_cve_rows(rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    await ensure_cves_table()
    table = cves_table()
    deleted = 0
    async with get_async_control_plane_engine().begin() as conn:
        for row in rows:
            result = await conn.execute(
                delete(table).where(
                    table.c.cve_id == row.get("cve_id"),
                    table.c.github_url == row.get("github_url"),
                )
            )
            deleted += max(int(result.rowcount or 0), 0)
    return deleted


async def count_cve_rows() -> int:
    await ensure_cves_table()
    table = cves_table()
    async with get_async_control_plane_engine().begin() as conn:
        return int(
            (await conn.execute(select(func.count()).select_from(table))).scalar_one()
        )

