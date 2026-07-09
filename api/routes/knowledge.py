from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth.claims import actor_id, scope_user_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.visibility import can_manage_resource
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.knowledge_document_service import KnowledgeDocumentPayload
from api.services.knowledge_service import (
    get_knowledge_base_lifecycle,
    update_rag_settings_async,
)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


class KnowledgeDocumentResponsePayload(KnowledgeDocumentPayload):
    can_manage: bool


def effective_knowledge_user_filter(user: User) -> str | None:
    return scope_user_id(user, None)


def with_manage_flag(document: KnowledgeDocumentPayload, user: User) -> KnowledgeDocumentResponsePayload:
    flagged = cast(
        KnowledgeDocumentResponsePayload,
        {
            **document,
            "can_manage": can_manage_resource(
                user,
                {
                    **document["metadata"],
                    "visibility": document["visibility"],
                    "owner_user_id": document["owner_user_id"],
                },
            ),
        },
    )
    return flagged


def with_manage_flags(
    documents: list[KnowledgeDocumentPayload],
    user: User,
) -> list[KnowledgeDocumentResponsePayload]:
    flagged: list[KnowledgeDocumentResponsePayload] = []
    for document in documents:
        flagged.append(with_manage_flag(document, user))
    return flagged


class KnowledgeIngestOptionsRequest(BaseModel):
    chunk_size: int | None = Field(default=None, ge=200)
    chunk_overlap: int | None = Field(default=None, ge=0)
    code_chunk_size: int | None = Field(default=None, ge=256)
    semantic_threshold: float | None = Field(default=None, ge=0, le=1)
    reader_strategy: str | None = None


class KnowledgeTextRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: str = "manual"
    metadata: dict[str, str] = Field(default_factory=dict)
    visibility: str = "private"
    ingest_options: KnowledgeIngestOptionsRequest | None = None


class KnowledgeFileRequest(BaseModel):
    path: str = Field(..., min_length=1)
    title: str | None = None
    source: str | None = None
    visibility: str = "private"
    ingest_options: KnowledgeIngestOptionsRequest | None = None


class KnowledgeVisibilityRequest(BaseModel):
    visibility: str


class KnowledgeSourceReplacementRequest(BaseModel):
    content: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    title: str | None = None
    source: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    ingest_options: KnowledgeIngestOptionsRequest | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(5, ge=1, le=20)
    search_type: str | None = Field(
        default=None,
        description="vector / keyword / hybrid，默认使用 AGNO_KNOWLEDGE_SEARCH_TYPE",
    )


class KnowledgeRagSettingsRequest(BaseModel):
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)
    rerank_model: str | None = None
    query_prompt: str | None = None
    top_k: int | None = Field(default=None, ge=1)
    chunk_size: int | None = Field(default=None, ge=200)
    chunk_overlap: int | None = Field(default=None, ge=0)
    code_chunk_size: int | None = Field(default=None, ge=256)
    semantic_threshold: float | None = Field(default=None, ge=0, le=1)
    vector_score_weight: float | None = Field(default=None, ge=0, le=1)
    content_language: str | None = None
    prefix_match: bool | None = None
    rerank_enabled: bool | None = None
    rerank_candidate_multiplier: int | None = Field(default=None, ge=1)
    rerank_min_candidates: int | None = Field(default=None, ge=1)
    device: str | None = None
    search_type: str | None = None


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
) -> KnowledgeDocumentResponsePayload:
    try:
        result = await get_knowledge_base_lifecycle().add_text_document_async(
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=request.metadata,
            owner_user_id=actor_id(user),
            visibility=request.visibility,
            ingest_options=(
                request.ingest_options.model_dump(exclude_none=True)
                if request.ingest_options is not None
                else None
            ),
        )
        response = cast(KnowledgeDocumentResponsePayload, {**result, "can_manage": True})
        await record_audit_event_async(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or request.title),
            metadata={"source": request.source},
            **audit_request_context(request_ctx),
        )
        return response
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/documents/file")
async def create_file_document(
    request_ctx: Request,
    request: KnowledgeFileRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    try:
        result = await get_knowledge_base_lifecycle().add_file_document_async(
            path=request.path,
            title=request.title,
            source=request.source,
            owner_user_id=actor_id(user),
            visibility=request.visibility,
            ingest_options=(
                request.ingest_options.model_dump(exclude_none=True)
                if request.ingest_options is not None
                else None
            ),
        )
        response = cast(KnowledgeDocumentResponsePayload, {**result, "can_manage": True})
        await record_audit_event_async(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or request.title or request.path),
            metadata={"path": request.path, "source": request.source or request.path},
            **audit_request_context(request_ctx),
        )
        return response
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


@router.post("/documents/{doc_id}/rebuild")
async def rebuild_document(
    request_ctx: Request,
    doc_id: str,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    try:
        updated = await get_knowledge_base_lifecycle().rebuild_document_async(
            doc_id,
            owner_user_id=effective_knowledge_user_filter(user),
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    response = cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})
    await record_audit_event_async(
        user,
        action="knowledge.rebuild",
        resource_type="knowledge_document",
        resource_id=doc_id,
        **audit_request_context(request_ctx),
    )
    return response


@router.post("/documents/{doc_id}/source")
async def replace_document_source(
    request_ctx: Request,
    doc_id: str,
    request: KnowledgeSourceReplacementRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    try:
        updated = await get_knowledge_base_lifecycle().replace_document_source_async(
            doc_id,
            content=request.content,
            file_name=request.file_name,
            title=request.title,
            source=request.source,
            metadata=request.metadata,
            owner_user_id=effective_knowledge_user_filter(user),
            user=user,
            ingest_options=(
                request.ingest_options.model_dump(exclude_none=True)
                if request.ingest_options is not None
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    response = cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})
    await record_audit_event_async(
        user,
        action="knowledge.source_replace",
        resource_type="knowledge_document",
        resource_id=str(updated.get("id") or doc_id),
        metadata={"previous_id": doc_id, "file_name": request.file_name},
        **audit_request_context(request_ctx),
    )
    return response


@router.put("/documents/{doc_id}/visibility")
async def update_document_visibility(
    request_ctx: Request,
    doc_id: str,
    request: KnowledgeVisibilityRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
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
    response = cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})
    await record_audit_event_async(
        user,
        action="knowledge.visibility_update",
        resource_type="knowledge_document",
        resource_id=doc_id,
        metadata={"visibility": request.visibility},
        **audit_request_context(request_ctx),
    )
    return response


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


@router.patch("/settings/rag")
async def update_rag_settings(
    request_ctx: Request,
    request: KnowledgeRagSettingsRequest,
    user: User = Depends(require_scope("config:write")),
) -> dict:
    try:
        settings = await update_rag_settings_async(request.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit_event_async(
        user,
        action="knowledge.rag_settings_update",
        resource_type="knowledge",
        metadata={"settings": settings},
        **audit_request_context(request_ctx),
    )
    return {
        "settings": settings,
        "status": await get_knowledge_base_lifecycle().knowledge_status_async(
            owner_user_id=effective_knowledge_user_filter(user),
        ),
    }


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
