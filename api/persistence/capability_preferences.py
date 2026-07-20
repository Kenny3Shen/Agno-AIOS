"""Persistence for sparse, per-user capability preference overrides."""

from __future__ import annotations

import time
from typing import Literal, cast

from sqlalchemy import BigInteger, CheckConstraint, Column, Index, MetaData, String, Table, delete, select
from sqlalchemy.dialects.postgresql import insert

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

CapabilityType = Literal["skill", "mcp_server"]
PreferenceState = Literal["enabled", "disabled"]

CAPABILITY_PREFERENCES_TABLE = "user_capability_preferences"


def _metadata() -> MetaData:
    return MetaData(schema=get_settings().agno_app_schema)


def capability_preferences_table(metadata: MetaData | None = None) -> Table:
    table = Table(
        CAPABILITY_PREFERENCES_TABLE,
        metadata or _metadata(),
        Column("user_id", String(255), primary_key=True),
        Column("capability_type", String(32), primary_key=True),
        Column("capability_key", String(255), primary_key=True),
        Column("state", String(16), nullable=False),
        Column("created_at", BigInteger, nullable=False),
        Column("updated_at", BigInteger, nullable=False),
        CheckConstraint(
            "capability_type IN ('skill', 'mcp_server')",
            name="ck_user_capability_preferences_type",
        ),
        CheckConstraint(
            "state IN ('enabled', 'disabled')",
            name="ck_user_capability_preferences_state",
        ),
    )
    Index(
        "idx_user_capability_preferences_user",
        table.c.user_id,
        table.c.capability_type,
    )
    return table


_ensure_once = AsyncOnce()


async def _ensure_table() -> None:
    await ensure_control_plane_schema_current()


async def ensure_capability_preferences_table() -> None:
    await _ensure_once.run(_ensure_table)


async def list_capability_preferences(
    user_id: str,
) -> dict[tuple[str, str], PreferenceState]:
    """Return the user's explicit overrides keyed by (type, stable key)."""
    await ensure_capability_preferences_table()
    table = capability_preferences_table()
    stmt = select(table.c.capability_type, table.c.capability_key, table.c.state).where(
        table.c.user_id == user_id
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).all()
    return {
        (str(row.capability_type), str(row.capability_key)): cast(
            PreferenceState, str(row.state)
        )
        for row in rows
    }


async def set_capability_preference(
    *,
    user_id: str,
    capability_type: CapabilityType,
    capability_key: str,
    state: PreferenceState,
) -> None:
    await ensure_capability_preferences_table()
    table = capability_preferences_table()
    now = int(time.time())
    stmt = insert(table).values(
        user_id=user_id,
        capability_type=capability_type,
        capability_key=capability_key,
        state=state,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.user_id, table.c.capability_type, table.c.capability_key],
        set_={"state": state, "updated_at": now},
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(stmt)


async def clear_capability_preference(
    *, user_id: str, capability_type: CapabilityType, capability_key: str
) -> bool:
    await ensure_capability_preferences_table()
    table = capability_preferences_table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            delete(table).where(
                table.c.user_id == user_id,
                table.c.capability_type == capability_type,
                table.c.capability_key == capability_key,
            )
        )
    return bool(result.rowcount)


async def clear_capability_preferences_for_resource(
    *, capability_type: CapabilityType, capability_key: str
) -> int:
    """Remove stale overrides after a resource is permanently deleted."""
    await ensure_capability_preferences_table()
    table = capability_preferences_table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            delete(table).where(
                table.c.capability_type == capability_type,
                table.c.capability_key == capability_key,
            )
        )
    return int(result.rowcount or 0)
