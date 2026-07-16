from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping

from api.persistence.chat_settings import (
    DEFAULT_CHAT_SETTINGS,
    get_chat_settings_row,
    update_chat_settings_row,
)

# Short-lived process cache for hot chat paths; cleared on update.
_SETTINGS_CACHE: dict[str, bool] | None = None
_SETTINGS_CACHE_AT: float = 0.0
_SETTINGS_CACHE_TTL_SEC = 5.0


@dataclass(frozen=True)
class ChatSettings:
    show_raw_reasoning: bool = False
    show_raw_tool_io: bool = False
    show_thought_chain: bool = True
    memory_enabled: bool = True


def _invalidate_chat_settings_cache() -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_AT
    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_AT = 0.0


def _project_settings(row: Mapping[str, object]) -> dict[str, bool]:
    return {key: bool(row.get(key, default)) for key, default in DEFAULT_CHAT_SETTINGS.items()}


async def get_chat_settings() -> dict[str, bool]:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_AT
    now = time.time()
    if _SETTINGS_CACHE is not None and (now - _SETTINGS_CACHE_AT) < _SETTINGS_CACHE_TTL_SEC:
        return dict(_SETTINGS_CACHE)
    row = await get_chat_settings_row()
    projected = _project_settings(row)
    _SETTINGS_CACHE = projected
    _SETTINGS_CACHE_AT = now
    return dict(projected)


async def get_chat_settings_async() -> ChatSettings:
    values = await get_chat_settings()
    return ChatSettings(**values)


async def update_chat_settings(values: Mapping[str, bool]) -> dict[str, bool]:
    row = await update_chat_settings_row(values)
    projected = _project_settings(row)
    global _SETTINGS_CACHE, _SETTINGS_CACHE_AT
    _SETTINGS_CACHE = projected
    _SETTINGS_CACHE_AT = time.time()
    return dict(projected)


__all__ = [
    "ChatSettings",
    "get_chat_settings",
    "get_chat_settings_async",
    "update_chat_settings",
]
