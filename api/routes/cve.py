from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import ADMIN_SCOPE
from api.auth.models import User
from api.auth.scopes import require_scope
from api.models.schemas import CveSearchRequest
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.cve_service import search_cves
from api.tasks.update_cve import (
    CVEUpdateAlreadyRunningError,
    main as update_cve_main,
)
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/cve", tags=["CVE"])


def _sse_payload(event: str, data: Mapping[str, Any]) -> dict[str, str]:
    return {
        "event": event,
        "data": json.dumps(dict(data), ensure_ascii=False, default=str),
    }


@router.post("/search")
async def search_cve(
    request: CveSearchRequest,
    _user: User = Depends(require_scope("cve:read")),
) -> dict:
    """Search CVEs by ID and/or keyword with Agno-style ``data`` / ``meta`` pagination."""
    try:
        items, total = await search_cves(
            query=request.query,
            source=request.source,
            page=request.page,
            size=request.size,
        )
        return {
            "data": items,
            "meta": pagination_meta(page=request.page, limit=request.size, total_count=total),
        }
    except Exception as e:
        logger.error("搜索 CVE 错误: {}", e)
        raise HTTPException(status_code=400, detail=f"错误:{e}") from e


@router.post("/update")
async def update_cve_database(
    request: Request,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
    stream: bool = Query(False, description="Stream stage progress as SSE"),
):
    """更新 CVE 数据库。

    默认同步返回新增/删除计数；``stream=true`` 时以 SSE 推送阶段进度。
    """
    if stream:
        return await _update_cve_stream(request, user)

    try:
        logger.info("开始更新 CVE 数据库")
        add_count, del_count = await update_cve_main()
        await record_audit_event_async(
            user,
            action="admin.cve.update",
            resource_type="cve",
            resource_id="database",
            metadata={"add_count": add_count, "del_count": del_count},
            **audit_request_context(request),
        )
        logger.info("CVE 数据库更新完成")
        return {
            "message": "CVE 数据库更新完成",
            "add_count": add_count,
            "del_count": del_count,
        }
    except CVEUpdateAlreadyRunningError as e:
        logger.warning("CVE update rejected: {}", e)
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        logger.error("更新 CVE 数据库错误: {}", e)
        await record_audit_event_async(
            user,
            action="admin.cve.update",
            resource_type="cve",
            resource_id="database",
            status="failure",
            metadata={"error": str(e)},
            **audit_request_context(request),
        )
        raise HTTPException(status_code=500, detail=f"更新失败: {e}") from e


async def _update_cve_stream(request: Request, user: User) -> EventSourceResponse:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_progress(event: Mapping[str, Any]) -> None:
        await queue.put(dict(event))

    async def worker() -> None:
        add_count = 0
        del_count = 0
        try:
            add_count, del_count = await update_cve_main(on_progress=on_progress)
            await record_audit_event_async(
                user,
                action="admin.cve.update",
                resource_type="cve",
                resource_id="database",
                metadata={"add_count": add_count, "del_count": del_count, "stream": True},
                **audit_request_context(request),
            )
        except CVEUpdateAlreadyRunningError as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 409,
                }
            )
        except asyncio.CancelledError:
            logger.info("CVE streamed update cancelled")
            raise
        except Exception as exc:
            logger.exception("CVE streamed update failed: {}", exc)
            await record_audit_event_async(
                user,
                action="admin.cve.update",
                resource_type="cve",
                resource_id="database",
                status="failure",
                metadata={"error": str(exc), "stream": True},
                **audit_request_context(request),
            )
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 500,
                }
            )
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(worker(), name="cve-update-progress")
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                stage = str(item.get("stage") or "")
                status = str(item.get("status") or "")
                if stage == "done":
                    event_name = (
                        "progress.completed" if status == "completed" else "progress.failed"
                    )
                    yield _sse_payload(event_name, item)
                    break
                event_name = "progress.failed" if status == "failed" else "progress"
                yield _sse_payload(event_name, item)
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("CVE update worker cancelled after client disconnect")

    return EventSourceResponse(event_generator())
