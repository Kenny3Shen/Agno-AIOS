from __future__ import annotations

from time import time
from typing import Any, Mapping

from sqlalchemy import BigInteger, Boolean, Column, MetaData, String, Table, insert, select, update
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

CHAT_SETTINGS_TABLE = "chat_settings"
GLOBAL_CHAT_SETTINGS_ID = "global"
DEFAULT_CHAT_SETTINGS = {
    "show_raw_reasoning": False,
    "show_raw_tool_io": False,
    "show_thought_chain": True,
    "memory_enabled": True,
}


def _app_schema() -> str:
    return get_settings().agno_app_schema


def chat_settings_table(metadata: MetaData | None = None) -> Table:
    return Table(
        CHAT_SETTINGS_TABLE,
        metadata or MetaData(schema=_app_schema()),
        Column("id", String(32), primary_key=True),
        Column("show_raw_reasoning", Boolean, nullable=False, server_default="false"),
        Column("show_raw_tool_io", Boolean, nullable=False, server_default="false"),
        Column("show_thought_chain", Boolean, nullable=False, server_default="true"),
        Column("memory_enabled", Boolean, nullable=False, server_default="true"),
        Column("updated_at", BigInteger, nullable=False),
    )


async def ensure_chat_settings_table_async() -> None:
    table = chat_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_app_schema(), if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)


async def get_chat_settings_row() -> dict[str, Any]:
    await ensure_chat_settings_table_async()
    table = chat_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                select(table).where(table.c.id == GLOBAL_CHAT_SETTINGS_ID)
            )
        ).mappings().first()
        if row is None:
            values = {
                "id": GLOBAL_CHAT_SETTINGS_ID,
                **DEFAULT_CHAT_SETTINGS,
                "updated_at": int(time()),
            }
            await conn.execute(insert(table).values(**values))
            return values
    return dict(row)


async def update_chat_settings_row(values: Mapping[str, bool]) -> dict[str, Any]:
    current = await get_chat_settings_row()
    updates: dict[str, Any] = {
        key: bool(value) for key, value in values.items() if key in DEFAULT_CHAT_SETTINGS
    }
    if not updates:
        return current
    updates["updated_at"] = int(time())
    table = chat_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(
            update(table)
            .where(table.c.id == GLOBAL_CHAT_SETTINGS_ID)
            .values(**updates)
        )
    return {**current, **updates}
