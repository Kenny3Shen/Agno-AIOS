from __future__ import annotations

from typing import Mapping

from api.persistence.chat_settings import (
    DEFAULT_CHAT_SETTINGS,
    get_chat_settings_row,
    update_chat_settings_row,
)


async def get_chat_settings() -> dict[str, bool]:
    row = await get_chat_settings_row()
    return {key: bool(row.get(key, default)) for key, default in DEFAULT_CHAT_SETTINGS.items()}


async def update_chat_settings(values: Mapping[str, bool]) -> dict[str, bool]:
    row = await update_chat_settings_row(values)
    return {key: bool(row.get(key, default)) for key, default in DEFAULT_CHAT_SETTINGS.items()}
