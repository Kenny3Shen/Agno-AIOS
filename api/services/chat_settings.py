"""Compatibility-facing Chat settings API for runtime consumers."""

from __future__ import annotations

from dataclasses import dataclass

from api.services.chat_settings_service import (
    get_chat_settings as _get_chat_settings,
    update_chat_settings,
)


@dataclass(frozen=True)
class ChatSettings:
    show_raw_reasoning: bool = False
    show_raw_tool_io: bool = False
    show_thought_chain: bool = True
    memory_enabled: bool = True


async def get_chat_settings_async() -> ChatSettings:
    values = await _get_chat_settings()
    return ChatSettings(**values)


async def get_chat_settings() -> dict[str, bool]:
    return await _get_chat_settings()


__all__ = ["ChatSettings", "get_chat_settings", "get_chat_settings_async", "update_chat_settings"]
