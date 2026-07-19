from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from api.persistence.chat_settings import (
    DEFAULT_CHAT_SETTINGS,
    get_chat_settings_row,
    update_chat_settings_row,
)
from api.utils.ttl_cache import TtlCache

# Short-lived process cache for hot chat paths; cleared on update.
_SETTINGS_CACHE: TtlCache[dict[str, bool]] = TtlCache(ttl_sec=5.0)


@dataclass(frozen=True)
class ChatSettings:
    show_raw_reasoning: bool = False
    show_raw_tool_io: bool = False
    show_thought_chain: bool = True
    memory_enabled: bool = True


def _project_settings(row: Mapping[str, object]) -> dict[str, bool]:
    return {key: bool(row.get(key, default)) for key, default in DEFAULT_CHAT_SETTINGS.items()}


async def get_chat_settings() -> dict[str, bool]:
    cached = _SETTINGS_CACHE.get()
    if cached is not None:
        return dict(cached)
    row = await get_chat_settings_row()
    projected = _project_settings(row)
    _SETTINGS_CACHE.set(projected)
    return dict(projected)


async def get_chat_settings_async() -> ChatSettings:
    values = await get_chat_settings()
    return ChatSettings(**values)


async def update_chat_settings(values: Mapping[str, bool]) -> dict[str, bool]:
    row = await update_chat_settings_row(values)
    projected = _project_settings(row)
    _SETTINGS_CACHE.set(projected)
    return dict(projected)


__all__ = [
    "ChatSettings",
    "get_chat_settings",
    "get_chat_settings_async",
    "update_chat_settings",
]
