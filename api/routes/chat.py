from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from api.services.llm_service import stream_chat_with_agent
from loguru import logger

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str


def _format_sse(data: str) -> str:
    lines = data.splitlines() or [""]
    return "".join(f"data: {line}\n" for line in lines) + "\n"


async def _event_generator(message: str):
    try:
        async for chunk in stream_chat_with_agent(message):
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
            _event_generator(request.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception as e:
        logger.error(f"处理聊天错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

