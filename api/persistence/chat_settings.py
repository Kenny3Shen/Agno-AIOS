from __future__ import annotations

from api.utils.async_once import AsyncOnce

from time import time
from typing import Any, Mapping

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current

MEMORY_MODES = frozenset({"off", "automatic", "agentic"})

CHAT_SETTINGS_TABLE = "chat_settings"
GLOBAL_CHAT_SETTINGS_ID = "global"

# Workbench privacy toggles + Agno Agent runtime knobs (history / memory / tools).
# Integer fields use None for "use profile default / unlimited".
DEFAULT_CHAT_SETTINGS: dict[str, Any] = {
    "show_raw_reasoning": False,
    "show_raw_tool_io": False,
    "show_thought_chain": True,
    # Unified memory mode (Settings radio). Legacy bools are derived on read/write.
    "memory_mode": "automatic",
    "memory_enabled": True,
    # Agno: num_history_runs — past runs injected into context (docs recommend 3–5).
    "num_history_runs": 5,
    # Agno: enable_session_summaries + add_session_summary_to_context.
    "session_summaries_enabled": True,
    # Agno: add_datetime_to_context.
    "add_datetime_to_context": True,
    # Agno: max_tool_calls_from_history (None = no extra filter).
    "max_tool_calls_from_history": None,
    # Global tool_call_limit when agent profile does not set one (None = profile).
    "default_tool_call_limit": None,
    # Agno: enable_agentic_memory (takes precedence over update_memory_on_run).
    "enable_agentic_memory": False,
    # Agno: markdown response formatting.
    "markdown": True,
    # Memory P0: allow MemoryManager / agentic memory to capture tool-derived facts.
    "memory_tool_content_enabled": False,
    # Memory P0 prune job (durable): delete by updated_at age, then keep top-k per user.
    "memory_prune_enabled": True,
    "memory_prune_retention_days": 90,
    "memory_prune_top_k": 50,
    # Memory P1 inject: score + cap before Agno dumps memories into system prompt.
    "memory_inject_enabled": True,
    "memory_inject_top_k": 12,
    "memory_inject_max_chars": 2000,
    "memory_inject_window_days": 90,
    "memory_inject_dedupe_topics": True,
}

_BOOL_KEYS = frozenset(
    {
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
    }
)
_INT_KEYS = frozenset(
    {
        "num_history_runs",
        "max_tool_calls_from_history",
        "default_tool_call_limit",
        "memory_prune_retention_days",
        "memory_prune_top_k",
        "memory_inject_top_k",
        "memory_inject_max_chars",
        "memory_inject_window_days",
    }
)
_STR_KEYS = frozenset({"memory_mode"})


def normalize_memory_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode in MEMORY_MODES:
        return mode
    return "automatic"


def memory_flags_from_mode(mode: str) -> tuple[bool, bool]:
    """Return (memory_enabled, enable_agentic_memory) for a memory_mode value."""
    normalized = normalize_memory_mode(mode)
    if normalized == "off":
        return False, False
    if normalized == "agentic":
        return True, True
    return True, False


def memory_mode_from_flags(*, memory_enabled: bool, enable_agentic_memory: bool) -> str:
    if not memory_enabled:
        return "off"
    if enable_agentic_memory:
        return "agentic"
    return "automatic"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def chat_settings_table(metadata: MetaData | None = None) -> Table:
    return Table(
        CHAT_SETTINGS_TABLE,
        metadata or MetaData(schema=_app_schema()),
        Column("id", String(32), primary_key=True),
        Column("show_raw_reasoning", Boolean, nullable=False, server_default="false"),
        Column("show_raw_tool_io", Boolean, nullable=False, server_default="false"),
        Column("show_thought_chain", Boolean, nullable=False, server_default="true"),
        Column("memory_enabled", Boolean, nullable=False, server_default="true"),
        Column(
            "memory_mode",
            String(16),
            nullable=False,
            server_default="automatic",
        ),
        Column(
            "session_summaries_enabled",
            Boolean,
            nullable=False,
            server_default="true",
        ),
        Column(
            "add_datetime_to_context",
            Boolean,
            nullable=False,
            server_default="true",
        ),
        Column(
            "enable_agentic_memory",
            Boolean,
            nullable=False,
            server_default="false",
        ),
        Column("markdown", Boolean, nullable=False, server_default="true"),
        Column("num_history_runs", Integer, nullable=False, server_default="5"),
        Column("max_tool_calls_from_history", Integer, nullable=True),
        Column("default_tool_call_limit", Integer, nullable=True),
        Column(
            "memory_tool_content_enabled",
            Boolean,
            nullable=False,
            server_default="false",
        ),
        Column(
            "memory_prune_enabled",
            Boolean,
            nullable=False,
            server_default="true",
        ),
        Column(
            "memory_prune_retention_days",
            Integer,
            nullable=False,
            server_default="90",
        ),
        Column(
            "memory_prune_top_k",
            Integer,
            nullable=False,
            server_default="50",
        ),
        Column(
            "memory_inject_enabled",
            Boolean,
            nullable=False,
            server_default="true",
        ),
        Column(
            "memory_inject_top_k",
            Integer,
            nullable=False,
            server_default="12",
        ),
        Column(
            "memory_inject_max_chars",
            Integer,
            nullable=False,
            server_default="2000",
        ),
        Column(
            "memory_inject_window_days",
            Integer,
            nullable=False,
            server_default="90",
        ),
        Column(
            "memory_inject_dedupe_topics",
            Boolean,
            nullable=False,
            server_default="true",
        ),
        Column("updated_at", BigInteger, nullable=False),
    )


