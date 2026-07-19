from __future__ import annotations

from api.utils.async_once import AsyncOnce

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, Table, Text, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.services.postgres_store import coerce_json_value

KNOWLEDGE_SOURCES_TABLE = "knowledge_sources"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def knowledge_sources_table() -> Table:
    table = Table(
        KNOWLEDGE_SOURCES_TABLE,
        _metadata(),
        Column("content_id", Text, primary_key=True),
        Column("source", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
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
            onupdate=func.now(),
        ),
    )
    return table


_knowledge_sources_table_once = AsyncOnce()


async def _create_knowledge_sources_table_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_knowledge_sources_table_async() -> None:
    await _knowledge_sources_table_once.run(_create_knowledge_sources_table_async)


async def upsert_knowledge_source_async(
    content_id: str,
    source: Mapping[str, Any],
) -> None:
    await ensure_knowledge_sources_table_async()
    table = knowledge_sources_table()
    async with get_async_control_plane_engine().begin() as conn:
        stmt = (
            pg_insert(table)
            .values(content_id=content_id, source=dict(source))
            .on_conflict_do_update(
                index_elements=[table.c.content_id],
                set_={"source": dict(source), "updated_at": func.now()},
            )
        )
        await conn.execute(stmt)


async def get_knowledge_source_async(content_id: str) -> dict[str, Any] | None:
    await ensure_knowledge_sources_table_async()
    table = knowledge_sources_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                select(table.c.source).where(table.c.content_id == content_id)
            )
        ).first()
    if row is None:
        return None
    source = coerce_json_value(row.source)
    return dict(source) if isinstance(source, Mapping) else None


async def delete_knowledge_source_async(content_id: str) -> None:
    await ensure_knowledge_sources_table_async()
    table = knowledge_sources_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(table.delete().where(table.c.content_id == content_id))
