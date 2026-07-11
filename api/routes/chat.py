from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.auth.models import User
from api.auth.claims import ADMIN_SCOPE, actor_id, has_scope, scope_user_id
from api.auth.ownership import assert_owned_resource
from api.auth.scopes import require_scope
from api.services.chat_session_service import (
    archive_session,
    get_all_sessions_async,
    get_session_messages_async,
    get_session_owner_async,
)
from api.services.audit_service import (
    AuditRequestContext,
    audit_request_context,
    record_audit_event_async,
)
from api.services.security_run_runtime import SecurityRunRequest, stream_security_run
from loguru import logger

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model_id: str | None = None


async def _event_generator(
    run_request: SecurityRunRequest,
    *,
    actor: User | None = None,
    request_context: AuditRequestContext | None = None,
):
    try:
        async for chunk in stream_security_run(run_request):
            if chunk:
                yield {"data": chunk}
        yield {"data": "[DONE]"}
        if actor is not None:
            await record_audit_event_async(
                actor,
                action="chat.run",
                resource_type="chat_session",
                resource_id=run_request.session_id or "",
                metadata={"model_id": run_request.model_id or "", "message_length": len(run_request.message)},
                ip_address=request_context["ip_address"] if request_context else "",
                user_agent=request_context["user_agent"] if request_context else "",
            )
    except Exception as exc:
        detail = _exception_detail(exc)
        logger.exception("处理聊天错误: {}", detail)
        if actor is not None:
            await record_audit_event_async(
                actor,
                action="chat.run",
                resource_type="chat_session",
                resource_id=run_request.session_id or "",
                status="error",
                metadata={"model_id": run_request.model_id or "", "error": detail},
                ip_address=request_context["ip_address"] if request_context else "",
                user_agent=request_context["user_agent"] if request_context else "",
            )
        yield {"event": "error", "data": detail}


def _exception_detail(exc: BaseException) -> str:
    current = exc
    while isinstance(current, BaseExceptionGroup) and current.exceptions:
        current = current.exceptions[0]
    return f"{type(current).__name__}: {current}"


@router.post("/chat")
async def chat_agent(
    request: ChatRequest,
    raw_request: Request,
    user: User = Depends(require_scope("sessions:write")),
):
    """使用 LLM 处理聊天消息（流式）"""
    try:
        if request.session_id:
            owner_user_id = await get_session_owner_async(request.session_id)
            if owner_user_id is not None:
                assert_owned_resource(
                    user,
                    owner_user_id=owner_user_id,
                    resource_name="Session",
                )
        run_request = SecurityRunRequest.from_chat_args(
            request.message,
            session_id=request.session_id,
            model_id=request.model_id,
            user_id=actor_id(user),
            knowledge_owner_user_id=None
            if has_scope(user, ADMIN_SCOPE)
            else actor_id(user),
        )
        return EventSourceResponse(
            _event_generator(
                run_request,
                actor=user,
                request_context=audit_request_context(raw_request),
            ),
            headers={"Cache-Control": "no-cache"},
            sep="\n",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理聊天错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions")
async def list_sessions(
    include_runs: bool = False,
    include_archived: bool = False,
    user: User = Depends(require_scope("sessions:read")),
):
    """获取所有聊天会话列表"""
    try:
        owner_user_id = scope_user_id(user, None)
        return await get_all_sessions_async(
            owner_user_id=owner_user_id,
            include_runs=include_runs,
            include_archived=include_archived,
        )
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: User = Depends(require_scope("sessions:read")),
):
    """获取指定会话的聊天记录"""
    try:
        return await get_session_messages_async(session_id, actor=user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/sessions/{session_id}")
async def remove_session(
    session_id: str,
    user: User = Depends(require_scope("sessions:write")),
):
    """归档指定会话；不删除 Agno runs/traces。"""
    try:
        success = await archive_session(session_id, actor=user)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"success": True, "archived": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"归档会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
