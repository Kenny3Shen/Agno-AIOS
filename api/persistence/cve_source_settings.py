"""Persisted enablement overrides for CVE ingestion sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from time import time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

CVE_SOURCE_SETTINGS_TABLE = "cve_source_settings"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def cve_source_settings_table(metadata: MetaData | None = None) -> Table:
    return Table(
        CVE_SOURCE_SETTINGS_TABLE,
        metadata or MetaData(schema=_app_schema()),
        Column("source", String(128), primary_key=True),
        Column("enabled", Boolean, nullable=False, server_default="true"),
        Column("updated_at", BigInteger, nullable=False),
    )


_table_once = AsyncOnce()


async def _ensure_table_schema_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_cve_source_settings_table_async() -> None:
    await _table_once.run(_ensure_table_schema_async)


def _normalize_source_names(source_names: Iterable[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for source_name in source_names:
        source = str(source_name).strip()
        if source and source not in seen:
            names.append(source)
            seen.add(source)
    return names


async def get_cve_source_enabled_map(
    source_names: Iterable[str],
) -> dict[str, bool]:
    """Return each configured source's enablement, defaulting absent rows to true."""
    names = _normalize_source_names(source_names)
    if not names:
        return {}

    await ensure_cve_source_settings_table_async()
    table = cve_source_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        rows = (
            await conn.execute(
                select(table.c.source, table.c.enabled).where(table.c.source.in_(names))
            )
        ).mappings()
        saved = {str(row["source"]): bool(row["enabled"]) for row in rows}
    return {source: saved.get(source, True) for source in names}


async def update_cve_source_enabled_map(
    values: Mapping[str, bool],
    source_names: Iterable[str],
) -> dict[str, bool]:
    """Persist supported source toggles and return the complete current map."""
    names = _normalize_source_names(source_names)
    supported = set(names)
    requested = {str(source).strip() for source in values}
    unknown = sorted(source for source in requested if source not in supported)
    if unknown:
        raise ValueError(f"Unknown CVE source(s): {', '.join(unknown)}")

    updates: dict[str, bool] = {}
    for raw_source, enabled in values.items():
        source = str(raw_source).strip()
        if source in supported:
            updates[source] = bool(enabled)
    current = await get_cve_source_enabled_map(names)
    if not updates:
        return current

    table = cve_source_settings_table()
    now = int(time())
    async with get_async_control_plane_engine().begin() as conn:
        existing = set(
            (
                await conn.execute(
                    select(table.c.source).where(table.c.source.in_(list(updates)))
                )
            )
            .scalars()
            .all()
        )
        for source, enabled in updates.items():
            if source in existing:
                await conn.execute(
                    update(table)
                    .where(table.c.source == source)
                    .values(enabled=enabled, updated_at=now)
                )
            else:
                await conn.execute(
                    insert(table).values(source=source, enabled=enabled, updated_at=now)
                )

    return {**current, **updates}
