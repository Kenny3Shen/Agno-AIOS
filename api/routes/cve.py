from fastapi import APIRouter
from api.models.schemas import CveSearchRequest
from api.services.cve_service import search_cves, refresh_cve_database
from loguru import logger

router = APIRouter(prefix="/api/cve", tags=["CVE"])


@router.post("/search")
async def search_cve(request: CveSearchRequest) -> dict:
    """Search CVEs by ID with pagination"""
    try:
        items, total = await search_cves(request.cve_id, request.page, request.size)
        return {
            "status": 200,
            "items": items,
            "total": total,
            "page": request.page,
            "size": request.size,
        }
    except Exception as e:
        logger.error(f"Error searching CVEs: {e}")
        return {"status": 400, "message": f"error:{e}"}


@router.post("/refresh")
async def refresh_cve_db():
    """Refresh CVE database from remote source"""
    try:
        new_count, deleted_count = await refresh_cve_database()
        return {
            "status": 200,
            "message": "Database refresh completed.",
            "new_count": new_count,
            "del_count": deleted_count,
        }
    except Exception as e:
        logger.error(f"Error refreshing CVE database: {e}")
        return {"status": 400, "message": f"error:{e}"}
