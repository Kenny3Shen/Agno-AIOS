import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Literal
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
    rename_session,
)
from api.services.audit_service import (
    AuditRequestContext,
    audit_request_context,
    record_audit_event_async,
)
from api.services.security_run_runtime import (
    SecurityRunRequest,
    cancel_security_run,
    stream_security_run,
)
from api.services.model_config_service import get_model_for_run
from api.services.chat_settings_service import get_chat_settings
from api.services.tracing_service import mark_trace_error
from loguru import logger

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str
    model_id: str | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high", "max"] | None = None
    search_knowledge: bool = True
    live_search: bool | None = None


class SessionRenameRequest(BaseModel):
    title: str


def _validate_reasoning_effort(
    reasoning_effort: str,
    model_config: dict[str, object],
) -> None:
    from api.services.model_capabilities import capabilities_for, resolve_reasoning_effort

    provider = str(model_config.get("provider") or "openai-compatible")
    protocol = str(model_config.get("api_protocol") or "chat-completions")
    model_id = str(model_config.get("model_id") or "")
    caps = capabilities_for(provider, api_protocol=protocol, model_id=model_id)
    if not caps.supports_reasoning_effort:
        # xAI: reasoning is model-id based; ignore client effort quietly is worse than 422
        # for explicit misuse — return clear message.
        if caps.reasoning_via_model_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "xAI 不支持 reasoning_effort 参数；请改用推理/非推理型号 "
                    "（例如 grok-*-reasoning vs *-non-reasoning）。"
                ),
            )
        raise HTTPException(
            status_code=422,
            detail="当前模型供应商不支持 reasoning_effort。",
        )
    resolved = resolve_reasoning_effort(
        provider=provider,
        api_protocol=protocol,
        model_id=model_id,
        override=reasoning_effort,
    )
    if resolved != reasoning_effort:
        raise HTTPException(
            status_code=422,
            detail=(
                f"当前 {provider} {protocol} 模型不支持 reasoning_effort={reasoning_effort}；"
                f"可用: {', '.join(caps.reasoning_efforts)}。"
            ),
        )


async def _event_generator(
    run_request: SecurityRunRequest,
    *,
    actor: User | None = None,
    request_context: AuditRequestContext | None = None,
):
    terminal_status = "success"
    resource_id = run_request.session_id or ""
    failed_run_id = ""
    try:
        async for event in stream_security_run(run_request):
            run_id = str(event.data.get("run_id") or "")
            if run_id:
                resource_id = run_id
            if event.event == "run.failed":
                terminal_status = "error"
                if run_id:
                    failed_run_id = run_id
            elif event.event == "run.cancelled":
                terminal_status = "cancelled"
            yield {"event": event.event, "data": json.dumps(event.data, ensure_ascii=False)}
        if failed_run_id:
            await mark_trace_error(failed_run_id)
        if actor is not None:
            await record_audit_event_async(
                actor,
                action="chat.run",
                resource_type="chat_run",
                resource_id=resource_id,
                status=terminal_status,
                metadata={
                    "model_id": run_request.model_id or "",
                    "message_length": len(run_request.message),
                    "reasoning_effort": run_request.reasoning_effort or "",
                },
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
                metadata={
                    "model_id": run_request.model_id or "",
                    "reasoning_effort": run_request.reasoning_effort or "",
                    "error": detail,
                },
                ip_address=request_context["ip_address"] if request_context else "",
                user_agent=request_context["user_agent"] if request_context else "",
            )
        yield {"event": "run.failed", "data": json.dumps({"run_id": "", "code": "CHAT_STREAM_ERROR", "message": detail, "retryable": True}, ensure_ascii=False)}


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
        if request.reasoning_effort is not None:
            model_config = await get_model_for_run(request.model_id)
            _validate_reasoning_effort(request.reasoning_effort, model_config)
        chat_settings = await get_chat_settings()
        run_request = SecurityRunRequest.from_chat_args(
            request.message,
            session_id=request.session_id,
            model_id=request.model_id,
            reasoning_effort=request.reasoning_effort,
            user_id=actor_id(user),
            knowledge_owner_user_id=None
            if has_scope(user, ADMIN_SCOPE)
            else actor_id(user),
            memory_enabled=chat_settings["memory_enabled"],
            store_raw_tool_io=chat_settings["show_raw_tool_io"],
            search_knowledge=request.search_knowledge,
            live_search=request.live_search,
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


@router.post("/chat/runs/{run_id}/cancel")
async def cancel_chat_run(
    run_id: str,
    user: User = Depends(require_scope("sessions:write")),
):
    """Cancel a live Agno run owned by the current user."""
    if not cancel_security_run(user_id=actor_id(user), run_id=run_id):
        raise HTTPException(status_code=404, detail="运行不存在或已结束")
    await record_audit_event_async(
        user,
        action="chat.run.cancel",
        resource_type="chat_run",
        resource_id=run_id,
    )
    return {"success": True, "run_id": run_id}


@router.get("/chat/sessions")
async def list_sessions(
    include_runs: bool = False,
    include_archived: bool = False,
    user_id: str | None = None,
    page: int = 1,
    limit: int = 100,
    user: User = Depends(require_scope("sessions:read")),
):
    """List chat sessions as Agno-style ``{data, meta}``."""
    try:
        owner_user_id = scope_user_id(user, user_id)
        return await get_all_sessions_async(
            owner_user_id=owner_user_id,
            include_runs=include_runs,
            include_archived=include_archived,
            page=page,
            limit=limit,
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


@router.patch("/chat/sessions/{session_id}")
async def rename_chat_session(
    session_id: str,
    body: SessionRenameRequest,
    user: User = Depends(require_scope("sessions:write")),
):
    try:
        result = await rename_session(session_id, body.title, actor=user)
        if result is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
