import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Literal
from sse_starlette.sse import EventSourceResponse

from api.auth.models import User
from api.auth.claims import ADMIN_SCOPE, actor_id, has_scope, scope_user_id
from api.auth.ownership import assert_owned_resource
from api.auth.scopes import require_scope
from api.services.chat_session_service import (
    archive_session,
    unarchive_session,
    list_sessions_async,
    get_session_messages_async,
    get_session_owner_async,
    get_session_summary_async,
    rename_session,
)
from api.services.audit_service import (
    AuditRequestContext,
    audit_request_context,
    record_audit_event_async,
)
from api.services.agent_catalog import list_chat_agents, resolve_chat_run_target
from api.services.team_runtime import list_chat_teams, team_feature_enabled
from api.services.security_run_runtime import (
    SecurityRunRequest,
    cancel_security_run,
    stream_security_run,
)
from api.services.chat_media import process_chat_uploads
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
    enable_tools: bool = True
    agent_id: str | None = None


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


def _parse_optional_bool(value: object, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return default
    text = value.strip().lower()
    if text in {"", "null", "none"}:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise HTTPException(status_code=422, detail=f"Invalid boolean: {value}")


async def _start_chat_stream(
    *,
    message: str,
    session_id: str,
    model_id: str | None,
    reasoning_effort: str | None,
    search_knowledge: bool,
    live_search: bool | None,
    enable_tools: bool,
    agent_id: str | None = None,
    media_images: tuple = (),
    media_files: tuple = (),
    media_audio: tuple = (),
    media_videos: tuple = (),
    attachments: tuple = (),
    user: User,
    raw_request: Request,
):
    if not message.strip() and not (media_images or media_files or media_audio or media_videos):
        raise HTTPException(status_code=422, detail="消息或附件不能同时为空")
    if session_id:
        owner_user_id = await get_session_owner_async(session_id)
        if owner_user_id is not None:
            assert_owned_resource(
                user,
                owner_user_id=owner_user_id,
                resource_name="Session",
            )
    if reasoning_effort is not None:
        model_config = await get_model_for_run(model_id)
        _validate_reasoning_effort(reasoning_effort, model_config)
    chat_settings = await get_chat_settings()
    # Empty message with media only: give the model a short instruction.
    text = message.strip() or "请根据附件内容进行分析。"
    run_request = SecurityRunRequest.from_chat_args(
        text,
        session_id=session_id,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
        user_id=actor_id(user),
        knowledge_owner_user_id=None
        if has_scope(user, ADMIN_SCOPE)
        else actor_id(user),
        memory_enabled=chat_settings["memory_enabled"],
        store_raw_tool_io=chat_settings["show_raw_tool_io"],
        search_knowledge=search_knowledge,
        live_search=live_search,
        enable_tools=enable_tools,
        agent_id=agent_id,
        images=media_images,
        files=media_files,
        audio=media_audio,
        videos=media_videos,
        attachments=attachments,
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



@router.get("/chat/agents")
async def chat_agents(user: User = Depends(require_scope("sessions:write"))):
    """Built-in Chat agent (+ optional Team) catalog."""
    _ = user
    data = list_chat_agents()
    if team_feature_enabled():
        data = [*data, *list_chat_teams()]
    return {
        "data": data,
        "meta": {"team_enabled": team_feature_enabled()},
    }


@router.post("/chat")
async def chat_agent(
    raw_request: Request,
    user: User = Depends(require_scope("sessions:write")),
):
    """Chat SSE: JSON body or multipart form (Agno-style ``files`` uploads)."""
    try:
        content_type = (raw_request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in content_type:
            form = await raw_request.form()
            message = str(form.get("message") or "")
            session_id = str(form.get("session_id") or "").strip()
            if not session_id:
                raise HTTPException(status_code=422, detail="session_id is required")
            model_raw = form.get("model_id")
            model_id = str(model_raw).strip() if model_raw not in (None, "") else None
            effort_raw = form.get("reasoning_effort")
            reasoning_effort = (
                str(effort_raw).strip() if effort_raw not in (None, "") else None  # type: ignore[assignment]
            )
            if reasoning_effort is not None and reasoning_effort not in {
                "minimal",
                "low",
                "medium",
                "high",
                "max",
            }:
                raise HTTPException(status_code=422, detail="Invalid reasoning_effort")
            search_knowledge = _parse_optional_bool(form.get("search_knowledge"), True)  # type: ignore[arg-type]
            live_search = _parse_optional_bool(form.get("live_search"), None)  # type: ignore[arg-type]
            enable_tools = _parse_optional_bool(form.get("enable_tools"), True)  # type: ignore[arg-type]
            agent_raw = form.get("agent_id")
            if agent_raw not in (None, ""):
                _kind, agent_id = resolve_chat_run_target(str(agent_raw).strip())
            else:
                agent_id = None
            assert search_knowledge is not None and enable_tools is not None
            uploads: list[Any] = []
            for key in ("files", "file"):
                for item in form.getlist(key):
                    if hasattr(item, "filename") and hasattr(item, "read"):
                        uploads.append(item)
            bundle = await process_chat_uploads(uploads or None)  # type: ignore[arg-type]
            return await _start_chat_stream(
                message=message,
                session_id=session_id,
                model_id=model_id,
                reasoning_effort=reasoning_effort,
                search_knowledge=search_knowledge,
                live_search=live_search,
                enable_tools=enable_tools,
                agent_id=agent_id,
                media_images=bundle.images,
                media_files=bundle.files,
                media_audio=bundle.audio,
                media_videos=bundle.videos,
                attachments=bundle.attachments,
                user=user,
                raw_request=raw_request,
            )

        body = await raw_request.json()
        request = ChatRequest.model_validate(body)
        return await _start_chat_stream(
            message=request.message,
            session_id=request.session_id,
            model_id=request.model_id,
            reasoning_effort=request.reasoning_effort,
            search_knowledge=request.search_knowledge,
            live_search=request.live_search,
            enable_tools=request.enable_tools,
            agent_id=request.agent_id,
            user=user,
            raw_request=raw_request,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("处理聊天错误: {}", e)
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
    archived_only: bool = False,
    user_id: str | None = None,
    page: int = 1,
    limit: int = 40,
    q: str | None = None,
    user: User = Depends(require_scope("sessions:read")),
):
    """List chat sessions as Agno-style ``{data, meta}``."""
    try:
        owner_user_id = scope_user_id(user, user_id)
        return await list_sessions_async(
            owner_user_id=owner_user_id,
            include_runs=include_runs,
            include_archived=include_archived,
            archived_only=archived_only,
            page=page,
            limit=limit,
            q=q,
        )
    except Exception as e:
        logger.error("获取会话列表失败: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}/meta")
async def get_session_meta(
    session_id: str,
    user: User = Depends(require_scope("sessions:read")),
):
    """Return one session list projection for deep-link headers and redirects."""
    try:
        result = await get_session_summary_async(session_id, actor=user)
        if result is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取会话摘要失败: {}", e)
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
        logger.error("获取会话记录失败: {}", e)
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
        logger.error("归档会话失败: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/sessions/{session_id}/unarchive")
async def unarchive_chat_session(
    session_id: str,
    user: User = Depends(require_scope("sessions:write")),
):
    """恢复已归档会话到最近列表。"""
    try:
        success = await unarchive_session(session_id, actor=user)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"success": True, "archived": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("恢复归档会话失败: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
