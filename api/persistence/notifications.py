from __future__ import annotations

from api.utils.async_once import AsyncOnce

import time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Index,
    MetaData,
    String,
    Table,
    Text,
    delete,
    desc,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current


def _table() -> Table:
    metadata = MetaData(schema=get_settings().agno_app_schema)
    table = Table(
        "notifications",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("user_id", String(255), nullable=False),
        Column("title", Text, nullable=False),
        Column("body", Text, nullable=False),
        Column("data", JSONB, nullable=False),
        Column("read", Boolean, nullable=False, server_default="false"),
        Column("created_at", BigInteger, nullable=False),
        Column("read_at", BigInteger),
    )
    # Hot paths: drawer list (user + created_at) and SSE cursor (user + id).
    Index("idx_notifications_user_created", table.c.user_id, desc(table.c.created_at))
    Index("idx_notifications_user_id", table.c.user_id, table.c.id)
    Index("idx_notifications_user_unread", table.c.user_id, table.c.read)
    return table


_notifications_ensure_once = AsyncOnce()


async def _create_notifications_table() -> None:
    await ensure_control_plane_schema_current()


async def _ensure() -> None:
    await _notifications_ensure_once.run(_create_notifications_table)


async def create_notifications(
    user_ids: list[str],
    *,
    title: str,
    body: str,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    if not user_ids:
        return []
    await _ensure()
    table = _table()
    now = int(time.time())
    records = [
        {
            "user_id": user_id,
            "title": title,
            "body": body,
            "data": data,
            "created_at": now,
        }
        for user_id in dict.fromkeys(user_ids)
        if user_id
    ]
    if not records:
        return []
    async with get_async_control_plane_engine().begin() as conn:
        rows = (
            (await conn.execute(insert(table).returning(table), records))
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


async def list_notifications(
    user_id: str,
    unread_only: bool,
    *,
    limit: int = 100,
) -> tuple[list[dict[str, Any]], int]:
    """Return recent notifications for a user (newest first) with unread total.

    Caps the returned list so the notification drawer cannot materialize an
    unbounded history; ``unread_count`` remains a full-table count.
    """
    await _ensure()
    table = _table()
    safe_limit = max(1, min(int(limit or 100), 200))
    stmt = (
        select(table)
        .where(table.c.user_id == user_id)
        .order_by(table.c.created_at.desc())
        .limit(safe_limit)
    )
    if unread_only:
        stmt = stmt.where(table.c.read.is_(False))
    async with get_async_control_plane_engine().begin() as conn:
        rows = [dict(row) for row in (await conn.execute(stmt)).mappings().all()]
        unread = int(
            (
                await conn.execute(
                    select(func.count())
                    .select_from(table)
                    .where(table.c.user_id == user_id, table.c.read.is_(False))
                )
            ).scalar_one()
        )
    return rows, unread


async def list_notifications_after(
    user_id: str,
    after_id: int,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await _ensure()
    table = _table()
    safe_limit = max(1, min(int(limit or 100), 200))
    stmt = (
        select(table)
        .where(table.c.user_id == user_id, table.c.id > max(0, int(after_id)))
        .order_by(table.c.id.asc())
        .limit(safe_limit)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def mark_notification_read(notification_id: int, user_id: str) -> bool:
    await _ensure()
    table = _table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            update(table)
            .where(table.c.id == notification_id, table.c.user_id == user_id)
            .values(read=True, read_at=int(time.time()))
        )
    return bool(result.rowcount)


async def mark_all_notifications_read(user_id: str) -> int:
    """Mark every unread notification for a user as read.

    The user predicate is intentionally part of the update so this operation can
    never affect notifications belonging to another account.
    """
    await _ensure()
    table = _table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            update(table)
            .where(table.c.user_id == user_id, table.c.read.is_(False))
            .values(read=True, read_at=int(time.time()))
        )
    return int(result.rowcount or 0)


async def delete_notification(notification_id: int, user_id: str) -> bool:
    """Delete one notification owned by the given user.

    Only rows matching both id and user_id are removed so callers cannot delete
    another account's notifications even with a guessed id.
    """
    await _ensure()
    table = _table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            delete(table).where(
                table.c.id == notification_id, table.c.user_id == user_id
            )
        )
    return bool(result.rowcount)
