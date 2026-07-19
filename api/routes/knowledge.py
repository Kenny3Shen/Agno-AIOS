import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from loguru import logger

from api.auth.claims import actor_id, scope_user_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.visibility import can_manage_resource
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.knowledge_document_service import KnowledgeDocumentPayload
from api.services.knowledge_rag_settings_service import current_ingest_defaults
from api.services.knowledge_service import get_knowledge_base_lifecycle
from api.utils.pagination import pagination_meta
from api.services.knowledge_upload_service import (
    KnowledgeUploadTooLargeError,
    remove_managed_upload_async,
    store_knowledge_upload_async,
)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])

# Wall-clock budget for one background ingest/update job (vectorize can be slow).
KNOWLEDGE_INGEST_TIMEOUT_SECONDS = 15 * 60


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






def _schedule_knowledge_ingest(
    *,
    task_name: str,
    work,
    user: User,
    audit_action: str,
    audit_resource_id: str,
    audit_metadata: Mapping[str, object] | None,
    request_ctx: Request,
) -> None:
    """Fire-and-forget parse/vectorize so HTTP handlers can return after upload."""

    async def _job() -> None:
        try:
            document = await asyncio.wait_for(
                work(),
                timeout=KNOWLEDGE_INGEST_TIMEOUT_SECONDS,
            )
            try:
                await record_audit_event_async(
                    user,
                    action=audit_action,
                    resource_type="knowledge_document",
                    resource_id=str(
                        (
                            (document or {}).get("id")
                            if isinstance(document, Mapping)
                            else None
                        )
                        or audit_resource_id
                    ),
                    metadata=dict(audit_metadata or {}),
                    **audit_request_context(request_ctx),
                )
            except Exception:
                logger.exception("knowledge background audit failed: {}", task_name)
        except Exception as exc:
            logger.exception("knowledge background ingest failed: {}", task_name)
            try:
                from api.services.notification_service import notify_background_task_failure

                await notify_background_task_failure(
                    task_name=task_name,
                    error=str(exc),
                    user_id=actor_id(user),
                )
            except Exception:
                logger.exception("knowledge background failure notify failed: {}", task_name)

    asyncio.create_task(_job(), name=task_name)


def _processing_document_payload(
    *,
    job_id: str,
    title: str,
    source: str,
    owner_user_id: str,
    visibility: str,
    file_name: str = "",
    file_size: object = None,
    mime_type: str = "",
    file_type: str = "",
    metadata: Mapping[str, object] | None = None,
) -> KnowledgeDocumentResponsePayload:
    """Placeholder row returned while vectorize runs in the background."""
    meta: dict[str, str] = {
        "status": "processing",
        "title": title,
        "source": source,
    }
    if file_name:
        meta["file_name"] = file_name
    if mime_type:
        meta["mime_type"] = mime_type
    if file_type:
        meta["file_type"] = file_type
    if file_size is not None:
        meta["file_size"] = str(file_size)
    for key, value in (metadata or {}).items():
        if value is not None and key not in meta:
            meta[str(key)] = str(value)
    return cast(
        KnowledgeDocumentResponsePayload,
        {
            "id": job_id,
            "title": title,
            "source": source,
            "chunks": 0,
            "created_at": "",
            "updated_at": "",
            "status": "processing",
            "type": file_type or (Path(file_name).suffix.lower() if file_name else ""),
            "size": file_size,
            "visibility": visibility,
            "owner_user_id": owner_user_id,
            "metadata": meta,
            "can_manage": True,
        },
    )

class KnowledgeIngestOptionsRequest(BaseModel):
    chunk_size: int | None = Field(default=None, ge=200)
    chunk_overlap: int | None = Field(default=None, ge=0)
    markdown_split_on_headings: int | None = Field(default=None, ge=0, le=6)
    csv_skip_header: bool | None = None
    csv_clean_rows: bool | None = None
    code_chunk_size: int | None = Field(default=None, ge=256)
    code_tokenizer: str | None = Field(default=None, pattern="^(character|gpt2)$")
    code_include_nodes: bool | None = None
    semantic_threshold: float | None = Field(default=None, ge=0, le=1)
    semantic_similarity_window: int | None = Field(default=None, ge=1)
    semantic_min_sentences_per_chunk: int | None = Field(default=None, ge=1)
    semantic_min_characters_per_sentence: int | None = Field(default=None, ge=1)
    reader_strategy: str | None = Field(
        default=None,
        pattern="^(markdown|semantic|code|csv_row|json|document)$",
    )


class KnowledgeTextRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: str = "manual"
    metadata: dict[str, str] = Field(default_factory=dict)
    visibility: str = "private"
    ingest_options: KnowledgeIngestOptionsRequest | None = None


class KnowledgeDocumentMetadataUpdateRequest(BaseModel):
    title: str | None = None
    source: str | None = None
    visibility: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class KnowledgeDocumentUpdateActionRequest(BaseModel):
    mode: Literal["metadata", "rebuild", "replace_text"]
    metadata: KnowledgeDocumentMetadataUpdateRequest | None = None
    ingest_options: KnowledgeIngestOptionsRequest | None = None
    content: str | None = None
    file_name: str | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(5, ge=1, le=20)
    search_type: str | None = Field(
        default=None,
        description="vector / keyword / hybrid，默认使用 TAIS_KNOWLEDGE_SEARCH_TYPE",
    )


def ingest_options_from_form(
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    markdown_split_on_headings: int | None = None,
    csv_skip_header: bool | None = None,
    csv_clean_rows: bool | None = None,
    code_chunk_size: int | None = None,
    code_tokenizer: str | None = None,
    code_include_nodes: bool | None = None,
    semantic_threshold: float | None = None,
    semantic_similarity_window: int | None = None,
    semantic_min_sentences_per_chunk: int | None = None,
    semantic_min_characters_per_sentence: int | None = None,
    reader_strategy: str | None = None,
) -> dict[str, object] | None:
    options: dict[str, object] = {}
    if chunk_size is not None:
        options["chunk_size"] = chunk_size
    if chunk_overlap is not None:
        options["chunk_overlap"] = chunk_overlap
    if markdown_split_on_headings is not None:
        options["markdown_split_on_headings"] = markdown_split_on_headings
    if csv_skip_header is not None:
        options["csv_skip_header"] = csv_skip_header
    if csv_clean_rows is not None:
        options["csv_clean_rows"] = csv_clean_rows
    if code_chunk_size is not None:
        options["code_chunk_size"] = code_chunk_size
    clean_tokenizer = (code_tokenizer or "").strip()
    if clean_tokenizer:
        options["code_tokenizer"] = clean_tokenizer
    if code_include_nodes is not None:
        options["code_include_nodes"] = code_include_nodes
    if semantic_threshold is not None:
        options["semantic_threshold"] = semantic_threshold
    if semantic_similarity_window is not None:
        options["semantic_similarity_window"] = semantic_similarity_window
    if semantic_min_sentences_per_chunk is not None:
        options["semantic_min_sentences_per_chunk"] = semantic_min_sentences_per_chunk
    if semantic_min_characters_per_sentence is not None:
        options["semantic_min_characters_per_sentence"] = semantic_min_characters_per_sentence
    clean_strategy = (reader_strategy or "").strip()
    if clean_strategy:
        options["reader_strategy"] = clean_strategy
    return options or None


