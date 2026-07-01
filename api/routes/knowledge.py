from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth.models import User
from api.auth.permissions import require_permission
from api.services.audit_service import record_audit_event
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
    search_type: str | None = Field(
        default=None,
        description="vector / keyword / hybrid，默认使用 AGNO_KNOWLEDGE_SEARCH_TYPE",
    )


@router.get("")
async def get_knowledge_status(_user: User = Depends(require_permission("knowledge:read"))) -> dict:
    return {"status": knowledge_status(), "documents": list_documents()}


@router.post("/documents/text")
async def create_text_document(
    request: KnowledgeTextRequest,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    try:
        result = add_text_document(
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=request.metadata,
        )
        record_audit_event(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or request.title),
            metadata={"source": request.source},
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/documents/file")
async def create_file_document(
    request: KnowledgeFileRequest,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    try:
        result = add_file_document(path=request.path, title=request.title)
        record_audit_event(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or request.title or request.path),
            metadata={"path": request.path},
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}")
async def remove_document(
    doc_id: str,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="知识文档不存在")
    record_audit_event(
        user,
        action="knowledge.delete",
        resource_type="knowledge_document",
        resource_id=doc_id,
    )
    return {"success": True}


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    _user: User = Depends(require_permission("knowledge:read")),
) -> dict:
    try:
        return {
            "results": search_documents(
                request.query,
                request.limit,
                search_type=request.search_type,
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("")
async def clear_knowledge(user: User = Depends(require_permission("knowledge:write"))) -> dict:
    result = clear_knowledge_base()
    record_audit_event(
        user,
        action="knowledge.clear",
        resource_type="knowledge",
    )
    return result
