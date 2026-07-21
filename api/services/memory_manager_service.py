"""Build a cheap Agno MemoryManager shared by Chat / Team runtimes.

P0 goals:
- Prefer a lower-cost model for memory extraction (not the chat leader model).
- Optional tool-content capture via ``memory_capture_instructions``.
- Agentic memory stays default-off; delete/clear tools stay off for safety.
"""

from __future__ import annotations

from typing import Any

from agno.memory import MemoryManager
from loguru import logger

from api.services.model_config_service import get_model_for_run, load_model_config_store
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db

# Prefer these model config ids (or substrings of model_id) for MemoryManager.
_CHEAP_MODEL_PREFERENCE: tuple[str, ...] = (
    "deepseek-v4-flash",
    "flash",
    "mini",
    "lite",
    "haiku",
)

_CAPTURE_WITHOUT_TOOLS = """\
Memories should capture durable personal or operational preferences about the user, such as:
- Role, team, preferred language, escalation contacts
- Stable workflow preferences (report format, severity thresholds)
- Significant goals or constraints the user explicitly stated in conversation

Do NOT store:
- Raw tool outputs, MCP payloads, CVE dumps, IP blacklists, or log excerpts
- One-off investigation artifacts (single IPs, temporary case numbers) unless the user
  explicitly asked to remember them
- Secrets, tokens, passwords, webhook URLs, or full message histories
- Casual chatter or temporary states
"""

_CAPTURE_WITH_TOOLS = """\
Memories should capture durable facts about the user and their environment, including:
- Personal / operational preferences stated in conversation
- Stable facts the user confirmed after tool use (e.g. preferred containment playbook,
  recurring asset ownership, standing allow/block policies)
- High-signal tool findings the user asked to retain for future sessions

When tool results are provided, extract only durable, third-person statements.
Do NOT store:
- Full raw tool dumps, multi-page CVE feeds, bulk IP lists, or entire log files
- Secrets, tokens, passwords, or webhook URLs
- Transient run noise (retry counts, stream status, one-off timestamps)
"""


def memory_capture_instructions(*, tool_content_enabled: bool) -> str:
    """Return MemoryManager capture criteria for the current Settings flag."""
    return _CAPTURE_WITH_TOOLS if tool_content_enabled else _CAPTURE_WITHOUT_TOOLS


async def resolve_memory_manager_model_config(
    preferred_model_id: str | None = None,
) -> dict[str, Any]:
    """Pick a cheap model for MemoryManager; fall back to the active chat model."""
    if preferred_model_id:
        try:
            return await get_model_for_run(preferred_model_id)
        except Exception:
            logger.debug(
                "memory manager preferred model {} unavailable; scanning store",
                preferred_model_id,
                exc_info=True,
            )

    store = await load_model_config_store()
    models = list(store.models or [])
    enabled = [m for m in models if getattr(m, "enabled", True)]
    candidates = enabled or models

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
        return best.model_dump()
    return await get_model_for_run(None)


async def build_memory_manager(
    *,
    tool_content_enabled: bool = False,
    model_id: str | None = None,
    db: Any | None = None,
    inject_config: Any | None = None,
    inject_query: str = "",
) -> MemoryManager:
    """Construct a MemoryManager with a cheap model and P0-safe tool flags.

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
            tool_content_enabled=tool_content_enabled
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
                "Extract durable memories only if warranted:\n\n"
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
