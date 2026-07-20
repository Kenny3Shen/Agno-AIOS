"""Per-user notification preferences (e.g. Feishu webhook)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import BigInteger, Column, MetaData, String, Table, select, update
from sqlalchemy.dialects.postgresql import insert

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

USER_NOTIFICATION_SETTINGS_TABLE = "user_notification_settings"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def user_notification_settings_table(metadata: MetaData | None = None) -> Table:
    return Table(
        USER_NOTIFICATION_SETTINGS_TABLE,
        metadata or MetaData(schema=_app_schema()),
        Column("user_id", String(255), primary_key=True),
        # Secret stored server-side only; never log or return full value by default.
        Column("feishu_webhook_url", String(2048), nullable=False, server_default=""),
        Column("updated_at", BigInteger, nullable=False),
    )


_table_once = AsyncOnce()


async def _ensure() -> None:
    await ensure_control_plane_schema_current()


async def ensure_user_notification_settings_table() -> None:
    await _table_once.run(_ensure)


async def get_user_feishu_webhook_url(user_id: str) -> str:
    """Return the stored webhook URL for *user_id*, or empty string."""
    owner = (user_id or "").strip()
    if not owner:
        return ""
    await ensure_user_notification_settings_table()
    table = user_notification_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(table.c.feishu_webhook_url).where(table.c.user_id == owner)
                )
            )
            .mappings()
            .first()
        )
    if not row:
        return ""
    return str(row.get("feishu_webhook_url") or "").strip()


async def get_user_notification_settings_public(user_id: str) -> dict[str, Any]:
    """Public projection: whether a webhook is set, never the full secret."""
    url = await get_user_feishu_webhook_url(user_id)
    return {
        "feishu_webhook_configured": bool(url),
        # Masked hint so users can tell which bot they saved (last path segment tail).
        "feishu_webhook_hint": _mask_webhook(url) if url else "",
    }


def _mask_webhook(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    # Keep scheme + host + last 6 chars of path secret.
    if len(text) <= 24:
        return text[:8] + "…"
    return text[:28] + "…" + text[-6:]


async def upsert_user_feishu_webhook_url(user_id: str, webhook_url: str) -> dict[str, Any]:
    """Create/update the user's Feishu webhook. Empty string clears the override."""
    owner = (user_id or "").strip()
    if not owner:
        raise ValueError("user_id is required")
    value = (webhook_url or "").strip()
    await ensure_user_notification_settings_table()
    table = user_notification_settings_table()
    now = int(time.time())
    async with get_async_control_plane_engine().begin() as conn:
        existing = (
            (
                await conn.execute(
                    select(table.c.user_id).where(table.c.user_id == owner)
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            await conn.execute(
                insert(table).values(
                    user_id=owner,
                    feishu_webhook_url=value,
                    updated_at=now,
                )
            )
        else:
            await conn.execute(
                update(table)
                .where(table.c.user_id == owner)
                .values(feishu_webhook_url=value, updated_at=now)
            )
    return await get_user_notification_settings_public(owner)
