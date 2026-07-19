"""Persistence for security-news articles collected from configured source sites."""

from __future__ import annotations

from api.utils.async_once import AsyncOnce

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    case,
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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, insert
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
        Column(
            "cve_ids",
            ARRAY(Text),
            nullable=False,
            server_default=text("'{}'::text[]"),
        ),
        Column("status", Text, nullable=False, server_default="ok"),
        Column("error_message", Text, nullable=False, server_default=""),
        Column(
            "fetched_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
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
        UniqueConstraint("url", name="uq_collect_articles_url"),
    )
    Index("idx_collect_articles_domain", table.c.source_domain)
    Index("idx_collect_articles_fetched", table.c.fetched_at.desc())
    Index("idx_collect_articles_status", table.c.status)
    return table


_collect_articles_table_once = AsyncOnce()


async def _create_collect_articles_table() -> None:
    table = collect_articles_table()
    schema = _app_schema()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(schema, if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)
        # ``Table.create(checkfirst=True)`` does not evolve an already-created
        # table. Keep this explicit migration beside the table declaration so
        # existing deployments receive persisted CVE tags too.
        escaped_schema = schema.replace('"', '""')
        await conn.execute(
            text(
                f'ALTER TABLE "{escaped_schema}"."{COLLECT_ARTICLES_TABLE}" '
                "ADD COLUMN IF NOT EXISTS cve_ids TEXT[] "
                "NOT NULL DEFAULT '{}'::text[]"
            )
        )
        for index in table.indexes:
            await conn.run_sync(index.create, checkfirst=True)


async def ensure_collect_articles_table() -> None:
    await _collect_articles_table_once.run(_create_collect_articles_table)


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["cve_ids"] = _normalize_cve_ids(data.get("cve_ids"))
    for key in ("fetched_at", "created_at", "updated_at"):
        value = data.get(key)
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


def _normalize_cve_ids(value: Any) -> list[str]:
    """Return a stable, de-duplicated list suitable for PostgreSQL TEXT[]."""
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        cve_id = str(item or "").strip().upper()
        if not cve_id or cve_id in seen:
            continue
        seen.add(cve_id)
        result.append(cve_id)
    return result


def _collect_article_conflict_update_values(table: Table, excluded: Any) -> dict[str, Any]:
    """Build an upsert that never replaces a usable article with an error.

    A transient refresh failure produces an empty/error record. If the URL
    already has an ``ok`` row, retain that successful payload (including its
    status and CVE tags) instead of making the article disappear from the
    default library view.
    """
    preserve_success = (table.c.status == "ok") & (excluded.status == "error")

    def keep_existing(column: str) -> Any:
        return case(
            (preserve_success, table.c[column]),
            else_=excluded[column],
        )

    return {
        "source_domain": keep_existing("source_domain"),
        "title": keep_existing("title"),
        "markdown": keep_existing("markdown"),
        "summary": keep_existing("summary"),
        "cve_ids": keep_existing("cve_ids"),
        "status": keep_existing("status"),
        "error_message": keep_existing("error_message"),
        "fetched_at": keep_existing("fetched_at"),
        "updated_at": keep_existing("updated_at"),
    }


