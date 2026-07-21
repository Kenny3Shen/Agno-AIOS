from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from api.persistence.chat_settings import (
    DEFAULT_CHAT_SETTINGS,
    get_chat_settings_row,
    update_chat_settings_row,
)
from api.utils.ttl_cache import TtlCache

# Short-lived process cache for hot chat paths; cleared on update.
_SETTINGS_CACHE: TtlCache[dict[str, Any]] = TtlCache(ttl_sec=5.0)


@dataclass(frozen=True)
class ChatSettings:
    show_raw_reasoning: bool = False
    show_raw_tool_io: bool = False
    show_thought_chain: bool = True
    memory_enabled: bool = True
    num_history_runs: int = 5
    session_summaries_enabled: bool = True
    add_datetime_to_context: bool = True
    max_tool_calls_from_history: int | None = None
    default_tool_call_limit: int | None = None
    enable_agentic_memory: bool = False
    markdown: bool = True


def _clamp_history_runs(value: object) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 5
    return max(0, min(50, number))


def _optional_positive_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return min(500, number)


def _project_settings(row: Mapping[str, object]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, default in DEFAULT_CHAT_SETTINGS.items():
        raw = row.get(key, default)
        if key in {
            "show_raw_reasoning",
            "show_raw_tool_io",
            "show_thought_chain",
            "memory_enabled",
            "session_summaries_enabled",
            "add_datetime_to_context",
            "enable_agentic_memory",
            "markdown",
        }:
            payload[key] = bool(raw if raw is not None else default)
        elif key == "num_history_runs":
            payload[key] = _clamp_history_runs(
                raw if raw is not None else default
            )
        else:
            payload[key] = _optional_positive_int(raw)
    return payload


async def get_chat_settings() -> dict[str, Any]:
    cached = _SETTINGS_CACHE.get()
    if cached is not None:
        return dict(cached)
    row = await get_chat_settings_row()
    projected = _project_settings(row)
    _SETTINGS_CACHE.set(projected)
    return dict(projected)


async def get_chat_settings_async() -> ChatSettings:
    values = await get_chat_settings()
    return ChatSettings(
        show_raw_reasoning=bool(values["show_raw_reasoning"]),
        show_raw_tool_io=bool(values["show_raw_tool_io"]),
        show_thought_chain=bool(values["show_thought_chain"]),
        memory_enabled=bool(values["memory_enabled"]),
        num_history_runs=int(values["num_history_runs"]),
        session_summaries_enabled=bool(values["session_summaries_enabled"]),
        add_datetime_to_context=bool(values["add_datetime_to_context"]),
        max_tool_calls_from_history=values.get("max_tool_calls_from_history"),
        default_tool_call_limit=values.get("default_tool_call_limit"),
        enable_agentic_memory=bool(values["enable_agentic_memory"]),
        markdown=bool(values["markdown"]),
    )


async def update_chat_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key in DEFAULT_CHAT_SETTINGS:
        if key not in values:
            continue
        raw = values[key]
        if key in {
            "show_raw_reasoning",
            "show_raw_tool_io",
            "show_thought_chain",
            "memory_enabled",
            "session_summaries_enabled",
            "add_datetime_to_context",
            "enable_agentic_memory",
            "markdown",
        }:
            allowed[key] = bool(raw)
        elif key == "num_history_runs":
            allowed[key] = _clamp_history_runs(raw)
        elif key in {"max_tool_calls_from_history", "default_tool_call_limit"}:
            allowed[key] = _optional_positive_int(raw)
    if not allowed:
        return await get_chat_settings()
    row = await update_chat_settings_row(allowed)
    projected = _project_settings(row)
    _SETTINGS_CACHE.set(projected)
    return dict(projected)


def resolve_tool_call_limit(
    profile_limit: object,
    settings: ChatSettings | Mapping[str, Any] | None,
) -> int | None:
    """Profile limit wins; else Settings default_tool_call_limit; else None."""
    if profile_limit is not None:
        try:
            return max(1, int(str(profile_limit)))
        except (TypeError, ValueError):
            pass
    if settings is None:
        return None
    if isinstance(settings, ChatSettings):
        return settings.default_tool_call_limit
    return _optional_positive_int(settings.get("default_tool_call_limit"))


__all__ = [
    "ChatSettings",
    "get_chat_settings",
    "get_chat_settings_async",
    "resolve_tool_call_limit",
    "update_chat_settings",
]
