"""IP blacklist threat-intel API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import ADMIN_SCOPE
from api.auth.models import User
from api.auth.scopes import require_scope
from api.persistence.ip_blacklist import search_ip_blacklist_rows
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.tasks.update_ip_blacklist import (
    IpBlacklistUpdateAlreadyRunningError,
    update_ip_blacklist,
)
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/ip-blacklist", tags=["IP Blacklist"])


class IpBlacklistSearchRequest(BaseModel):
    query: str = ""
    source: str | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)


def _sse_payload(event: str, data: Mapping[str, Any]) -> dict[str, str]:
    return {
        "event": event,
        "data": json.dumps(dict(data), ensure_ascii=False, default=str),
    }


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("first_seen", "last_seen", "updated_at", "created_at"):
        value = out.get(key)
        if value is not None and hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    return out


@router.post("/search")
async def search_ip_blacklist(
    request: IpBlacklistSearchRequest,
    _user: User = Depends(require_scope("ip_blacklist:read")),
) -> dict:
    """Search IP/CIDR indicators with Agno-style ``data`` / ``meta`` pagination."""
    try:
        items, total = await search_ip_blacklist_rows(
            query=request.query,
            source=request.source,
            page=request.page,
            size=request.size,
        )
        return {
            "data": [_serialize_row(item) for item in items],
            "meta": pagination_meta(
                page=request.page, limit=request.size, total_count=total
            ),
        }
    except Exception as exc:
        logger.error("搜索 IP 黑名单错误: {}", exc)
        raise HTTPException(status_code=400, detail=f"错误:{exc}") from exc


@router.post("/update")
async def update_ip_blacklist_database(
    request: Request,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
    stream: bool = Query(False, description="Stream stage progress as SSE"),
):
    """更新 IP 黑名单库（管理员）。``stream=true`` 时以 SSE 推送进度。"""
    if stream:
        return await _update_stream(request, user)

    try:
        logger.info("开始更新 IP 黑名单")
        add_count, del_count = await update_ip_blacklist()
        await record_audit_event_async(
            user,
            action="admin.ip_blacklist.update",
            resource_type="ip_blacklist",
            resource_id="database",
            metadata={"add_count": add_count, "del_count": del_count},
            **audit_request_context(request),
        )
        return {
            "message": "IP 黑名单更新完成",
            "add_count": add_count,
            "del_count": del_count,
        }
    except IpBlacklistUpdateAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("更新 IP 黑名单失败")
        await record_audit_event_async(
            user,
            action="admin.ip_blacklist.update",
            resource_type="ip_blacklist",
            resource_id="database",
            status="failure",
            metadata={"error": str(exc)},
            **audit_request_context(request),
        )
        raise HTTPException(status_code=500, detail=f"更新失败: {exc}") from exc


async def _update_stream(request: Request, user: User) -> EventSourceResponse:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_progress(payload: dict[str, Any]) -> None:
        await queue.put(payload)

    async def worker() -> None:
        try:
            add_count, del_count = await update_ip_blacklist(progress=on_progress)
            await record_audit_event_async(
                user,
                action="admin.ip_blacklist.update",
                resource_type="ip_blacklist",
                resource_id="database",
                metadata={"add_count": add_count, "del_count": del_count, "stream": True},
                **audit_request_context(request),
            )
        except IpBlacklistUpdateAlreadyRunningError as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "code": 409,
                    "error": str(exc),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("流式更新 IP 黑名单失败")
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "error": str(exc),
                }
            )
            await record_audit_event_async(
                user,
                action="admin.ip_blacklist.update",
                resource_type="ip_blacklist",
                resource_id="database",
                status="failure",
                metadata={"error": str(exc), "stream": True},
                **audit_request_context(request),
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker(), name="ip-blacklist-update-stream")

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    break
                yield _sse_payload("progress", item)
                if item.get("stage") == "done":
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    return EventSourceResponse(
        event_generator(),
        headers={"Cache-Control": "no-cache"},
        sep="\n",
    )
