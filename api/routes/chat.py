from fastapi import APIRouter, HTTPException
from api.models.schemas import ChatRequest, ChatResponse
from api.services.llm_service import chat_with_llm
from loguru import logger

router = APIRouter(prefix="/api", tags=["Chat"])


@router.post("/chat")
async def chat_llm(request: ChatRequest):
    """Process chat message with LLM"""
    try:
        response, sources = await chat_with_llm(request.message)
        return ChatResponse(response=response, sources=sources)
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
