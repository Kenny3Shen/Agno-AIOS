from fastapi import APIRouter
from api.models.schemas import CveSearchRequest
from api.services.cve_service import search_cves, search_keywords
from loguru import logger

router = APIRouter(prefix="/api/cve", tags=["CVE"])


@router.post("/search")
async def search_cve(request: CveSearchRequest) -> dict:
    """Search CVEs by ID or keyword with pagination
    
    - 如果提供 cve_id，则按 CVE 编号搜索
    - 如果提供 keyword，则按描述关键字搜索
    - 两者都为空时返回错误
    """
    try:
        if request.cve_id and request.cve_id.strip():
            # 按 CVE 编号搜索
            items, total = await search_cves(request.cve_id.strip(), request.page, request.size)
        elif request.keyword and request.keyword.strip():
            # 按关键字搜索
            items, total = await search_keywords(request.keyword.strip(), request.page, request.size)
        else:
            return {"status": 400, "message": "请提供 CVE 编号或关键字"}
        
        return {
            "status": 200,
            "items": items,
            "total": total,
            "page": request.page,
            "size": request.size,
        }
    except Exception as e:
        logger.error(f"搜索 CVE 错误: {e}")
        return {"status": 400, "message": f"错误:{e}"}

