from fastapi import APIRouter
from api.models.schemas import CveSearchRequest
from api.services.cve_service import search_cves_by_description, search_cves_by_id
from update_cve import main as update_cve_main
from loguru import logger

router = APIRouter(prefix="/api/cve", tags=["CVE"])


@router.post("/search")
async def search_cve(request: CveSearchRequest) -> dict:
    """Search CVEs by ID or keyword with pagination

    - 如果提供 cve_id，则按 CVE 编号搜索
    - 如果提供 keyword，则按描述关键字搜索
    - 如果提供 source，则添加来源过滤
    - 两者都为空时返回错误
    """
    try:
        source = request.source.strip() if request.source else None
        if request.cve_id and request.cve_id.strip():
            # 按 CVE 编号搜索
            items, total = await search_cves_by_id(
                request.cve_id.strip(), request.page, request.size, source
            )
        elif request.keyword and request.keyword.strip():
            # 按关键字搜索
            items, total = await search_cves_by_description(
                request.keyword.strip(), request.page, request.size, source
            )
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
