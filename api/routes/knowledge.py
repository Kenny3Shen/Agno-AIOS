from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services.knowledge_service import (
    add_file_document,
    add_text_document,
    clear_knowledge_base,
    delete_document,
    knowledge_status,
    list_documents,
    search_documents,
)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


class KnowledgeTextRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: str = "manual"
    metadata: dict[str, str] = Field(default_factory=dict)


class KnowledgeFileRequest(BaseModel):
    path: str = Field(..., min_length=1)
    title: str | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(5, ge=1, le=20)


@router.get("")
async def get_knowledge_status() -> dict:
    return {"status": knowledge_status(), "documents": list_documents()}


@router.post("/documents/text")
async def create_text_document(request: KnowledgeTextRequest) -> dict:
    try:
        return add_text_document(
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=request.metadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/documents/file")
async def create_file_document(request: KnowledgeFileRequest) -> dict:
    try:
        return add_file_document(path=request.path, title=request.title)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str) -> dict:
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="知识文档不存在")
    return {"success": True}


@router.post("/search")
async def search_knowledge(request: KnowledgeSearchRequest) -> dict:
    return {"results": search_documents(request.query, request.limit)}


@router.delete("")
async def clear_knowledge() -> dict:
    return clear_knowledge_base()
