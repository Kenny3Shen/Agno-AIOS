from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth.models import User
from api.auth.permissions import actor_id, has_permission, require_permission
from api.services.audit_service import audit_request_context, record_audit_event
from api.services.knowledge_service import get_knowledge_base_lifecycle

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


def effective_knowledge_user_filter(user: User) -> str | None:
    if has_permission(user, "knowledge:read:any"):
        return None
    return actor_id(user)


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
async def get_knowledge_status(user: User = Depends(require_permission("knowledge:read"))) -> dict:
    owner_user_id = effective_knowledge_user_filter(user)
    knowledge_base = get_knowledge_base_lifecycle()
    return {
        "status": knowledge_base.knowledge_status(owner_user_id=owner_user_id),
        "documents": knowledge_base.list_documents(owner_user_id=owner_user_id),
    }


@router.post("/documents/text")
async def create_text_document(
    request_ctx: Request,
    request: KnowledgeTextRequest,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    try:
        result = get_knowledge_base_lifecycle().add_text_document(
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=request.metadata,
            owner_user_id=actor_id(user),
        )
        record_audit_event(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or request.title),
            metadata={"source": request.source},
            **audit_request_context(request_ctx),
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/documents/file")
async def create_file_document(
    request_ctx: Request,
    request: KnowledgeFileRequest,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    try:
        result = get_knowledge_base_lifecycle().add_file_document(
            path=request.path,
            title=request.title,
            owner_user_id=actor_id(user),
        )
        record_audit_event(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or request.title or request.path),
            metadata={"path": request.path},
            **audit_request_context(request_ctx),
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}")
async def remove_document(
    request_ctx: Request,
    doc_id: str,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    deleted = get_knowledge_base_lifecycle().delete_document(
        doc_id,
        owner_user_id=effective_knowledge_user_filter(user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    record_audit_event(
        user,
        action="knowledge.delete",
        resource_type="knowledge_document",
        resource_id=doc_id,
        **audit_request_context(request_ctx),
    )
    return {"success": True}


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    user: User = Depends(require_permission("knowledge:read")),
) -> dict:
    try:
        return {
            "results": get_knowledge_base_lifecycle().search_documents(
                request.query,
                request.limit,
                search_type=request.search_type,
                owner_user_id=effective_knowledge_user_filter(user),
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("")
async def clear_knowledge(
    request_ctx: Request,
    user: User = Depends(require_permission("knowledge:write")),
) -> dict:
    result = get_knowledge_base_lifecycle().clear_knowledge_base(
        owner_user_id=effective_knowledge_user_filter(user),
    )
    record_audit_event(
        user,
        action="knowledge.clear",
        resource_type="knowledge",
        **audit_request_context(request_ctx),
    )
    return result
