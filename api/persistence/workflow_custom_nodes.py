"""Per-user Workflow Studio custom step nodes (reusable palette presets)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import BigInteger, Column, MetaData, String, Table, Text, delete, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

WORKFLOW_CUSTOM_NODES_TABLE = "workflow_custom_nodes"


def _metadata() -> MetaData:
    return MetaData(schema=get_settings().agno_app_schema)


def workflow_custom_nodes_table(metadata: MetaData | None = None) -> Table:
    return Table(
        WORKFLOW_CUSTOM_NODES_TABLE,
        metadata or _metadata(),
        Column("id", String(64), primary_key=True),
        Column("user_id", String(255), nullable=False),
        Column("name", String(255), nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("color", String(32), nullable=False, server_default="#1677ff"),
        Column("definition", JSONB, nullable=False, server_default="{}"),
        Column("created_at", BigInteger, nullable=False),
        Column("updated_at", BigInteger, nullable=False),
    )


_table_ready = AsyncOnce()


async def ensure_workflow_custom_nodes_table() -> None:
    async def _ready() -> None:
        await ensure_control_plane_schema_current()

    await _table_ready.run(_ready)


async def list_custom_nodes_for_user(user_id: str) -> list[dict[str, Any]]:
    await ensure_workflow_custom_nodes_table()
    table = workflow_custom_nodes_table()
    stmt = (
        select(table)
        .where(table.c.user_id == user_id)
        .order_by(table.c.updated_at.desc(), table.c.name.asc())
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def get_custom_node_for_user(user_id: str, node_id: str) -> dict[str, Any] | None:
    await ensure_workflow_custom_nodes_table()
    table = workflow_custom_nodes_table()
    stmt = select(table).where(table.c.user_id == user_id, table.c.id == node_id)
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().first()
    return dict(row) if row else None


async def upsert_custom_node_for_user(
    user_id: str,
    *,
    node_id: str | None,
    name: str,
    description: str,
    color: str,
    definition: dict[str, Any],
) -> dict[str, Any]:
    await ensure_workflow_custom_nodes_table()
    table = workflow_custom_nodes_table()
    now = int(time.time())
    resolved_id = (node_id or "").strip() or str(uuid.uuid4())
    values = {
        "id": resolved_id,
        "user_id": user_id,
        "name": name,
        "description": description,
        "color": color,
        "definition": definition,
        "created_at": now,
        "updated_at": now,
    }
    stmt = (
        insert(table)
        .values(values)
        .on_conflict_do_update(
            index_elements=[table.c.id],
            set_={
                "name": name,
                "description": description,
                "color": color,
                "definition": definition,
                "updated_at": now,
            },
            where=(table.c.user_id == user_id),
        )
        .returning(table)
    )
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().first()
    if row is None:
        # Conflict on another user's id — allocate a fresh id.
        values["id"] = str(uuid.uuid4())
        async with get_async_control_plane_engine().begin() as conn:
            row = (await conn.execute(insert(table).values(values).returning(table))).mappings().one()
    return dict(row)


async def delete_custom_node_for_user(user_id: str, node_id: str) -> bool:
    await ensure_workflow_custom_nodes_table()
    table = workflow_custom_nodes_table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            delete(table).where(table.c.user_id == user_id, table.c.id == node_id)
        )
    return bool(result.rowcount)
