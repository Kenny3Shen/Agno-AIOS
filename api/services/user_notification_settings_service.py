"""Resolve and manage per-user Feishu webhook settings."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from api.config import get_settings
from api.persistence.user_notification_settings import (
    get_user_feishu_webhook_url,
    get_user_notification_settings_public,
    upsert_user_feishu_webhook_url,
)


def is_secure_feishu_webhook_url(value: str) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def global_feishu_webhook_url() -> str:
    return get_settings().feishu_webhook_url.get_secret_value().strip()


async def resolve_feishu_webhook_url(user_id: str | None) -> str:
    """Prefer per-user webhook; fall back to process-wide FEISHU_WEBHOOK_URL."""
    owner = (user_id or "").strip()
    if owner:
        personal = await get_user_feishu_webhook_url(owner)
        if personal:
            return personal
    return global_feishu_webhook_url()


async def read_user_notification_settings(user_id: str) -> dict[str, Any]:
    public = await get_user_notification_settings_public(user_id)
    return {
        **public,
        "global_feishu_webhook_configured": bool(global_feishu_webhook_url()),
    }


async def update_user_feishu_webhook(user_id: str, webhook_url: str | None) -> dict[str, Any]:
    """Set or clear the user's webhook. None means no change; '' clears."""
    if webhook_url is None:
        return await read_user_notification_settings(user_id)
    value = webhook_url.strip()
    if value and not is_secure_feishu_webhook_url(value):
        raise ValueError("飞书 Webhook 必须是 https:// 开头的完整 URL")
    await upsert_user_feishu_webhook_url(user_id, value)
    return await read_user_notification_settings(user_id)
