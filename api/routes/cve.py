from typing import Any

from fastapi import APIRouter, Depends, Request
from psycopg_pool import AsyncConnectionPool

from api.auth.models import User
from api.auth.permissions import require_permission
from api.dependencies import get_pool
from api.models.schemas import CveSearchRequest
from api.services.audit_service import audit_request_context, record_audit_event
from api.services.cve_service import search_cves
from api.tasks.update_cve import main as update_cve_main
from loguru import logger

router = APIRouter(prefix="/api/cve", tags=["CVE"])


@router.post("/search")
async def search_cve(
    request: CveSearchRequest,
    pool: AsyncConnectionPool[Any] = Depends(get_pool),
    _user: User = Depends(require_permission("cve:read")),
) -> dict:
    """Search CVEs by ID and/or keyword with pagination"""
    try:
        items, total = await search_cves(
            pool,
            query=request.query,
            source=request.source,
            page=request.page,
            size=request.size,
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
async def update_cve_database(
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    """更新 CVE 数据库"""
    try:
        logger.info("开始更新 CVE 数据库")
        # 异步运行更新任务
        add_count, del_count = await update_cve_main()
        record_audit_event(
            user,
            action="admin.cve.update",
            resource_type="cve",
            resource_id="database",
            metadata={"add_count": add_count, "del_count": del_count},
            **audit_request_context(request),
        )
        logger.info("CVE 数据库更新完成")
        return {
            "status": 200,
            "message": "CVE 数据库更新完成",
            "add_count": add_count,
            "del_count": del_count,
        }
    except Exception as e:
        logger.error(f"更新 CVE 数据库错误: {e}")
        record_audit_event(
            user,
            action="admin.cve.update",
            resource_type="cve",
            resource_id="database",
            status="failure",
            metadata={"error": str(e)},
            **audit_request_context(request),
        )
        return {"status": 500, "message": f"更新失败: {e}"}
