import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import actor_id, scope_user_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.visibility import can_manage_resource
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.knowledge_document_service import KnowledgeDocumentPayload
from api.services.knowledge_progress import (
    emit_progress,
    initial_progress_stages,
    knowledge_progress_event,
)
from api.services.knowledge_service import (
    get_knowledge_base_lifecycle,
    update_rag_settings_async,
)
from api.services.knowledge_upload_service import (
    KnowledgeUploadTooLargeError,
    remove_managed_upload_async,
    store_knowledge_upload_async,
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




def _sse_payload(event: str, data: Mapping[str, object] | dict[str, object]) -> dict[str, str]:
    return {
        "event": event,
        "data": json.dumps(data, ensure_ascii=False, default=str),
    }


async def _queue_progress(
    queue: asyncio.Queue[dict[str, object] | None],
    event: Mapping[str, object],
) -> None:
    await queue.put(dict(event))



async def _run_progress_sse(
    *,
    include_upload: bool,
    work,
) -> EventSourceResponse:
    """Run an async work(on_progress) coroutine and stream stage events."""
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def on_progress(event: Mapping[str, object]) -> None:
        await _queue_progress(queue, event)

    async def worker() -> None:
        try:
            for stage_event in initial_progress_stages(include_upload=include_upload):
                await queue.put(stage_event)
            document = await work(on_progress)
            await queue.put(
                {
                    "stage": "done",
                    "status": "completed",
                    "label": "完成",
                    "message": "完成",
                    "document": document,
                }
            )
        except KnowledgeUploadTooLargeError as exc:
            await queue.put(
                knowledge_progress_event(
                    "upload",
                    "failed",
                    message=str(exc),
                    error=str(exc),
                )
            )
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 413,
                }
            )
        except LookupError as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 404,
                }
            )
        except Exception as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 400,
                }
            )
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                status = str(item.get("status") or "")
                stage = str(item.get("stage") or "")
                if stage == "done":
                    yield _sse_payload(
                        "progress.completed" if status == "completed" else "progress.failed",
                        item,
                    )
                    break
                event_name = "progress.failed" if status == "failed" else "progress"
                yield _sse_payload(event_name, item)
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return EventSourceResponse(event_generator())


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


