"""Persistence for security-news articles collected from configured source sites."""

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
    UniqueConstraint,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

COLLECT_ARTICLES_TABLE = "collect_articles"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def collect_articles_table() -> Table:
    table = Table(
        COLLECT_ARTICLES_TABLE,
        _metadata(),
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("url", Text, nullable=False),
        Column("source_domain", Text, nullable=False, server_default=""),
        Column("title", Text, nullable=False, server_default=""),
        Column("markdown", Text, nullable=False, server_default=""),
        Column("summary", Text, nullable=False, server_default=""),
        Column("status", Text, nullable=False, server_default="ok"),
        Column("error_message", Text, nullable=False, server_default=""),
        Column("fetched_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        UniqueConstraint("url", name="uq_collect_articles_url"),
    )
    Index("idx_collect_articles_domain", table.c.source_domain)
    Index("idx_collect_articles_fetched", table.c.fetched_at.desc())
    Index("idx_collect_articles_status", table.c.status)
    return table


async def ensure_collect_articles_table() -> None:
    table = collect_articles_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_app_schema(), if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)
        for index in table.indexes:
            await conn.run_sync(index.create, checkfirst=True)


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key in ("fetched_at", "created_at", "updated_at"):
        value = data.get(key)
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


async def search_collect_articles(
    *,
    query: str = "",
    source_domain: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_collect_articles_table()
    safe_page = max(1, int(page or 1))
    safe_size = min(100, max(1, int(size or 20)))
    table = collect_articles_table()
    filters = [table.c.status == "ok"]
    normalized = (query or "").strip()
    if normalized:
        pattern = f"%{normalized}%"
        filters.append(
            or_(
                table.c.title.ilike(pattern),
                table.c.summary.ilike(pattern),
                table.c.url.ilike(pattern),
                table.c.markdown.ilike(pattern),
            )
        )
    if source_domain:
        filters.append(table.c.source_domain == source_domain.strip())

    count_stmt = select(func.count()).select_from(table).where(*filters)
    rows_stmt = (
        select(
            table.c.id,
            table.c.url,
            table.c.source_domain,
            table.c.title,
            table.c.markdown,
            table.c.summary,
            table.c.status,
            table.c.error_message,
            table.c.fetched_at,
            table.c.created_at,
            table.c.updated_at,
        )
        .where(*filters)
        .order_by(desc(table.c.fetched_at), desc(table.c.id))
        .limit(safe_size)
        .offset((safe_page - 1) * safe_size)
    )

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = [_row_to_dict(row) for row in (await conn.execute(rows_stmt)).mappings().all()]
    return rows, total


async def get_collect_article(article_id: int) -> dict[str, Any] | None:
    await ensure_collect_articles_table()
    table = collect_articles_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                select(table).where(table.c.id == int(article_id)).limit(1)
            )
        ).mappings().first()
    return _row_to_dict(row) if row else None


async def list_collect_source_domains() -> list[str]:
    await ensure_collect_articles_table()
    table = collect_articles_table()
    stmt = (
        select(table.c.source_domain)
        .where(table.c.status == "ok", table.c.source_domain != "")
        .group_by(table.c.source_domain)
        .order_by(table.c.source_domain)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).scalars().all()
    return [str(item) for item in rows if item]


async def upsert_collect_article(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_collect_articles_table()
    table = collect_articles_table()
    now = datetime.now(UTC)
    url = str(record.get("url") or "").strip()
    values = {
        "url": url,
        "source_domain": str(record.get("source_domain") or ""),
        "title": str(record.get("title") or "")[:500],
        "markdown": str(record.get("markdown") or ""),
        "summary": str(record.get("summary") or "")[:1000],
        "status": str(record.get("status") or "ok"),
        "error_message": str(record.get("error_message") or "")[:2000],
        "fetched_at": record.get("fetched_at") or now,
        "updated_at": now,
    }
    stmt = (
        insert(table)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[table.c.url],
            set_={
                "source_domain": values["source_domain"],
                "title": values["title"],
                "markdown": values["markdown"],
                "summary": values["summary"],
                "status": values["status"],
                "error_message": values["error_message"],
                "fetched_at": values["fetched_at"],
                "updated_at": now,
            },
        )
        .returning(
            table.c.id,
            table.c.url,
            table.c.source_domain,
            table.c.title,
            table.c.markdown,
            table.c.summary,
            table.c.status,
            table.c.error_message,
            table.c.fetched_at,
            table.c.created_at,
            table.c.updated_at,
        )
    )
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().one()
    return _row_to_dict(row)


async def bulk_upsert_collect_articles(records: Sequence[dict[str, Any]]) -> int:
    if not records:
        return 0
    count = 0
    for record in records:
        await upsert_collect_article(record)
        count += 1
    return count


async def count_collect_articles(*, status: str | None = "ok") -> int:
    await ensure_collect_articles_table()
    table = collect_articles_table()
    stmt = select(func.count()).select_from(table)
    if status:
        stmt = stmt.where(table.c.status == status)
    async with get_async_control_plane_engine().begin() as conn:
        return int((await conn.execute(stmt)).scalar_one())
