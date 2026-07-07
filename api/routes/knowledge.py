from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth.models import User
from api.auth.claims import actor_id, scope_user_id
from api.auth.scopes import require_scope
from api.auth.visibility import can_manage_resource
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.knowledge_service import get_knowledge_base_lifecycle

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


def effective_knowledge_user_filter(user: User) -> str | None:
    return scope_user_id(user, None)


def with_manage_flags(documents: list[dict], user: User) -> list[dict]:
    flagged: list[dict] = []
    for document in documents:
        metadata = {
            **(document.get("metadata") or {}),
            "visibility": document.get("visibility"),
            "owner_user_id": document.get("owner_user_id"),
        }
        flagged.append({**document, "can_manage": can_manage_resource(user, metadata)})
    return flagged


class KnowledgeTextRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: str = "manual"
    metadata: dict[str, str] = Field(default_factory=dict)
    visibility: str = "private"


class KnowledgeFileRequest(BaseModel):
    path: str = Field(..., min_length=1)
    title: str | None = None
    visibility: str = "private"


class KnowledgeVisibilityRequest(BaseModel):
    visibility: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(5, ge=1, le=20)
    search_type: str | None = Field(
        default=None,
        description="vector / keyword / hybrid，默认使用 AGNO_KNOWLEDGE_SEARCH_TYPE",
    )


@router.get("")
async def get_knowledge_status(user: User = Depends(require_scope("knowledge:read"))) -> dict:
    owner_user_id = effective_knowledge_user_filter(user)
    knowledge_base = get_knowledge_base_lifecycle()
    documents = await knowledge_base.list_documents_async(owner_user_id=owner_user_id)
    return {
        "status": await knowledge_base.knowledge_status_async(
            owner_user_id=owner_user_id,
            documents=documents,
        ),
        "documents": with_manage_flags(documents, user),
    }


@router.post("/documents/text")
async def create_text_document(
    request_ctx: Request,
    request: KnowledgeTextRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> dict:
    try:
        result = await get_knowledge_base_lifecycle().add_text_document_async(
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=request.metadata,
            owner_user_id=actor_id(user),
            visibility=request.visibility,
        )
        result["can_manage"] = True
        await record_audit_event_async(
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
    user: User = Depends(require_scope("knowledge:write")),
) -> dict:
    try:
        result = await get_knowledge_base_lifecycle().add_file_document_async(
            path=request.path,
            title=request.title,
            owner_user_id=actor_id(user),
            visibility=request.visibility,
        )
        result["can_manage"] = True
        await record_audit_event_async(
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
    user: User = Depends(require_scope("knowledge:delete")),
) -> dict:
    deleted = await get_knowledge_base_lifecycle().delete_document_async(
        doc_id,
        owner_user_id=effective_knowledge_user_filter(user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    await record_audit_event_async(
        user,
        action="knowledge.delete",
        resource_type="knowledge_document",
        resource_id=doc_id,
        **audit_request_context(request_ctx),
    )
    return {"success": True}


@router.put("/documents/{doc_id}/visibility")
async def update_document_visibility(
    request_ctx: Request,
    doc_id: str,
    request: KnowledgeVisibilityRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> dict:
    try:
        updated = await get_knowledge_base_lifecycle().update_document_visibility_async(
            doc_id,
            request.visibility,
            user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    updated["can_manage"] = True
    await record_audit_event_async(
        user,
        action="knowledge.visibility_update",
        resource_type="knowledge_document",
        resource_id=doc_id,
        metadata={"visibility": request.visibility},
        **audit_request_context(request_ctx),
    )
    return updated


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    user: User = Depends(require_scope("knowledge:read")),
) -> dict:
    try:
        return {
            "results": await get_knowledge_base_lifecycle().search_documents_async(
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
    user: User = Depends(require_scope("knowledge:delete")),
) -> dict:
    result = await get_knowledge_base_lifecycle().clear_knowledge_base_async(
        owner_user_id=effective_knowledge_user_filter(user),
    )
    await record_audit_event_async(
        user,
        action="knowledge.clear",
        resource_type="knowledge",
        **audit_request_context(request_ctx),
    )
    return result