class KnowledgeFileRequest(BaseModel):
    path: str = Field(..., min_length=1)
    title: str | None = None
    source: str | None = None
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
async def get_knowledge_status(
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
    document_count = total
    if query:
        _, document_count = await knowledge_base.list_documents_page_async(
            owner_user_id=owner_user_id,
            page=1,
            limit=1,
        )
    return {
        "status": await knowledge_base.knowledge_status_async(
            owner_user_id=owner_user_id,
            document_count=document_count,
        ),
        "documents": with_manage_flags(page_documents, user),
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "query": query,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    }


@router.post("/documents/text", response_model=None)
async def create_text_document(
    request_ctx: Request,
    request: KnowledgeTextRequest,
    stream: Annotated[bool, Query()] = False,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload | EventSourceResponse:
    ingest_options = (
        request.ingest_options.model_dump(exclude_none=True)
        if request.ingest_options is not None
        else None
    )

    async def run_create(on_progress=None) -> KnowledgeDocumentResponsePayload:
        await emit_progress(
            on_progress,
            "upload",
            "skipped",
            message="跳过",
        )
        result = await get_knowledge_base_lifecycle().add_text_document_async(
            title=request.title,
            content=request.content,
            source=request.source,
            visibility=request.visibility,
            metadata=request.metadata,
            owner_user_id=actor_id(user),
            ingest_options=ingest_options,
            on_progress=on_progress,
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

    if not stream:
        try:
            return await run_create()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _run_progress_sse(include_upload=False, work=run_create)


@router.post("/documents/file", response_model=None)
async def create_file_document(
    request_ctx: Request,
    request: KnowledgeFileRequest,
    stream: Annotated[bool, Query()] = False,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload | EventSourceResponse:
    ingest_options = (
        request.ingest_options.model_dump(exclude_none=True)
        if request.ingest_options is not None
        else None
    )

    async def run_create(on_progress=None) -> KnowledgeDocumentResponsePayload:
        await emit_progress(
            on_progress,
            "upload",
            "skipped",
            message="跳过",
        )
        result = await get_knowledge_base_lifecycle().add_file_document_async(
            path=request.path,
            title=request.title,
            source=request.source,
            owner_user_id=actor_id(user),
            visibility=request.visibility,
            ingest_options=ingest_options,
            on_progress=on_progress,
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

    if not stream:
        try:
            return await run_create()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _run_progress_sse(include_upload=False, work=run_create)


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
    stream: Annotated[bool, Form()] = False,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload | EventSourceResponse:
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

    async def run_create(on_progress=None) -> KnowledgeDocumentResponsePayload:
        await emit_progress(
            on_progress,
            "upload",
            "running",
            message="上传中",
        )
        stored_upload = await store_knowledge_upload_async(file)
        await emit_progress(
            on_progress,
            "upload",
            "completed",
            message="已上传",
            detail={
                "file_name": stored_upload.file_name,
                "file_size": stored_upload.file_size,
            },
        )
        clean_source = (source or "").strip() or f"upload:{stored_upload.file_name}"
        try:
            result = await get_knowledge_base_lifecycle().add_file_document_async(
                path=str(stored_upload.path),
                title=clean_title,
                source=clean_source,
                metadata=stored_upload.metadata(),
                owner_user_id=actor_id(user),
                visibility=visibility,
                ingest_options=ingest_options,
                on_progress=on_progress,
            )
        except Exception:
            await remove_managed_upload_async(stored_upload.metadata())
            raise
        response = cast(KnowledgeDocumentResponsePayload, {**result, "can_manage": True})
        await record_audit_event_async(
            user,
            action="knowledge.create",
            resource_type="knowledge_document",
            resource_id=str(result.get("id") or stored_upload.file_name),
            metadata={
                "file_name": stored_upload.file_name,
                "file_size": stored_upload.file_size,
                "mime_type": stored_upload.mime_type,
                "source": clean_source,
                "upload_mode": "browser",
            },
            **audit_request_context(request_ctx),
        )
        return response

    if not stream:
        try:
            return await run_create()
        except KnowledgeUploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _run_progress_sse(include_upload=True, work=run_create)


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
    stream: Annotated[bool, Query()] = False,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload | EventSourceResponse:
    metadata = request.metadata or KnowledgeDocumentMetadataUpdateRequest()
    ingest_options = (
        request.ingest_options.model_dump(exclude_none=True)
        if request.ingest_options is not None
        else None
    )
    wants_stream = stream and request.mode in {"rebuild", "replace_text"}

    async def run_update(on_progress=None) -> KnowledgeDocumentResponsePayload:
        if request.mode == "metadata":
            updated = await get_knowledge_base_lifecycle().update_document_metadata_async(
                doc_id,
                title=metadata.title,
                source=metadata.source,
                visibility=metadata.visibility,
                metadata=metadata.metadata,
                user=user,
            )
            audit_action = "knowledge.update"
            audit_metadata = {"mode": request.mode, "fields": changed_metadata_fields(metadata)}
        elif request.mode == "rebuild":
            await emit_progress(
                on_progress,
                "upload",
                "skipped",
                message="跳过",
            )
            updated = await get_knowledge_base_lifecycle().rebuild_document_async(
                doc_id,
                owner_user_id=effective_knowledge_user_filter(user),
                user=user,
                title=metadata.title,
                source=metadata.source,
                visibility=metadata.visibility,
                metadata=metadata.metadata,
                ingest_options=ingest_options,
                on_progress=on_progress,
            )
            audit_action = "knowledge.rebuild"
            audit_metadata = {"mode": request.mode, "fields": changed_metadata_fields(metadata)}
        else:
            clean_content = (request.content or "").strip()
            clean_file_name = (request.file_name or "").strip()
            if not clean_content or not clean_file_name:
                raise ValueError("正文替换需要提供 content 和 file_name")
            await emit_progress(
                on_progress,
                "upload",
                "skipped",
                message="跳过",
            )
            updated = await get_knowledge_base_lifecycle().replace_document_source_async(
                doc_id,
                content=clean_content,
                file_name=clean_file_name,
                title=metadata.title,
                source=metadata.source,
                visibility=metadata.visibility,
                metadata=metadata.metadata,
                owner_user_id=effective_knowledge_user_filter(user),
                user=user,
                ingest_options=ingest_options,
                on_progress=on_progress,
            )
            audit_action = "knowledge.source_replace"
            audit_metadata = {
                "mode": request.mode,
                "fields": changed_metadata_fields(metadata),
                "file_name": clean_file_name,
            }
        if updated is None:
            raise LookupError("知识文档不存在")
        response = cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})
        await record_audit_event_async(
            user,
            action=audit_action,
            resource_type="knowledge_document",
            resource_id=doc_id,
            metadata=audit_metadata,
            **audit_request_context(request_ctx),
        )
        return response

    if not wants_stream:
        try:
            return await run_update()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def on_progress(event: Mapping[str, object]) -> None:
        await _queue_progress(queue, event)

    async def worker() -> None:
        try:
            for stage_event in initial_progress_stages(include_upload=False):
                await queue.put(stage_event)
            document = await run_update(on_progress=on_progress)
            await queue.put(
                {
                    "stage": "done",
                    "status": "completed",
                    "label": "完成",
                    "message": "完成",
                    "document": document,
                }
            )
        except LookupError as exc:
            await queue.put(
                knowledge_progress_event(
                    "cleanup",
                    "failed",
                    message=str(exc),
                    error=str(exc),
                )
            )
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 404,
                }
            )
        except Exception as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 400,
                }
            )
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                status = str(item.get("status") or "")
                stage = str(item.get("stage") or "")
                if stage == "done":
                    yield _sse_payload(
                        "progress.completed" if status == "completed" else "progress.failed",
                        item,
                    )
                    break
                event_name = "progress.failed" if status == "failed" else "progress"
                yield _sse_payload(event_name, item)
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return EventSourceResponse(event_generator())


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
    stream: Annotated[bool, Form()] = False,
    user: User = Depends(require_scope("knowledge:write")),
) -> KnowledgeDocumentResponsePayload | EventSourceResponse:
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
    clean_source = (source or "").strip() or None

    async def run_upload(on_progress=None) -> tuple[KnowledgeDocumentResponsePayload, Any]:
        await emit_progress(
            on_progress,
            "upload",
            "running",
            message="上传中",
        )
        stored_upload = await store_knowledge_upload_async(file)
        await emit_progress(
            on_progress,
            "upload",
            "completed",
            message="已上传",
            detail={
                "file_name": stored_upload.file_name,
                "file_size": stored_upload.file_size,
            },
        )
        try:
            updated = await get_knowledge_base_lifecycle().replace_document_file_async(
                doc_id,
                path=str(stored_upload.path),
                title=clean_title,
                source=clean_source,
                visibility=visibility,
                metadata=stored_upload.metadata(),
                owner_user_id=effective_knowledge_user_filter(user),
                user=user,
                ingest_options=ingest_options,
                on_progress=on_progress,
            )
        except Exception:
            await remove_managed_upload_async(stored_upload.metadata())
            raise
        if updated is None:
            await remove_managed_upload_async(stored_upload.metadata())
            raise LookupError("知识文档不存在")
        response = cast(KnowledgeDocumentResponsePayload, {**updated, "can_manage": True})
        await record_audit_event_async(
            user,
            action="knowledge.source_replace",
            resource_type="knowledge_document",
            resource_id=doc_id,
            metadata={
                "mode": "upload",
                "file_name": stored_upload.file_name,
                "file_size": stored_upload.file_size,
                "mime_type": stored_upload.mime_type,
                "upload_mode": "browser",
            },
            **audit_request_context(request_ctx),
        )
        return response, stored_upload

    if not stream:
        try:
            response, _stored = await run_upload()
            return response
        except KnowledgeUploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def on_progress(event: Mapping[str, object]) -> None:
        await _queue_progress(queue, event)

    async def worker() -> None:
        try:
            for stage_event in initial_progress_stages(include_upload=True):
                await queue.put(stage_event)
            document, _stored = await run_upload(on_progress=on_progress)
            await queue.put(
                {
                    "stage": "done",
                    "status": "completed",
                    "label": "完成",
                    "message": "完成",
                    "document": document,
                }
            )
        except KnowledgeUploadTooLargeError as exc:
            await queue.put(
                knowledge_progress_event(
                    "upload",
                    "failed",
                    message=str(exc),
                    error=str(exc),
                )
            )
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 413,
                }
            )
        except LookupError as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 404,
                }
            )
        except Exception as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "label": "失败",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 400,
                }
            )
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                status = str(item.get("status") or "")
                stage = str(item.get("stage") or "")
                if stage == "done":
                    yield _sse_payload(
                        "progress.completed" if status == "completed" else "progress.failed",
                        item,
                    )
                    break
                event_name = "progress.failed" if status == "failed" else "progress"
                yield _sse_payload(event_name, item)
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return EventSourceResponse(event_generator())


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
        user=user,
    )
    await record_audit_event_async(
        user,
        action="knowledge.clear",
        resource_type="knowledge",
        **audit_request_context(request_ctx),
    )
    return result
