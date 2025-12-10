from fastapi import APIRouter
from api.models.schemas import CveSearchRequest
from api.services.cve_service import search_cves
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
