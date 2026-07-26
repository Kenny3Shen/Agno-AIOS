"""Resolve and manage per-user Feishu webhook settings."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from api.persistence.user_notification_settings import (
    get_user_feishu_webhook_url,
    get_user_notification_settings_public,
    upsert_user_feishu_webhook_url,
)


def is_secure_feishu_webhook_url(value: str) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


async def resolve_feishu_webhook_url(user_id: str | None) -> str:
    """Return the caller's personal webhook, never a process-wide fallback."""
    owner = (user_id or "").strip()
    return await get_user_feishu_webhook_url(owner) if owner else ""


async def read_user_notification_settings(user_id: str) -> dict[str, Any]:
    return await get_user_notification_settings_public(user_id)


async def update_user_feishu_webhook(user_id: str, webhook_url: str | None) -> dict[str, Any]:
    """Set or clear the user's webhook. None means no change; '' clears."""
    if webhook_url is None:
        return await read_user_notification_settings(user_id)
    value = webhook_url.strip()
    if value and not is_secure_feishu_webhook_url(value):
        raise ValueError("飞书 Webhook 必须是 https:// 开头的完整 URL")
    await upsert_user_feishu_webhook_url(user_id, value)
    return await read_user_notification_settings(user_id)
