"""Shared Agno-style list pagination meta helpers."""

from __future__ import annotations

from typing import Any


def pagination_meta(
    *,
    page: int,
    limit: int,
    total_count: int,
    search_time_ms: float = 0.0,
) -> dict[str, Any]:
    """Build ``meta`` for Agno-native ``{data, meta}`` list responses."""
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, int(limit or 1))
    total = max(0, int(total_count or 0))
    total_pages = (total + safe_limit - 1) // safe_limit if total else 0
    return {
        "page": safe_page,
        "limit": safe_limit,
        "total_pages": total_pages,
        "total_count": total,
        "search_time_ms": float(search_time_ms or 0.0),
    }
