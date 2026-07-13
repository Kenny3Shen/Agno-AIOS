from __future__ import annotations

import time
from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, MetaData, String, Table, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine


def _table() -> Table:
    metadata = MetaData(schema=get_settings().agno_app_schema)
    return Table("notifications", metadata, Column("id", BigInteger, primary_key=True, autoincrement=True), Column("user_id", String(255), nullable=False), Column("title", Text, nullable=False), Column("body", Text, nullable=False), Column("data", JSONB, nullable=False), Column("read", Boolean, nullable=False, server_default="false"), Column("created_at", BigInteger, nullable=False), Column("read_at", BigInteger))


async def _ensure() -> None:
    table = _table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(get_settings().agno_app_schema, if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)


async def create_notifications(user_ids: list[str], *, title: str, body: str, data: dict[str, Any]) -> None:
    if not user_ids:
        return
    await _ensure()
    table = _table()
    now = int(time.time())
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(insert(table), [{"user_id": user_id, "title": title, "body": body, "data": data, "created_at": now} for user_id in user_ids])


async def list_notifications(user_id: str, unread_only: bool) -> tuple[list[dict[str, Any]], int]:
    await _ensure()
    table = _table()
    stmt = select(table).where(table.c.user_id == user_id).order_by(table.c.created_at.desc())
    if unread_only:
        stmt = stmt.where(table.c.read.is_(False))
    async with get_async_control_plane_engine().begin() as conn:
        rows = [dict(row) for row in (await conn.execute(stmt)).mappings().all()]
        unread = int((await conn.execute(select(func.count()).select_from(table).where(table.c.user_id == user_id, table.c.read.is_(False)))).scalar_one())
    return rows, unread


async def mark_notification_read(notification_id: int, user_id: str) -> bool:
    await _ensure()
    table = _table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(update(table).where(table.c.id == notification_id, table.c.user_id == user_id).values(read=True, read_at=int(time.time())))
    return bool(result.rowcount)
