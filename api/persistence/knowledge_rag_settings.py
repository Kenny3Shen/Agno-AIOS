from __future__ import annotations

from time import time
from typing import Any, Mapping

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Float,
    Integer,
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

KNOWLEDGE_RAG_SETTINGS_TABLE = "knowledge_rag_settings"
GLOBAL_KNOWLEDGE_RAG_SETTINGS_ID = "global"

# Runtime-tunable PgVector / retrieval knobs (env supplies defaults).
DEFAULT_KNOWLEDGE_RAG_SETTINGS: dict[str, Any] = {
    "search_type": "hybrid",
    "top_k": 5,
    "vector_score_weight": 0.55,
    "similarity_threshold": 0.35,
    "content_language": "english",
    "prefix_match": False,
    "rerank_enabled": True,
    "rerank_candidate_multiplier": 3,
    "rerank_min_candidates": 10,
}


def _app_schema() -> str:
    return get_settings().agno_app_schema


def knowledge_rag_settings_table(metadata: MetaData | None = None) -> Table:
    return Table(
        KNOWLEDGE_RAG_SETTINGS_TABLE,
        metadata or MetaData(schema=_app_schema()),
        Column("id", String(32), primary_key=True),
        Column("search_type", String(32), nullable=False, server_default="hybrid"),
        Column("top_k", Integer, nullable=False, server_default="5"),
        Column("vector_score_weight", Float, nullable=False, server_default="0.55"),
        Column("similarity_threshold", Float, nullable=True),
        Column("content_language", String(64), nullable=False, server_default="english"),
        Column("prefix_match", Boolean, nullable=False, server_default="false"),
        Column("rerank_enabled", Boolean, nullable=False, server_default="true"),
        Column("rerank_candidate_multiplier", Integer, nullable=False, server_default="3"),
        Column("rerank_min_candidates", Integer, nullable=False, server_default="10"),
        Column("updated_at", BigInteger, nullable=False),
    )


_table_once = AsyncOnce()


async def _create_table_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_knowledge_rag_settings_table_async() -> None:
    await _table_once.run(_create_table_async)


def _env_defaults() -> dict[str, Any]:
    settings = get_settings()
    return {
        "search_type": settings.agno_knowledge_search_type,
        "top_k": max(1, settings.agno_knowledge_top_k),
        "vector_score_weight": settings.agno_knowledge_vector_score_weight,
        "similarity_threshold": settings.agno_knowledge_similarity_threshold,
        "content_language": settings.agno_knowledge_content_language,
        "prefix_match": settings.agno_knowledge_prefix_match,
        "rerank_enabled": settings.agno_knowledge_rerank_enabled,
        "rerank_candidate_multiplier": max(
            1, settings.agno_knowledge_rerank_candidate_multiplier
        ),
        "rerank_min_candidates": max(1, settings.agno_knowledge_rerank_min_candidates),
    }


def _row_payload(row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    defaults = _env_defaults()
    if row is None:
        return dict(defaults)
    payload = dict(defaults)
    for key in DEFAULT_KNOWLEDGE_RAG_SETTINGS:
        if key in row and row[key] is not None:
            payload[key] = row[key]
        elif key == "similarity_threshold" and key in row:
            # Explicit NULL means filtering disabled.
            payload[key] = row[key]
    return payload


async def get_knowledge_rag_settings_row() -> dict[str, Any]:
    await ensure_knowledge_rag_settings_table_async()
    table = knowledge_rag_settings_table()
    defaults = _env_defaults()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(table).where(table.c.id == GLOBAL_KNOWLEDGE_RAG_SETTINGS_ID)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            values = {
                "id": GLOBAL_KNOWLEDGE_RAG_SETTINGS_ID,
                **defaults,
                "updated_at": int(time()),
            }
            await conn.execute(insert(table).values(**values))
            return _row_payload(values)
    return _row_payload(dict(row))


async def update_knowledge_rag_settings_row(
    values: Mapping[str, Any],
) -> dict[str, Any]:
    current = await get_knowledge_rag_settings_row()
    allowed = set(DEFAULT_KNOWLEDGE_RAG_SETTINGS)
    updates: dict[str, Any] = {}
    for key, value in values.items():
        if key not in allowed:
            continue
        updates[key] = value
    if not updates:
        return current
    updates["updated_at"] = int(time())
    table = knowledge_rag_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(
            update(table)
            .where(table.c.id == GLOBAL_KNOWLEDGE_RAG_SETTINGS_ID)
            .values(**updates)
        )
    return {**current, **updates}
