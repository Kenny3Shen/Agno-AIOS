from api.database.cve_db import search_cves_by_id_paginated


async def search_cves(cve_id: str, page: int, size: int) -> tuple[list[dict], int]:
    """Search CVEs by ID with pagination"""
    items, total = await search_cves_by_id_paginated(cve_id, page, size)
    return items, total
