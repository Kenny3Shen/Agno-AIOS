"""Runtime + Settings UI access for Agno input guardrails."""

from __future__ import annotations

from typing import Any, Mapping

from api.persistence.guardrail_settings import (
    get_guardrail_settings_row,
    update_guardrail_settings_row,
)
from api.utils.ttl_cache import TtlCache

_SETTINGS_CACHE: TtlCache[dict[str, Any]] = TtlCache(ttl_sec=5.0)

_ALLOWED_KEYS = frozenset(
    {
        "enabled",
        "pii_enabled",
        "pii_mask",
        "pii_check_email",
        "pii_check_phone",
        "prompt_injection_enabled",
    }
)


def invalidate_guardrail_settings_cache() -> None:
    _SETTINGS_CACHE.clear()
    try:
        from api.services import guardrails as guardrails_mod

        guardrails_mod._EFFECTIVE_CACHE.clear()
    except Exception:  # noqa: BLE001
        pass


def _publish_effective(projected: dict[str, Any]) -> None:
    """Keep Agent-construction sync cache in lockstep with Settings API cache."""
    _SETTINGS_CACHE.set(projected)
    try:
        from api.services import guardrails as guardrails_mod

        guardrails_mod._EFFECTIVE_CACHE.set(projected)
    except Exception:  # noqa: BLE001
        pass


async def get_guardrail_settings() -> dict[str, Any]:
    cached = _SETTINGS_CACHE.get()
    if cached is not None:
        return dict(cached)
    row = await get_guardrail_settings_row()
    projected = {key: bool(row.get(key)) for key in _ALLOWED_KEYS}
    _publish_effective(projected)
    return dict(projected)


async def update_guardrail_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key in _ALLOWED_KEYS:
        if key in values and values[key] is not None:
            allowed[key] = bool(values[key])
    if not allowed:
        return await get_guardrail_settings()
    row = await update_guardrail_settings_row(allowed)
    projected = {key: bool(row.get(key)) for key in _ALLOWED_KEYS}
    _publish_effective(projected)
    return dict(projected)