async def search_collect_articles(
    *,
    query: str = "",
    source_domain: str | None = None,
    status: str | None = "ok",
    page: int = 1,
    size: int = 20,
    include_markdown: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Search articles.

    List responses omit ``markdown`` by default (use ``get_collect_article`` for
    body). ``status`` accepts ``ok`` / ``error`` / ``all`` (None treated as ok).
    """
    await ensure_collect_articles_table()
    safe_page = max(1, int(page or 1))
    safe_size = min(100, max(1, int(size or 20)))
    table = collect_articles_table()
    filters = []
    status_norm = (status or "ok").strip().lower()
    if status_norm in {"ok", "error"}:
        filters.append(table.c.status == status_norm)
    elif status_norm not in {"all", "*"}:
        filters.append(table.c.status == "ok")
    normalized = (query or "").strip()
    if normalized:
        pattern = f"%{normalized}%"
        text_filters = [
            table.c.title.ilike(pattern),
            table.c.summary.ilike(pattern),
            table.c.url.ilike(pattern),
        ]
        # Full-body scan is expensive; only when explicitly requested with markdown.
        if include_markdown:
            text_filters.append(table.c.markdown.ilike(pattern))
        filters.append(or_(*text_filters))
    if source_domain:
        filters.append(table.c.source_domain == source_domain.strip())

    count_stmt = select(func.count()).select_from(table).where(*filters)
    columns = [
        table.c.id,
        table.c.url,
        table.c.source_domain,
        table.c.title,
        table.c.summary,
        table.c.cve_ids,
        table.c.status,
        table.c.error_message,
        table.c.fetched_at,
        table.c.created_at,
        table.c.updated_at,
    ]
    if include_markdown:
        columns.insert(4, table.c.markdown)
    rows_stmt = (
        select(*columns)
        .where(*filters)
        .order_by(desc(table.c.fetched_at), desc(table.c.id))
        .limit(safe_size)
        .offset((safe_page - 1) * safe_size)
    )

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = [
            _row_to_dict(row)
            for row in (await conn.execute(rows_stmt)).mappings().all()
        ]
    if not include_markdown:
        for row in rows:
            row.setdefault("markdown", "")
    return rows, total


async def get_collect_article(article_id: int) -> dict[str, Any] | None:
    await ensure_collect_articles_table()
    table = collect_articles_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(table).where(table.c.id == int(article_id)).limit(1)
                )
            )
            .mappings()
            .first()
        )
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



async def list_error_collect_article_ids(
    *,
    source_domain: str | None = None,
    limit: int = 20,
) -> list[int]:
    """IDs of failed collects, newest first (for bulk reparse)."""
    await ensure_collect_articles_table()
    safe_limit = max(1, min(int(limit or 20), 50))
    table = collect_articles_table()
    filters = [table.c.status == "error"]
    if source_domain:
        filters.append(table.c.source_domain == source_domain.strip())
    stmt = (
        select(table.c.id)
        .where(*filters)
        .order_by(desc(table.c.fetched_at), desc(table.c.id))
        .limit(safe_limit)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).scalars().all()
    return [int(item) for item in rows if item is not None]


async def count_collect_articles_by_status(
    *,
    source_domain: str | None = None,
) -> dict[str, int]:
    """Return ``{status: count}`` for health badges."""
    await ensure_collect_articles_table()
    table = collect_articles_table()
    filters = []
    if source_domain:
        filters.append(table.c.source_domain == source_domain.strip())
    stmt = (
        select(table.c.status, func.count())
        .where(*filters)
        .group_by(table.c.status)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).all()
    out: dict[str, int] = {}
    for status, count in rows:
        key = str(status or "").strip() or "unknown"
        out[key] = int(count or 0)
    return out


async def list_collect_source_stats() -> list[dict[str, Any]]:
    """Per-domain ok/error/total counts for configured library views."""
    await ensure_collect_articles_table()
    table = collect_articles_table()
    stmt = (
        select(
            table.c.source_domain,
            table.c.status,
            func.count().label("cnt"),
        )
        .where(table.c.source_domain != "")
        .group_by(table.c.source_domain, table.c.status)
        .order_by(table.c.source_domain)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).all()
    by_domain: dict[str, dict[str, int]] = {}
    for domain, status, count in rows:
        key = str(domain or "").strip()
        if not key:
            continue
        bucket = by_domain.setdefault(key, {"ok": 0, "error": 0, "total": 0})
        status_key = str(status or "").strip() or "unknown"
        n = int(count or 0)
        if status_key in ("ok", "error"):
            bucket[status_key] = n
        bucket["total"] += n
    return [
        {
            "domain": domain,
            "ok": stats.get("ok", 0),
            "error": stats.get("error", 0),
            "total": stats.get("total", 0),
        }
        for domain, stats in sorted(by_domain.items())
    ]


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
        "cve_ids": _normalize_cve_ids(record.get("cve_ids")),
        "status": str(record.get("status") or "ok"),
        "error_message": str(record.get("error_message") or "")[:2000],
        "fetched_at": record.get("fetched_at") or now,
        "updated_at": now,
    }
    stmt = insert(table).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.url],
        set_=_collect_article_conflict_update_values(table, stmt.excluded),
    ).returning(
        table.c.id,
        table.c.url,
        table.c.source_domain,
        table.c.title,
        table.c.markdown,
        table.c.summary,
        table.c.cve_ids,
        table.c.status,
        table.c.error_message,
        table.c.fetched_at,
        table.c.created_at,
        table.c.updated_at,
    )
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().one()
    return _row_to_dict(row)


async def list_existing_ok_urls(urls: Sequence[str]) -> set[str]:
    """Return the subset of *urls* already stored with status=ok."""
    cleaned = [str(u).strip() for u in urls if str(u).strip()]
    if not cleaned:
        return set()
    await ensure_collect_articles_table()
    table = collect_articles_table()
    # Cap IN clause size for very large batches
    found: set[str] = set()
    chunk_size = 500
    async with get_async_control_plane_engine().begin() as conn:
        for i in range(0, len(cleaned), chunk_size):
            chunk = cleaned[i : i + chunk_size]
            rows = (
                (
                    await conn.execute(
                        select(table.c.url).where(
                            table.c.url.in_(chunk),
                            table.c.status == "ok",
                        )
                    )
                )
                .scalars()
                .all()
            )
            found.update(str(item) for item in rows if item)
    return found


async def bulk_upsert_collect_articles(records: Sequence[dict[str, Any]]) -> int:
    """Upsert many rows in one statement when possible."""
    if not records:
        return 0
    await ensure_collect_articles_table()
    table = collect_articles_table()
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for record in records:
        url = str(record.get("url") or "").strip()
        if not url:
            continue
        rows.append(
            {
                "url": url,
                "source_domain": str(record.get("source_domain") or ""),
                "title": str(record.get("title") or "")[:500],
                "markdown": str(record.get("markdown") or ""),
                "summary": str(record.get("summary") or "")[:1000],
                "cve_ids": _normalize_cve_ids(record.get("cve_ids")),
                "status": str(record.get("status") or "ok"),
                "error_message": str(record.get("error_message") or "")[:2000],
                "fetched_at": record.get("fetched_at") or now,
                "updated_at": now,
            }
        )
    if not rows:
        return 0

    # De-dupe by url (last wins) to satisfy unique index in one INSERT
    by_url: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_url[row["url"]] = row
    values = list(by_url.values())

    stmt = insert(table).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.url],
        set_=_collect_article_conflict_update_values(table, stmt.excluded),
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(stmt)
    return len(values)
