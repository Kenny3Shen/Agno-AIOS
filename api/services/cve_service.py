from api.database.cve_db import (
    search_cves_by_id_paginated,
    search_cves_by_description_paginated,
)


async def search_cves(cve_id: str, page: int, size: int) -> tuple[list[dict], int]:
    """Search CVEs by ID with pagination"""
    items, total = await search_cves_by_id_paginated(cve_id, page, size)
    return items, total


async def search_keywords(keyword: str, page: int, size: int) -> tuple[list[dict], int]:
    """Search CVEs by keyword in description with pagination"""
    items, total = await search_cves_by_description_paginated(keyword, page, size)
    return items, total
