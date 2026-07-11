from __future__ import annotations

from typing import Any

from api.persistence.cves import search_cve_rows


async def search_cves(
    query: str,
    source: str | None = None,
    page: int = 1,
    size: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Search CVEs, or return the most recently ingested entries when query is blank."""
    return await search_cve_rows(
        query=query,
        source=source,
        page=page,
        size=size,
    )
