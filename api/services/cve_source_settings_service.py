"""Settings-page and CVE-worker access to source enablement toggles."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from api.persistence.cve_source_settings import (
    get_cve_source_enabled_map,
    update_cve_source_enabled_map,
)


def _source_names(source_names: Iterable[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for source_name in source_names:
        source = str(source_name).strip()
        if source and source not in seen:
            names.append(source)
            seen.add(source)
    return names


async def get_cve_source_settings(source_names: Iterable[str]) -> list[dict[str, Any]]:
    """Return UI-ready source records in the configured source order."""
    names = _source_names(source_names)
    enabled_by_source = await get_cve_source_enabled_map(names)
    return [
        {"source": source, "enabled": bool(enabled_by_source.get(source, True))}
        for source in names
    ]


async def update_cve_source_settings(
    values: Mapping[str, bool],
    source_names: Iterable[str],
) -> list[dict[str, Any]]:
    """Validate and persist source toggles, returning the UI-ready full list."""
    names = _source_names(source_names)
    enabled_by_source = await update_cve_source_enabled_map(values, names)
    return [
        {"source": source, "enabled": bool(enabled_by_source.get(source, True))}
        for source in names
    ]


async def get_enabled_cve_source_names(source_names: Iterable[str]) -> list[str]:
    """Return only enabled sources, preserving the configured order."""
    names = _source_names(source_names)
    enabled_by_source = await get_cve_source_enabled_map(names)
    return [source for source in names if enabled_by_source.get(source, True)]
