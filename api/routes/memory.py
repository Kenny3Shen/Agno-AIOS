from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from api.auth.claims import has_scope
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.users import current_active_user
from api.services.memory_service import (
    MemoryMutationNotFound,
    delete_memory_record,
    get_memory_payload,
    update_memory_record,
)
from api.services.security_policy import (
    PolicyAuditEvent,
    record_policy_event,
)

router = APIRouter(prefix="/api/memory", tags=["Memory"])


class MemoryUpdateRequest(BaseModel):
    user_id: str | None = None
    memory: str = Field(..., min_length=1)
    topics: list[str] = Field(default_factory=list)


def require_memory_write_permission(
    user: User = Depends(current_active_user),
) -> User:
    if not has_scope(user, "memories:write"):
        raise HTTPException(status_code=403, detail="权限不足")
    return user


def require_memory_delete_permission(
    user: User = Depends(current_active_user),
) -> User:
    if not has_scope(user, "memories:delete"):
        raise HTTPException(status_code=403, detail="权限不足")
    return user


@router.get("")
async def get_memory(
    user_id: str | None = None,
    topic: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
    user: User = Depends(require_scope("memories:read")),
):
    try:
        return await get_memory_payload(
            actor=user,
            user_id=user_id,
            topic=topic,
            search=search,
            page=page,
            limit=limit,
        )
    except Exception as exc:
        logger.error(f"获取 Agno memory 失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load memory") from exc


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Request,
    user_id: str | None = None,
    user: User = Depends(require_memory_delete_permission),
):
    try:
        result = await delete_memory_record(user, memory_id=memory_id, user_id=user_id)
    except MemoryMutationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"删除 Agno memory 失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete memory") from exc
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="memory.delete",
            resource_type="memory",
            resource_id=memory_id,
            metadata={"user_id": result.get("user_id", "")},
        ),
        request,
    )
    return result


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: str,
    body: MemoryUpdateRequest,
    request: Request,
    user: User = Depends(require_memory_write_permission),
):
    try:
        result = await update_memory_record(
            user,
            memory_id=memory_id,
            user_id=body.user_id,
            memory=body.memory,
            topics=body.topics,
        )
    except MemoryMutationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"更新 Agno memory 失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update memory") from exc
    result_topics = result.get("topics")
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="memory.update",
            resource_type="memory",
            resource_id=memory_id,
            metadata={
                "user_id": result.get("user_id", ""),
                "topics": len(result_topics) if isinstance(result_topics, list) else 0,
            },
        ),
        request,
    )
    return result
