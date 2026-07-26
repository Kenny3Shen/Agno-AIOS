"""Build a cheap Agno MemoryManager shared by Chat / Team runtimes.

P0/P1 goals:
- Prefer a lower-cost model for memory extraction (not the chat leader model).
- Strict capture instructions (preferences only; SOC IOE blocked).
- Optional tool-content capture + inject-side ranking filter.
- Agentic memory is Settings-gated via memory_mode (not dual switches).
"""

from __future__ import annotations

from typing import Any

from agno.memory import MemoryManager
from loguru import logger

from api.services.memory_capture import memory_capture_instructions
from api.services.model_config_service import (
    get_memory_model_id,
    get_model_for_run,
    load_model_config_store,
)
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db

# Prefer these model config ids (or substrings of model_id) for MemoryManager
# when Settings has not pinned a dedicated memory model.
_CHEAP_MODEL_PREFERENCE: tuple[str, ...] = (
    "flash",
    "mini",
    "lite",
    "haiku",
)


async def resolve_memory_manager_model_config(
    preferred_model_id: str | None = None,
) -> dict[str, Any]:
    """Resolve MemoryManager model: explicit pin → Settings pin → cheap auto-pick."""
    # 1) Caller override (tests / special paths).
    if preferred_model_id:
        try:
            return await get_model_for_run(preferred_model_id)
        except Exception:
            logger.debug(
                "memory manager preferred model {} unavailable; scanning store",
                preferred_model_id,
                exc_info=True,
            )

    # 2) Settings → 模型连接「设为 MemoryManager」.
    pinned = await get_memory_model_id()
    if pinned:
        try:
            return await get_model_for_run(pinned)
        except Exception:
            logger.warning(
                "configured memory_model_id={} unavailable; falling back to auto-pick",
                pinned,
                exc_info=True,
            )

    # 3) Auto-pick a lower-cost enabled, fully configured model.  An
    # incomplete draft must never break an otherwise runnable Chat/Workflow
    # session merely because it sorts ahead of the active connection.
    store = await load_model_config_store()
    models = list(store.models or [])
    candidates = [
        model
        for model in models
        if getattr(model, "enabled", True) and getattr(model, "configured", False)
    ]

    def _score(model: Any) -> tuple[int, str]:
        mid = str(getattr(model, "id", "") or "").lower()
        model_id = str(getattr(model, "model_id", "") or "").lower()
        blob = f"{mid} {model_id}"
        for rank, needle in enumerate(_CHEAP_MODEL_PREFERENCE):
            if needle in blob:
                return (rank, mid)
        return (len(_CHEAP_MODEL_PREFERENCE) + 10, mid)

    if candidates:
        best = min(candidates, key=_score)
        return await get_model_for_run(best.id)
    return await get_model_for_run(None)


async def build_memory_manager(
    *,
    tool_content_enabled: bool = False,
    model_id: str | None = None,
    db: Any | None = None,
    inject_config: Any | None = None,
    inject_query: str = "",
    agent_id: str | None = None,
) -> MemoryManager:
    """Construct a MemoryManager with a cheap model and P0/P1-safe tool flags.

    When *inject_config* enables inject-side ranking, returns a thin subclass
    that filters ``get_user_memories`` / ``aget_user_memories`` (Agno injects
    every memory returned by those methods into the system prompt).
    """
    config = await resolve_memory_manager_model_config(model_id)
    model = build_agno_model(config)
    database = db if db is not None else get_async_agno_postgres_db()
    kwargs: dict[str, Any] = {
        "model": model,
        "db": database,
        "memory_capture_instructions": memory_capture_instructions(
            tool_content_enabled=tool_content_enabled,
            agent_id=agent_id,
        ),
        # Safety: agentic / automatic managers must not wipe or free-delete.
        "delete_memories": False,
        "clear_memories": False,
        "update_memories": True,
        "add_memories": True,
        "name": "tais-memory-manager",
    }
    from api.services.memory_inject_service import (
        MemoryInjectConfig,
        memory_inject_config_from_settings,
        select_memories_for_inject,
    )

    cfg: MemoryInjectConfig | None
    if inject_config is None:
        cfg = None
    elif isinstance(inject_config, MemoryInjectConfig):
        cfg = inject_config
    else:
        cfg = memory_inject_config_from_settings(inject_config)

    if cfg is None or not cfg.enabled:
        return MemoryManager(**kwargs)

    query = str(inject_query or "")

    class _InjectFilteredMemoryManager(MemoryManager):
        """Filter memories returned for Agno context injection only."""

        def get_user_memories(self, user_id: str | None = None) -> Any:
            raw = super().get_user_memories(user_id=user_id)
            if not raw:
                return raw
            return select_memories_for_inject(raw, query=query, config=cfg)

        async def aget_user_memories(self, user_id: str | None = None) -> Any:
            raw = await super().aget_user_memories(user_id=user_id)
            if not raw:
                return raw
            return select_memories_for_inject(raw, query=query, config=cfg)

    return _InjectFilteredMemoryManager(**kwargs)


async def capture_tool_content_memories(
    *,
    memory_manager: MemoryManager,
    user_id: str,
    agent_id: str | None,
    tool_summaries: list[str],
) -> None:
    """Optional second-pass memory write from truncated tool result summaries."""
    owner = str(user_id or "").strip()
    if not owner or owner in {"anonymous", "default"}:
        logger.warning("skip tool-content memory write: fail-closed missing user_id")
        return
    from api.services.memory_capture import is_soc_memory_profile

    if is_soc_memory_profile(agent_id):
        # SOC: never second-pass tool dumps into user memory (IOE / IOC risk).
        logger.info(
            "skip tool-content memory write for SOC agent_id={}",
            agent_id,
        )
        return
    messages_payload: list[str] = []
    for raw in tool_summaries:
        text = str(raw or "").strip()
        if not text:
            continue
        # Hard cap each tool snippet to keep MemoryManager prompts bounded.
        if len(text) > 2_000:
            text = text[:2_000] + "…"
        messages_payload.append(text)
    if not messages_payload:
        return
    from agno.models.message import Message

    messages = [
        Message(
            role="user",
            content=(
                "The following tool results were observed in this run. "
                "Extract durable user preferences only if warranted; "
                "do not store one-off investigation artifacts:\n\n"
                + "\n---\n".join(messages_payload)
            ),
        )
    ]
    await memory_manager.acreate_user_memories(
        messages=messages,
        user_id=owner,
        agent_id=agent_id,
    )


__all__ = [
    "build_memory_manager",
    "capture_tool_content_memories",
    "memory_capture_instructions",
    "resolve_memory_manager_model_config",
]
