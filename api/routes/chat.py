from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth.models import User
from api.auth.permissions import actor_id, assert_owned_resource, has_permission, require_permission
from api.services.llm_service import (
    stream_chat_with_agent,
    get_all_sessions,
    get_session_owner,
    get_session_messages,
    archive_session,
)
from loguru import logger

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model_id: str | None = None


def _format_sse(data: str) -> str:
    lines = data.splitlines() or [""]
    return "".join(f"data: {line}\n" for line in lines) + "\n"


async def _event_generator(
    message: str,
    session_id: str | None = None,
    model_id: str | None = None,
    user_id: str | None = None,
    knowledge_owner_user_id: str | None = None,
):
    try:
        async for chunk in stream_chat_with_agent(
            message,
            session_id,
            model_id,
            user_id,
            knowledge_owner_user_id=knowledge_owner_user_id,
        ):
            if chunk:
                yield _format_sse(chunk)
        yield _format_sse("[DONE]")
    except Exception as e:
        logger.error(f"处理聊天错误: {e}")
        yield "event: error\n" + _format_sse(str(e))


@router.post("/chat")
async def chat_agent(
    request: ChatRequest,
    user: User = Depends(require_permission("session:write:own")),
):
    """使用 LLM 处理聊天消息（流式）"""
    try:
        if request.session_id:
            owner_user_id = get_session_owner(request.session_id)
            if owner_user_id is not None:
                assert_owned_resource(
                    user,
                    owner_user_id=owner_user_id,
                    resource_name="Session",
                )
        return StreamingResponse(
            _event_generator(
                request.message,
                request.session_id,
                request.model_id,
                actor_id(user),
                None if has_permission(user, "knowledge:read:any") else actor_id(user),
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理聊天错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions")
async def list_sessions(user: User = Depends(require_permission("session:read:own"))):
    """获取所有聊天会话列表"""
    try:
        owner_user_id = None if has_permission(user, "session:read:any") else actor_id(user)
        return get_all_sessions(owner_user_id=owner_user_id)
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: User = Depends(require_permission("session:read:own")),
):
    """获取指定会话的聊天记录"""
    try:
        return get_session_messages(session_id, actor=user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/sessions/{session_id}")
async def remove_session(
    session_id: str,
    user: User = Depends(require_permission("session:write:own")),
):
    """归档指定会话；不删除 Agno runs/traces。"""
    try:
        success = archive_session(session_id, actor=user)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"success": True, "archived": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"归档会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
