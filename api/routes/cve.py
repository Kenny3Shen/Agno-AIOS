from fastapi import APIRouter, Depends
import aiomysql
from api.dependencies import get_pool
from api.models.schemas import CveSearchRequest
from api.services.cve_service import search_cves_by_description, search_cves_by_id
from update_cve import main as update_cve_main
from loguru import logger

router = APIRouter(prefix="/api/cve", tags=["CVE"])


@router.post("/search")
async def search_cve(
    request: CveSearchRequest, pool: aiomysql.Pool = Depends(get_pool)
) -> dict:
    """Search CVEs by ID or keyword with pagination"""

    try:
        if request.cve_id:
            items, total = await search_cves_by_id(
                pool, request.cve_id, request.page, request.size, request.source
            )
        elif request.keyword:
            items, total = await search_cves_by_description(
                pool, request.keyword, request.page, request.size, request.source
            )

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


@router.post("/update")
async def update_cve_database():
    """更新 CVE 数据库"""
    try:
        logger.info("开始更新 CVE 数据库")
        # 异步运行更新任务
        add_count, del_count = await update_cve_main()
        logger.info("CVE 数据库更新完成")
        return {
            "status": 200,
            "message": "CVE 数据库更新完成",
            "add_count": add_count,
            "del_count": del_count,
        }
    except Exception as e:
        logger.error(f"更新 CVE 数据库错误: {e}")
        return {"status": 500, "message": f"更新失败: {e}"}
