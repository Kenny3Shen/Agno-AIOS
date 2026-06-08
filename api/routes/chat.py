from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from api.services.llm_service import (
    stream_chat_with_agent,
    get_all_sessions,
    get_session_messages,
    delete_session,
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
    message: str, session_id: str | None = None, model_id: str | None = None
):
    try:
        async for chunk in stream_chat_with_agent(message, session_id, model_id):
            if chunk:
                yield _format_sse(chunk)
        yield _format_sse("[DONE]")
    except Exception as e:
        logger.error(f"处理聊天错误: {e}")
        yield "event: error\n" + _format_sse(str(e))


@router.post("/chat")
async def chat_agent(request: ChatRequest):
    """使用 LLM 处理聊天消息（流式）"""
    try:
        return StreamingResponse(
            _event_generator(request.message, request.session_id, request.model_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception as e:
        logger.error(f"处理聊天错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions")
async def list_sessions():
    """获取所有聊天会话列表"""
    try:
        return get_all_sessions()
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """获取指定会话的聊天记录"""
    try:
        return get_session_messages(session_id)
    except Exception as e:
        logger.error(f"获取会话记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/sessions/{session_id}")
async def remove_session(session_id: str):
    """删除指定会话"""
    try:
        success = delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
