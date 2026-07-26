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
    case,
    delete,
    desc,
    func,
    literal,
    or_,
    select,
    tuple_,
)
from sqlalchemy.dialects.postgresql import insert
from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current

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
    )
    Index("idx_cves_cve_id", table.c.cve_id)
    Index("idx_cves_source", table.c.source)
    # A reference can legitimately be supplied by more than one upstream
    # feed.  Source is therefore part of its ownership key: reconciling one
    # feed must never remove another feed's membership.
    Index(
        "uq_cves_cve_url_source",
        table.c.cve_id,
        table.c.github_url,
        table.c.source,
        unique=True,
    )
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
    await ensure_control_plane_schema_current()


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
    order_by = [desc(table.c.created_at), desc(table.c.id)]
    if normalized_query:
        upper_q = normalized_query.upper()
        # Exact / prefix CVE-ID lookups stay on btree-friendly ILIKE.
        if upper_q.startswith("CVE-") and len(upper_q) <= 32 and " " not in upper_q:
            pattern = f"%{normalized_query}%"
            filters.append(
                or_(
                    table.c.cve_id.ilike(pattern),
                    table.c.description.ilike(pattern),
                )
            )
            order_by = [
                case((func.upper(table.c.cve_id) == upper_q, 0), else_=1),
                desc(table.c.created_at),
                desc(table.c.id),
            ]
        else:
            # Keyword search: use GIN full-text index (idx_cves_search).
            tsvector = func.to_tsvector(
                "simple",
                table.c.cve_id.concat(literal(" ")).concat(
                    func.coalesce(table.c.description, "")
                ),
            )
            tsquery = func.plainto_tsquery("simple", normalized_query)
            filters.append(tsvector.op("@@")(tsquery))
            order_by = [
                desc(func.ts_rank_cd(tsvector, tsquery)),
                desc(table.c.created_at),
                desc(table.c.id),
            ]
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
        .order_by(*order_by)
        .limit(safe_size)
        .offset((safe_page - 1) * safe_size)
    )

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = [dict(row) for row in (await conn.execute(rows_stmt)).mappings().all()]
    return rows, total


async def insert_new_cve_rows(rows: Sequence[dict[str, Any]]) -> int:
    """Insert new references and refresh mutable source data on conflict.

    The historical function name is kept for call-site compatibility.  Its
    upsert behaviour also refreshes changed descriptions and timestamps so a
    remote correction is visible without waiting for a new reference URL.
    """
    if not rows:
        return 0
    await ensure_cves_table()
    now = datetime.now(UTC)
    table = cves_table()
    values: list[dict[str, Any]] = []
    for row in rows:
        cve_id = str(row.get("cve_id") or "").strip().upper()
        github_url = str(row.get("github_url") or "").strip()
        source = str(row.get("source") or "").strip()
        if not cve_id or not github_url or not source:
            continue
        values.append(
            {
                "cve_id": cve_id,
                "description": str(row.get("description") or ""),
                "github_url": github_url,
                "source": source,
                "create_time": row.get("create_time") or now,
                "updated_at": now,
            }
        )
    if not values:
        return 0
    stmt = insert(table).values(values)
    stmt = (
        stmt.on_conflict_do_update(
            index_elements=[table.c.cve_id, table.c.github_url, table.c.source],
            set_={
                "description": stmt.excluded.description,
                "create_time": stmt.excluded.create_time,
                "updated_at": now,
            },
        )
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(stmt)
    # psycopg reports ``-1`` for this multi-row INSERT .. ON CONFLICT DO
    # UPDATE statement, even though every validated value was inserted or
    # refreshed.  The source delta is already deduplicated, so its validated
    # value count is the reliable write count for progress and completion UI.
    return len(values)


async def find_missing_cve_source_keys(
    rows: Sequence[dict[str, Any]],
) -> set[tuple[str, str, str]]:
    """Return source-owned CVE identities absent from the database.

    After upgrading the legacy two-column uniqueness constraint, a local cache
    can know that a second source owns a reference even though the old database
    could store only the first source. This lookup allows the update task to
    repair only those missing memberships instead of replaying an entire cache.
    """
    requested: set[tuple[str, str, str]] = set()
    for row in rows:
        cve_id = str(row.get("cve_id") or "").strip().upper()
        github_url = str(row.get("github_url") or "").strip()
        source = str(row.get("source") or "").strip()
        if cve_id and github_url and source:
            requested.add((cve_id, github_url, source))
    if not requested:
        return set()

    await ensure_cves_table()
    table = cves_table()
    existing: set[tuple[str, str, str]] = set()
    # Keep parameter counts bounded while allowing a single set-based lookup
    # per chunk instead of one query for every cached row.
    chunk_size = 1_000
    identities = list(requested)
    async with get_async_control_plane_engine().begin() as conn:
        for index in range(0, len(identities), chunk_size):
            chunk = identities[index : index + chunk_size]
            rows_found = (
                (
                    await conn.execute(
                        select(table.c.cve_id, table.c.github_url, table.c.source).where(
                            tuple_(
                                table.c.cve_id,
                                table.c.github_url,
                                table.c.source,
                            ).in_(chunk)
                        )
                    )
                )
                .all()
            )
            existing.update(
                (str(cve_id), str(github_url), str(source))
                for cve_id, github_url, source in rows_found
            )
    return requested.difference(existing)


async def delete_cve_rows(rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    await ensure_cves_table()
    table = cves_table()
    pairs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        cve_id = str(row.get("cve_id") or "").strip().upper()
        github_url = str(row.get("github_url") or "").strip()
        source = str(row.get("source") or "").strip()
        # Do not make a legacy/cache row without source ownership capable of
        # deleting every matching reference in the database.
        if not cve_id or not github_url or not source:
            continue
        key = (cve_id, github_url, source)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    if not pairs:
        return 0
    deleted = 0
    chunk_size = 200
    async with get_async_control_plane_engine().begin() as conn:
        for i in range(0, len(pairs), chunk_size):
            chunk = pairs[i : i + chunk_size]
            result = await conn.execute(
                delete(table).where(
                    or_(
                        *[
                            (table.c.cve_id == cve_id)
                            & (table.c.github_url == github_url)
                            & (table.c.source == source)
                            for cve_id, github_url, source in chunk
                        ]
                    )
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