_chat_settings_table_once = AsyncOnce()


async def _create_chat_settings_table_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_chat_settings_table_async() -> None:
    await _chat_settings_table_once.run(_create_chat_settings_table_async)


def _project_row(row: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(DEFAULT_CHAT_SETTINGS)
    if not row:
        return payload
    for key in DEFAULT_CHAT_SETTINGS:
        if key not in row:
            continue
        value = row[key]
        if key in _BOOL_KEYS:
            payload[key] = bool(value) if value is not None else DEFAULT_CHAT_SETTINGS[key]
        elif key in _STR_KEYS:
            payload[key] = (
                normalize_memory_mode(value)
                if key == "memory_mode"
                else (str(value) if value is not None else DEFAULT_CHAT_SETTINGS[key])
            )
        elif key in _INT_KEYS:
            if value is None or value == "":
                # Nullable tool limits use None; required memory prune ints keep defaults.
                if key in {
                    "num_history_runs",
                    "memory_prune_retention_days",
                    "memory_prune_top_k",
                    "memory_inject_top_k",
                    "memory_inject_max_chars",
                    "memory_inject_window_days",
                }:
                    payload[key] = DEFAULT_CHAT_SETTINGS[key]
                else:
                    payload[key] = None
            else:
                payload[key] = int(value)
    # Prefer memory_mode when present; keep legacy bools consistent.
    if "memory_mode" in row and row.get("memory_mode") is not None:
        mode = normalize_memory_mode(row.get("memory_mode"))
        enabled, agentic = memory_flags_from_mode(mode)
        payload["memory_mode"] = mode
        payload["memory_enabled"] = enabled
        payload["enable_agentic_memory"] = agentic
    else:
        mode = memory_mode_from_flags(
            memory_enabled=bool(payload["memory_enabled"]),
            enable_agentic_memory=bool(payload["enable_agentic_memory"]),
        )
        payload["memory_mode"] = mode
        enabled, agentic = memory_flags_from_mode(mode)
        payload["memory_enabled"] = enabled
        payload["enable_agentic_memory"] = agentic
    return payload


async def get_chat_settings_row() -> dict[str, Any]:
    await ensure_chat_settings_table_async()
    table = chat_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(table).where(table.c.id == GLOBAL_CHAT_SETTINGS_ID)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            values = {
                "id": GLOBAL_CHAT_SETTINGS_ID,
                **DEFAULT_CHAT_SETTINGS,
                "updated_at": int(time()),
            }
            await conn.execute(insert(table).values(**values))
            return dict(DEFAULT_CHAT_SETTINGS)
    return _project_row(dict(row))


async def update_chat_settings_row(values: Mapping[str, Any]) -> dict[str, Any]:
    current = await get_chat_settings_row()
    updates: dict[str, Any] = {}
    for key, value in values.items():
        if key not in DEFAULT_CHAT_SETTINGS:
            continue
        if key in _BOOL_KEYS:
            updates[key] = bool(value)
        elif key in _STR_KEYS:
            if key == "memory_mode":
                updates[key] = normalize_memory_mode(value)
            else:
                updates[key] = str(value)
        elif key in _INT_KEYS:
            if value is None or value == "":
                if key in {
                    "num_history_runs",
                    "memory_prune_retention_days",
                    "memory_prune_top_k",
                    "memory_inject_top_k",
                    "memory_inject_max_chars",
                    "memory_inject_window_days",
                }:
                    updates[key] = current[key]
                else:
                    updates[key] = None
            else:
                updates[key] = int(value)
    # memory_mode is source of truth when provided; otherwise reconcile from bools.
    if "memory_mode" in updates:
        enabled, agentic = memory_flags_from_mode(str(updates["memory_mode"]))
        updates["memory_enabled"] = enabled
        updates["enable_agentic_memory"] = agentic
    elif "memory_enabled" in updates or "enable_agentic_memory" in updates:
        enabled = bool(
            updates.get("memory_enabled", current.get("memory_enabled", True))
        )
        agentic = bool(
            updates.get(
                "enable_agentic_memory",
                current.get("enable_agentic_memory", False),
            )
        )
        mode = memory_mode_from_flags(
            memory_enabled=enabled, enable_agentic_memory=agentic
        )
        updates["memory_mode"] = mode
        enabled, agentic = memory_flags_from_mode(mode)
        updates["memory_enabled"] = enabled
        updates["enable_agentic_memory"] = agentic
    if not updates:
        return current
    updates["updated_at"] = int(time())
    table = chat_settings_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(
            update(table).where(table.c.id == GLOBAL_CHAT_SETTINGS_ID).values(**updates)
        )
    return {**current, **{k: v for k, v in updates.items() if k != "updated_at"}}