@router.get("")
async def list_knowledge(
    query: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    sort_by: str = Query(default="updated_at", pattern="^(updated_at|created_at|name|status)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    user: User = Depends(require_scope("knowledge:read")),
) -> dict:
    owner_user_id = effective_knowledge_user_filter(user)
    knowledge_base = get_knowledge_base_lifecycle()
    page_documents, total = await knowledge_base.list_documents_page_async(
        owner_user_id=owner_user_id,
        query=query,
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {
        "data": with_manage_flags(page_documents, user),
        "meta": pagination_meta(
            page=page,
            limit=limit,
            total_count=total,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
            ingest_defaults=current_ingest_defaults(),
        ),
    }


@router.post("/documents/text", response_model=None)
async def create_text_document(
    request_ctx: Request,
    request: KnowledgeTextRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    ingest_options = (
        request.ingest_options.model_dump(exclude_none=True)
        if request.ingest_options is not None
        else None
    )
    owner = actor_id(user)
    job_id = f"processing:text:{owner}:{abs(hash((request.title, request.source, request.content[:64]))) % 10**12}"
    clean_title = (request.title or "").strip() or "text"
    clean_source = (request.source or "").strip() or "manual"

    async def _bg_ingest() -> KnowledgeDocumentResponsePayload:
        result = await get_knowledge_base_lifecycle().add_text_document_async(
            title=request.title,
            content=request.content,
            source=request.source,
            visibility=request.visibility,
            metadata=request.metadata,
            owner_user_id=owner,
            ingest_options=ingest_options,
        )
        return cast(KnowledgeDocumentResponsePayload, {**result, "can_manage": True})

    _schedule_knowledge_ingest(
        task_name=f"knowledge-bg-text:{job_id}",
        work=_bg_ingest,
        user=user,
        audit_action="knowledge.create",
        audit_resource_id=job_id,
        audit_metadata={
            "title": request.title,
            "source": request.source,
            "async_ingest": True,
            "input_mode": "text",
        },
        request_ctx=request_ctx,
    )
    return _processing_document_payload(
        job_id=job_id,
        title=clean_title,
        source=clean_source,
        owner_user_id=owner,
        visibility=request.visibility,
        file_type=".txt",
        metadata={"input_mode": "text"},
    )


@router.post("/documents/upload", response_model=None)
async def upload_document(

    request_ctx: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source: str | None = Form(default=None),
    visibility: str = Form(default="private"),
    chunk_size: int | None = Form(default=None, ge=200),
    chunk_overlap: int | None = Form(default=None, ge=0),
    markdown_split_on_headings: int | None = Form(default=None, ge=0, le=6),
    csv_skip_header: bool | None = Form(default=None),
    csv_clean_rows: bool | None = Form(default=None),
    code_chunk_size: int | None = Form(default=None, ge=256),
    code_tokenizer: str | None = Form(default=None, pattern="^(character|gpt2)$"),
    code_include_nodes: bool | None = Form(default=None),
    semantic_threshold: float | None = Form(default=None, ge=0, le=1),
    semantic_similarity_window: int | None = Form(default=None, ge=1),
    semantic_min_sentences_per_chunk: int | None = Form(default=None, ge=1),
    semantic_min_characters_per_sentence: int | None = Form(default=None, ge=1),
    reader_strategy: str | None = Form(default=None),
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    ingest_options = ingest_options_from_form(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        markdown_split_on_headings=markdown_split_on_headings,
        csv_skip_header=csv_skip_header,
        csv_clean_rows=csv_clean_rows,
        code_chunk_size=code_chunk_size,
        code_tokenizer=code_tokenizer,
        code_include_nodes=code_include_nodes,
        semantic_threshold=semantic_threshold,
        semantic_similarity_window=semantic_similarity_window,
        semantic_min_sentences_per_chunk=semantic_min_sentences_per_chunk,
        semantic_min_characters_per_sentence=semantic_min_characters_per_sentence,
        reader_strategy=reader_strategy,
    )
    clean_title = (title or "").strip() or None
    try:
        stored_upload = await store_knowledge_upload_async(file)
    except KnowledgeUploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clean_source = (source or "").strip() or f"upload:{stored_upload.file_name}"
    owner = actor_id(user)
    job_id = f"processing:upload:{stored_upload.upload_id}"

    async def _bg_ingest() -> KnowledgeDocumentResponsePayload:
        try:
            result = await get_knowledge_base_lifecycle().add_file_document_async(
                path=str(stored_upload.path),
                title=clean_title,
                source=clean_source,
                metadata=stored_upload.metadata(),
                owner_user_id=owner,
                visibility=visibility,
                ingest_options=ingest_options,
            )
        except Exception:
            await remove_managed_upload_async(stored_upload.metadata())
            raise
        return cast(KnowledgeDocumentResponsePayload, {**result, "can_manage": True})

    _schedule_knowledge_ingest(
        task_name=f"knowledge-bg-upload:{stored_upload.upload_id}",
        work=_bg_ingest,
        user=user,
        audit_action="knowledge.create",
        audit_resource_id=job_id,
        audit_metadata={
            "file_name": stored_upload.file_name,
            "file_size": stored_upload.file_size,
            "mime_type": stored_upload.mime_type,
            "source": clean_source,
            "upload_mode": "browser",
            "async_ingest": True,
        },
        request_ctx=request_ctx,
    )
    return _processing_document_payload(
        job_id=job_id,
        title=clean_title or Path(stored_upload.file_name).stem,
        source=clean_source,
        owner_user_id=owner,
        visibility=visibility,
        file_name=stored_upload.file_name,
        file_size=stored_upload.file_size,
        mime_type=stored_upload.mime_type,
        file_type=Path(stored_upload.file_name).suffix.lower(),
        metadata=stored_upload.metadata(),
    )


@router.delete("/documents/{doc_id}")
async def remove_document(
    request_ctx: Request,
    doc_id: str,
    user: User = Depends(require_scope("knowledge:delete")),
) -> dict:
    deleted = await get_knowledge_base_lifecycle().delete_document_async(
        doc_id,
        owner_user_id=effective_knowledge_user_filter(user),
        user=user,
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


def changed_metadata_fields(metadata: KnowledgeDocumentMetadataUpdateRequest | None) -> list[str]:
    if metadata is None:
        return []
    return [
        field
        for field, value in (
            ("title", metadata.title),
            ("source", metadata.source),
            ("visibility", metadata.visibility),
            ("metadata", metadata.metadata),
        )
        if value not in (None, {}, "")
    ]


@router.post("/documents/{doc_id}/update", response_model=None)
async def update_document(
    request_ctx: Request,
    doc_id: str,
    request: KnowledgeDocumentUpdateActionRequest,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    metadata = request.metadata or KnowledgeDocumentMetadataUpdateRequest()
    ingest_options = (
        request.ingest_options.model_dump(exclude_none=True)
        if request.ingest_options is not None
        else None
    )

    if request.mode == "metadata":
        try:
            updated = await get_knowledge_base_lifecycle().update_document_metadata_async(
                doc_id,
                title=metadata.title,
                source=metadata.source,
                visibility=metadata.visibility,
                metadata=metadata.metadata,
                user=user,
            )
            if updated is None:
                raise LookupError("知识文档不存在")
            response = cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})
            await record_audit_event_async(
                user,
                action="knowledge.update",
                resource_type="knowledge_document",
                resource_id=doc_id,
                metadata={"mode": request.mode, "fields": changed_metadata_fields(metadata)},
                **audit_request_context(request_ctx),
            )
            return response
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    if request.mode == "replace_text":
        clean_content = (request.content or "").strip()
        clean_file_name = (request.file_name or "").strip()
        if not clean_content or not clean_file_name:
            raise HTTPException(
                status_code=400,
                detail="正文替换需要提供 content 和 file_name",
            )

    job_id = f"processing:update:{request.mode}:{doc_id}"
    owner_filter = effective_knowledge_user_filter(user)

    async def _bg_update() -> KnowledgeDocumentResponsePayload:
        if request.mode == "rebuild":
            updated = await get_knowledge_base_lifecycle().rebuild_document_async(
                doc_id,
                owner_user_id=owner_filter,
                user=user,
                title=metadata.title,
                source=metadata.source,
                visibility=metadata.visibility,
                metadata=metadata.metadata,
                ingest_options=ingest_options,
            )
        else:
            updated = await get_knowledge_base_lifecycle().replace_document_source_async(
                doc_id,
                content=(request.content or "").strip(),
                file_name=(request.file_name or "").strip(),
                title=metadata.title,
                source=metadata.source,
                visibility=metadata.visibility,
                metadata=metadata.metadata,
                owner_user_id=owner_filter,
                user=user,
                ingest_options=ingest_options,
            )
        if updated is None:
            raise LookupError("知识文档不存在")
        return cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})

    audit_action = (
        "knowledge.rebuild" if request.mode == "rebuild" else "knowledge.source_replace"
    )
    _schedule_knowledge_ingest(
        task_name=f"knowledge-bg-update:{request.mode}:{doc_id}",
        work=_bg_update,
        user=user,
        audit_action=audit_action,
        audit_resource_id=doc_id,
        audit_metadata={
            "mode": request.mode,
            "fields": changed_metadata_fields(metadata),
            "async_ingest": True,
            **(
                {"file_name": (request.file_name or "").strip()}
                if request.mode == "replace_text"
                else {}
            ),
        },
        request_ctx=request_ctx,
    )
    return _processing_document_payload(
        job_id=job_id,
        title=(metadata.title or "").strip() or doc_id,
        source=(metadata.source or "").strip() or doc_id,
        owner_user_id=actor_id(user),
        visibility=metadata.visibility or "private",
        file_name=(request.file_name or "").strip() if request.mode == "replace_text" else "",
        metadata={"mode": request.mode, "async_ingest": "true"},
    )


@router.post("/documents/{doc_id}/update/upload", response_model=None)
async def update_document_upload(

    request_ctx: Request,
    doc_id: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source: str | None = Form(default=None),
    visibility: str | None = Form(default=None),
    chunk_size: int | None = Form(default=None, ge=200),
    chunk_overlap: int | None = Form(default=None, ge=0),
    markdown_split_on_headings: int | None = Form(default=None, ge=0, le=6),
    csv_skip_header: bool | None = Form(default=None),
    csv_clean_rows: bool | None = Form(default=None),
    code_chunk_size: int | None = Form(default=None, ge=256),
    code_tokenizer: str | None = Form(default=None, pattern="^(character|gpt2)$"),
    code_include_nodes: bool | None = Form(default=None),
    semantic_threshold: float | None = Form(default=None, ge=0, le=1),
    semantic_similarity_window: int | None = Form(default=None, ge=1),
    semantic_min_sentences_per_chunk: int | None = Form(default=None, ge=1),
    semantic_min_characters_per_sentence: int | None = Form(default=None, ge=1),
    reader_strategy: str | None = Form(default=None),
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload:
    ingest_options = ingest_options_from_form(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        markdown_split_on_headings=markdown_split_on_headings,
        csv_skip_header=csv_skip_header,
        csv_clean_rows=csv_clean_rows,
        code_chunk_size=code_chunk_size,
        code_tokenizer=code_tokenizer,
        code_include_nodes=code_include_nodes,
        semantic_threshold=semantic_threshold,
        semantic_similarity_window=semantic_similarity_window,
        semantic_min_sentences_per_chunk=semantic_min_sentences_per_chunk,
        semantic_min_characters_per_sentence=semantic_min_characters_per_sentence,
        reader_strategy=reader_strategy,
    )
    clean_title = (title or "").strip() or None
    try:
        stored_upload = await store_knowledge_upload_async(file)
    except KnowledgeUploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clean_source_val = (source or "").strip() or None
    owner_filter = effective_knowledge_user_filter(user)
    job_id = f"processing:update-upload:{doc_id}:{stored_upload.upload_id}"

    async def _bg_replace() -> KnowledgeDocumentResponsePayload:
        try:
            updated = await get_knowledge_base_lifecycle().replace_document_file_async(
                doc_id,
                path=str(stored_upload.path),
                title=clean_title,
                source=clean_source_val,
                visibility=visibility,
                metadata=stored_upload.metadata(),
                owner_user_id=owner_filter,
                user=user,
                ingest_options=ingest_options,
            )
        except Exception:
            await remove_managed_upload_async(stored_upload.metadata())
            raise
        if updated is None:
            await remove_managed_upload_async(stored_upload.metadata())
            raise LookupError("知识文档不存在")
        return cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})

    _schedule_knowledge_ingest(
        task_name=f"knowledge-bg-update-upload:{doc_id}:{stored_upload.upload_id}",
        work=_bg_replace,
        user=user,
        audit_action="knowledge.source_replace",
        audit_resource_id=doc_id,
        audit_metadata={
            "mode": "upload",
            "file_name": stored_upload.file_name,
            "file_size": stored_upload.file_size,
            "mime_type": stored_upload.mime_type,
            "upload_mode": "browser",
            "async_ingest": True,
        },
        request_ctx=request_ctx,
    )
    return _processing_document_payload(
        job_id=job_id,
        title=clean_title or stored_upload.file_name,
        source=clean_source_val or f"upload:{stored_upload.file_name}",
        owner_user_id=actor_id(user),
        visibility=visibility or "private",
        file_name=stored_upload.file_name,
        file_size=stored_upload.file_size,
        mime_type=stored_upload.mime_type,
        file_type=Path(stored_upload.file_name).suffix.lower(),
        metadata=stored_upload.metadata(),
    )


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    user: User = Depends(require_scope("knowledge:read")),
) -> dict:
    try:
        results = await get_knowledge_base_lifecycle().search_documents_async(
            request.query,
            request.limit,
            search_type=request.search_type,
            owner_user_id=effective_knowledge_user_filter(user),
        )
        return {
            "data": results,
            "meta": pagination_meta(
                page=1,
                limit=max(int(request.limit or 1), 1),
                total_count=len(results),
            ),
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
        user=user,
    )
    await record_audit_event_async(
        user,
        action="knowledge.clear",
        resource_type="knowledge",
        **audit_request_context(request_ctx),
    )
    return result
