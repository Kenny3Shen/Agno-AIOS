from __future__ import annotations

from typing import Any

from api.persistence.cves import search_cve_rows


async def search_cves(
    query: str,
    source: str | None = None,
    page: int = 1,
    size: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Search CVEs by CVE ID or description."""
    return await search_cve_rows(
        query=query,
        source=source,
        page=page,
        size=size,
    )
