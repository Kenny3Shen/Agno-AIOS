from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from api.persistence.chat_settings import (
    DEFAULT_CHAT_SETTINGS,
    get_chat_settings_row,
    memory_flags_from_mode,
    memory_mode_from_flags,
    normalize_memory_mode,
    update_chat_settings_row,
)
from api.utils.ttl_cache import TtlCache

# Short-lived process cache for hot chat paths; cleared on update.
_SETTINGS_CACHE: TtlCache[dict[str, Any]] = TtlCache(ttl_sec=5.0)

MemoryMode = str  # "off" | "automatic" | "agentic"


@dataclass(frozen=True)
class ChatSettings:
    show_raw_reasoning: bool = False
    show_raw_tool_io: bool = False
    show_thought_chain: bool = True
    memory_mode: str = "automatic"
    memory_enabled: bool = True
    num_history_runs: int = 5
    session_summaries_enabled: bool = True
    add_datetime_to_context: bool = True
    max_tool_calls_from_history: int | None = None
    default_tool_call_limit: int | None = None
    enable_agentic_memory: bool = False
    markdown: bool = True
    memory_tool_content_enabled: bool = False
    memory_prune_enabled: bool = True
    memory_prune_retention_days: int = 90
    memory_prune_top_k: int = 50
    memory_inject_enabled: bool = True
    memory_inject_top_k: int = 12
    memory_inject_window_days: int = 90
    memory_inject_dedupe_topics: bool = True


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


def _clamp_prune_retention_days(value: object) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 90
    return max(1, min(3650, number))


def _clamp_prune_top_k(value: object) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 50
    return max(1, min(500, number))


def _clamp_inject_top_k(value: object) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 12
    return max(1, min(100, number))


def _clamp_inject_window_days(value: object) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 90
    # 0 = disable time-window filter on inject.
    return max(0, min(3650, number))


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
            "memory_tool_content_enabled",
            "memory_prune_enabled",
            "memory_inject_enabled",
            "memory_inject_dedupe_topics",
        }:
            payload[key] = bool(raw if raw is not None else default)
        elif key == "memory_mode":
            payload[key] = normalize_memory_mode(
                raw if raw is not None else default
            )
        elif key == "num_history_runs":
            payload[key] = _clamp_history_runs(
                raw if raw is not None else default
            )
        elif key == "memory_prune_retention_days":
            payload[key] = _clamp_prune_retention_days(
                raw if raw is not None else default
            )
        elif key == "memory_prune_top_k":
            payload[key] = _clamp_prune_top_k(
                raw if raw is not None else default
            )
        elif key == "memory_inject_top_k":
            payload[key] = _clamp_inject_top_k(
                raw if raw is not None else default
            )
        elif key == "memory_inject_window_days":
            payload[key] = _clamp_inject_window_days(
                raw if raw is not None else default
            )
        else:
            payload[key] = _optional_positive_int(raw)
    # Keep mode and legacy bools aligned (mode wins when both present).
    if "memory_mode" in row or "memory_mode" in payload:
        mode = normalize_memory_mode(payload.get("memory_mode"))
        enabled, agentic = memory_flags_from_mode(mode)
        payload["memory_mode"] = mode
        payload["memory_enabled"] = enabled
        payload["enable_agentic_memory"] = agentic
    else:
        mode = memory_mode_from_flags(
            memory_enabled=bool(payload.get("memory_enabled", True)),
            enable_agentic_memory=bool(payload.get("enable_agentic_memory", False)),
        )
        payload["memory_mode"] = mode
        enabled, agentic = memory_flags_from_mode(mode)
        payload["memory_enabled"] = enabled
        payload["enable_agentic_memory"] = agentic
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
    mode = normalize_memory_mode(values.get("memory_mode"))
    enabled, agentic = memory_flags_from_mode(mode)
    return ChatSettings(
        show_raw_reasoning=bool(values["show_raw_reasoning"]),
        show_raw_tool_io=bool(values["show_raw_tool_io"]),
        show_thought_chain=bool(values["show_thought_chain"]),
        memory_mode=mode,
        memory_enabled=enabled,
        num_history_runs=int(values["num_history_runs"]),
        session_summaries_enabled=bool(values["session_summaries_enabled"]),
        add_datetime_to_context=bool(values["add_datetime_to_context"]),
        max_tool_calls_from_history=values.get("max_tool_calls_from_history"),
        default_tool_call_limit=values.get("default_tool_call_limit"),
        enable_agentic_memory=agentic,
        markdown=bool(values["markdown"]),
        memory_tool_content_enabled=bool(values["memory_tool_content_enabled"]),
        memory_prune_enabled=bool(values["memory_prune_enabled"]),
        memory_prune_retention_days=int(values["memory_prune_retention_days"]),
        memory_prune_top_k=int(values["memory_prune_top_k"]),
        memory_inject_enabled=bool(values["memory_inject_enabled"]),
        memory_inject_top_k=int(values["memory_inject_top_k"]),
        memory_inject_window_days=int(values["memory_inject_window_days"]),
        memory_inject_dedupe_topics=bool(values["memory_inject_dedupe_topics"]),
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
            "memory_tool_content_enabled",
            "memory_prune_enabled",
            "memory_inject_enabled",
            "memory_inject_dedupe_topics",
        }:
            allowed[key] = bool(raw)
        elif key == "memory_mode":
            allowed[key] = normalize_memory_mode(raw)
        elif key == "num_history_runs":
            allowed[key] = _clamp_history_runs(raw)
        elif key == "memory_prune_retention_days":
            allowed[key] = _clamp_prune_retention_days(raw)
        elif key == "memory_prune_top_k":
            allowed[key] = _clamp_prune_top_k(raw)
        elif key == "memory_inject_top_k":
            allowed[key] = _clamp_inject_top_k(raw)
        elif key == "memory_inject_window_days":
            allowed[key] = _clamp_inject_window_days(raw)
        elif key in {"max_tool_calls_from_history", "default_tool_call_limit"}:
            allowed[key] = _optional_positive_int(raw)
    # Prefer explicit memory_mode over dual switches when both are sent.
    if "memory_mode" in allowed:
        enabled, agentic = memory_flags_from_mode(str(allowed["memory_mode"]))
        allowed["memory_enabled"] = enabled
        allowed["enable_agentic_memory"] = agentic
    elif "memory_enabled" in allowed or "enable_agentic_memory" in allowed:
        current = await get_chat_settings()
        enabled = bool(allowed.get("memory_enabled", current["memory_enabled"]))
        agentic = bool(
            allowed.get("enable_agentic_memory", current["enable_agentic_memory"])
        )
        mode = memory_mode_from_flags(
            memory_enabled=enabled, enable_agentic_memory=agentic
        )
        allowed["memory_mode"] = mode
        enabled, agentic = memory_flags_from_mode(mode)
        allowed["memory_enabled"] = enabled
        allowed["enable_agentic_memory"] = agentic
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
