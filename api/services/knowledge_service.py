from __future__ import annotations

import asyncio
from importlib.util import find_spec
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, cast

from anyio import Path as AsyncPath
from agno.knowledge.document import Document
from agno.knowledge.embedder.sentence_transformer import SentenceTransformerEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.reranker.sentence_transformer import SentenceTransformerReranker
from agno.vectordb.search import SearchType
from sqlalchemy import Column, MetaData, Table, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.services.postgres_store import (
    get_async_knowledge_postgres_db,
    postgres_label,
    postgres_sqlalchemy_url,
)
from api.services.knowledge_document_service import (
    content_to_document as _content_to_document,
    content_visible_to_owner as _content_visible_to_owner,
    owner_metadata as _owner_metadata,
    result_from_document as _result_from_document,
    safe_metadata as _safe_metadata,
)
from api.services.knowledge_ingest_service import (
    PROFILE_CSV as _PROFILE_CSV,
    PROFILE_JSON as _PROFILE_JSON,
    PROFILE_MARKDOWN as _PROFILE_MARKDOWN,
    PROFILE_TEXT as _PROFILE_TEXT,
    SUPPORTED_FILE_SUFFIXES,
    KnowledgeIngestProfile,
    KnowledgeReader,
    KnowledgeReaderConfig,
    pipeline_status as _ingest_pipeline_status,
    profile_for_filename as _profile_for_filename,
    reader_for_profile as _reader_for_profile,
)
from api.services.knowledge_runtime_service import (
    KnowledgeRuntimeDependencies,
    KnowledgeRuntimeSettings,
    build_knowledge_base,
    retrieval_candidate_limit,
)

@dataclass(frozen=True)
class KnowledgeServiceSettings:
    name: str
    pgvector_table: str
    postgres_schema: str
    postgres_knowledge_table: str
    embedding_model: str
    embedding_dimensions: int
    rerank_model: str
    query_prompt: str
    top_k: int
    chunk_size: int
    chunk_overlap: int
    code_chunk_size: int
    semantic_threshold: float
    vector_score_weight: float
    content_language: str
    prefix_match: bool
    rerank_enabled: bool
    rerank_candidate_multiplier: int
    rerank_min_candidates: int
    model_device: str
    search_type: str
    rerank_use_fp16: bool


def knowledge_settings() -> KnowledgeServiceSettings:
    settings = get_settings()
    return KnowledgeServiceSettings(
        name=settings.agno_knowledge_name,
        pgvector_table=settings.agno_knowledge_pgvector_table,
        postgres_schema=settings.agno_knowledge_schema,
        postgres_knowledge_table=settings.agno_postgres_knowledge_table,
        embedding_model=settings.agno_knowledge_embedding_model,
        embedding_dimensions=max(1, settings.agno_knowledge_embedding_dimensions),
        rerank_model=settings.agno_knowledge_rerank_model,
        query_prompt=settings.agno_knowledge_query_prompt,
        top_k=max(1, settings.agno_knowledge_top_k),
        chunk_size=max(200, settings.agno_knowledge_chunk_size),
        chunk_overlap=max(0, settings.agno_knowledge_chunk_overlap),
        code_chunk_size=max(256, settings.agno_knowledge_code_chunk_size),
        semantic_threshold=settings.agno_knowledge_semantic_threshold,
        vector_score_weight=settings.agno_knowledge_vector_score_weight,
        content_language=settings.agno_knowledge_content_language,
        prefix_match=settings.agno_knowledge_prefix_match,
        rerank_enabled=settings.agno_knowledge_rerank_enabled,
        rerank_candidate_multiplier=max(
            1,
            settings.agno_knowledge_rerank_candidate_multiplier,
        ),
        rerank_min_candidates=max(1, settings.agno_knowledge_rerank_min_candidates),
        model_device=settings.agno_knowledge_device.strip().lower() or "auto",
        search_type=settings.agno_knowledge_search_type,
        rerank_use_fp16=settings.agno_knowledge_rerank_use_fp16,
    )


COLD_START_NOTE = (
    "首次触发知识写入、向量检索或重排时会在线程中加载/下载本地模型，"
    "当前操作可能等待 30-120 秒，但不会阻塞其它页面请求。"
)
_knowledge_async_lock = asyncio.Lock()
_knowledge_runtime_async_lock = asyncio.Lock()


async def _resolve_existing_file_async(path: str) -> Path:
    file_path = Path(path).expanduser().resolve()
    if not await AsyncPath(file_path).is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return file_path


def _model_device() -> str:
    model_device = knowledge_settings().model_device
    return "cpu" if model_device == "auto" else model_device


@lru_cache(maxsize=1)
def _get_embedder() -> SentenceTransformerEmbedder:
    settings = knowledge_settings()
    return SentenceTransformerEmbedder(
        id=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        prompt=settings.query_prompt,
        normalize_embeddings=True,
    )


@lru_cache(maxsize=1)
def _get_reranker() -> SentenceTransformerReranker | None:
    if not knowledge_settings().rerank_enabled:
        return None
    return SentenceTransformerReranker(model=knowledge_settings().rerank_model)


def _search_type_from_name(value: str | None) -> SearchType:
    clean_value = (value or "").strip().lower()
    if not clean_value:
        return SearchType.hybrid
    try:
        return SearchType(clean_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SearchType)
        raise ValueError(f"不支持的 search_type: {value}. 可选值: {allowed}") from exc


def search_type_from_env() -> SearchType:
    return _search_type_from_name(knowledge_settings().search_type)


def _reader_config(needs_embedder: bool) -> KnowledgeReaderConfig:
    settings = knowledge_settings()
    return KnowledgeReaderConfig(
        embedder=_get_embedder() if needs_embedder else None,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        code_chunk_size=settings.code_chunk_size,
        semantic_threshold=settings.semantic_threshold,
    )


def knowledge_profile_for_filename(filename: str | None) -> KnowledgeIngestProfile:
    return _profile_for_filename(filename)


def reader_for_profile(
    profile: KnowledgeIngestProfile,
    filename: str | None = None,
) -> KnowledgeReader:
    return _reader_for_profile(
        profile,
        _reader_config(needs_embedder=profile.strategy == "semantic"),
        filename,
    )


def reader_for_filename(
    filename: str | None,
) -> KnowledgeReader:
    profile = knowledge_profile_for_filename(filename)
    return _reader_for_profile(
        profile,
        _reader_config(needs_embedder=profile.strategy == "semantic"),
        filename,
    )


def pipeline_status() -> dict[str, Any]:
    settings = knowledge_settings()
    return _ingest_pipeline_status(
        search_type=search_type_from_env().value,
        vector_score_weight=settings.vector_score_weight,
        prefix_match=settings.prefix_match,
        content_language=settings.content_language,
        semantic_threshold=settings.semantic_threshold,
        code_chunk_size=settings.code_chunk_size,
    )


@lru_cache(maxsize=4)
def get_async_knowledge_base(search_type: SearchType | None = None) -> Knowledge:
    settings = knowledge_settings()
    embedder = _get_embedder()
    effective_search_type = search_type or search_type_from_env()
    return build_knowledge_base(
        KnowledgeRuntimeSettings(
            name=settings.name,
            description="Trinity AI Security knowledge base",
            pgvector_table=settings.pgvector_table,
            postgres_schema=settings.postgres_schema,
            db_url=postgres_sqlalchemy_url(),
            prefix_match=settings.prefix_match,
            vector_score_weight=settings.vector_score_weight,
            content_language=settings.content_language,
            top_k=settings.top_k,
            rerank_enabled=settings.rerank_enabled,
            rerank_candidate_multiplier=settings.rerank_candidate_multiplier,
            rerank_min_candidates=settings.rerank_min_candidates,
        ),
        KnowledgeRuntimeDependencies(
            embedder=embedder,
            reranker=_get_reranker(),
            contents_db=get_async_knowledge_postgres_db(),
        ),
        search_type=effective_search_type,
        readers={
            "text": reader_for_profile(_PROFILE_TEXT),
            "markdown": reader_for_profile(_PROFILE_MARKDOWN),
            "csv": reader_for_profile(_PROFILE_CSV),
            "json": reader_for_profile(_PROFILE_JSON),
        },
    )


async def _get_async_knowledge_base_async(search_type: SearchType | None = None) -> Knowledge:
    async with _knowledge_runtime_async_lock:
        return await asyncio.to_thread(get_async_knowledge_base, search_type)


async def get_async_knowledge_base_async(search_type: SearchType | None = None) -> Knowledge:
    return await _get_async_knowledge_base_async(search_type)


def knowledge_runtime_loaded() -> bool:
    return get_async_knowledge_base.cache_info().currsize > 0


async def _ensure_knowledge_contents_storage_async() -> None:
    contents_db = get_async_knowledge_postgres_db()
    get_table = getattr(contents_db, "_get_table")
    await get_table(table_type="knowledge", create_table_if_not_found=True)


async def _ensure_knowledge_storage_async() -> None:
    knowledge = await _get_async_knowledge_base_async()
    vector_db = cast(Any, knowledge.vector_db)
    await vector_db.async_create()
    await _ensure_knowledge_contents_storage_async()


async def _knowledge_content_rows_async(
    *,
    limit: int | None = None,
    page: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> tuple[list[Any], int]:
    return await get_async_knowledge_postgres_db().get_knowledge_contents(
        limit=limit,
        page=page,
        sort_by=sort_by,
        sort_order=sort_order,
        linked_to=knowledge_settings().name,
    )


async def _knowledge_content_by_id_async(content_id: str) -> Any | None:
    return await get_async_knowledge_postgres_db().get_knowledge_content(content_id)


def _pgvector_projection_table() -> Table:
    settings = knowledge_settings()
    return Table(
        settings.pgvector_table,
        MetaData(schema=settings.postgres_schema),
        Column("id", Text),
        Column("content_id", Text),
        Column("meta_data", JSONB),
    )


async def _chunk_counts_by_content_id_async(owner_user_id: str | None = None) -> dict[str, int]:
    table = _pgvector_projection_table()
    stmt = select(table.c.content_id, func.count()).where(table.c.content_id.is_not(None))
    owner_filter = _owner_metadata(owner_user_id)
    if owner_filter:
        stmt = stmt.where(table.c.meta_data.contains(owner_filter))
    stmt = stmt.group_by(table.c.content_id)
    try:
        async with get_async_control_plane_engine().begin() as conn:
            rows = (await conn.execute(stmt)).all()
    except Exception:
        return {}
    return {str(content_id): int(count) for content_id, count in rows if content_id}


async def _chunk_count_async(owner_user_id: str | None = None) -> int:
    table = _pgvector_projection_table()
    stmt = select(func.count()).select_from(table)
    owner_filter = _owner_metadata(owner_user_id)
    if owner_filter:
        stmt = stmt.where(table.c.meta_data.contains(owner_filter))
    try:
        async with get_async_control_plane_engine().begin() as conn:
            count = (await conn.execute(stmt)).scalar()
    except Exception:
        return 0
    return int(count or 0)


async def _hydrate_content_ids_async(documents: list[Document]) -> None:
    ids = [document.id for document in documents if document.id]
    if not ids:
        return
    table = _pgvector_projection_table()
    stmt = select(table.c.id, table.c.content_id).where(table.c.id.in_(ids))
    try:
        async with get_async_control_plane_engine().begin() as conn:
            rows = (await conn.execute(stmt)).all()
    except Exception:
        return
    content_ids = {str(row_id): str(content_id) for row_id, content_id in rows if content_id}
    for document in documents:
        if document.id and document.id in content_ids:
            document.content_id = content_ids[document.id]
            document.meta_data["content_id"] = content_ids[document.id]


async def _delete_vector_rows_by_content_id_async(content_id: str) -> None:
    table = _pgvector_projection_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(table.delete().where(table.c.content_id == content_id))


async def _delete_knowledge_content_row_async(knowledge: Any, content_id: str) -> None:
    contents_db = getattr(knowledge, "contents_db", None) or get_async_knowledge_postgres_db()
    delete_knowledge_content = getattr(contents_db, "delete_knowledge_content", None)
    if delete_knowledge_content is None:
        raise RuntimeError("Knowledge contents DB does not support async content deletion")
    result = delete_knowledge_content(content_id)
    if hasattr(result, "__await__"):
        await result


async def _delete_content_async(knowledge: Any, content_id: str) -> None:
    await _delete_vector_rows_by_content_id_async(content_id)
    await _delete_knowledge_content_row_async(knowledge, content_id)


async def _document_status_async(content_id: str) -> dict[str, Any] | None:
    await _ensure_knowledge_contents_storage_async()
    content = await _knowledge_content_by_id_async(content_id)
    if content is None:
        return None
    return _content_to_document(content)


@dataclass(frozen=True)
class KnowledgeBaseLifecycleDependencies:
    get_async_knowledge_base: Callable[[SearchType | None], Any] | None = None
    ensure_storage_async: Callable[[], Any] | None = None
    ensure_contents_storage_async: Callable[[], Any] | None = None
    knowledge_content_rows_async: Callable[..., Any] | None = None
    knowledge_content_by_id_async: Callable[[str], Any] | None = None
    chunk_counts_by_content_id_async: Callable[[str | None], Any] | None = None
    chunk_count_async: Callable[[str | None], Any] | None = None
    hydrate_content_ids_async: Callable[[list[Document]], Any] | None = None
    delete_content_async: Callable[[Any, str], Any] | None = None


class KnowledgeBaseLifecycle:
    """Knowledge Document lifecycle, retrieval and status behind one interface."""

    def __init__(
        self,
        dependencies: KnowledgeBaseLifecycleDependencies | None = None,
    ) -> None:
        self.dependencies = dependencies or KnowledgeBaseLifecycleDependencies()

    def _async_knowledge(self, search_type: SearchType | None = None) -> Any:
        if self.dependencies.get_async_knowledge_base is not None:
            return self.dependencies.get_async_knowledge_base(search_type)
        return get_async_knowledge_base(search_type)

    async def _async_knowledge_async(self, search_type: SearchType | None = None) -> Any:
        if self.dependencies.get_async_knowledge_base is not None:
            return self.dependencies.get_async_knowledge_base(search_type)
        return await _get_async_knowledge_base_async(search_type)

    async def _ensure_storage_async(self) -> None:
        if self.dependencies.ensure_storage_async is not None:
            result = self.dependencies.ensure_storage_async()
            if hasattr(result, "__await__"):
                await result
            return
        await _ensure_knowledge_storage_async()

    async def _ensure_contents_storage_async(self) -> None:
        if self.dependencies.ensure_contents_storage_async is not None:
            result = self.dependencies.ensure_contents_storage_async()
            if hasattr(result, "__await__"):
                await result
            return
        if self.dependencies.ensure_storage_async is not None:
            result = self.dependencies.ensure_storage_async()
            if hasattr(result, "__await__"):
                await result
            return
        await _ensure_knowledge_contents_storage_async()

    async def _knowledge_content_rows_async(
        self,
        *,
        limit: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> tuple[list[Any], int]:
        if self.dependencies.knowledge_content_rows_async is not None:
            result = self.dependencies.knowledge_content_rows_async(
                limit=limit,
                page=page,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            if hasattr(result, "__await__"):
                return await result
            return result
        return await _knowledge_content_rows_async(
            limit=limit,
            page=page,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    async def _knowledge_content_by_id_async(self, content_id: str) -> Any | None:
        if self.dependencies.knowledge_content_by_id_async is not None:
            result = self.dependencies.knowledge_content_by_id_async(content_id)
            if hasattr(result, "__await__"):
                return await result
            return result
        return await _knowledge_content_by_id_async(content_id)

    async def _chunk_counts_by_content_id_async(self, owner_user_id: str | None) -> dict[str, int]:
        if self.dependencies.chunk_counts_by_content_id_async is not None:
            result = self.dependencies.chunk_counts_by_content_id_async(owner_user_id)
            if hasattr(result, "__await__"):
                return await result
            return result
        return await _chunk_counts_by_content_id_async(owner_user_id)

    async def _chunk_count_async(self, owner_user_id: str | None) -> int:
        if self.dependencies.chunk_count_async is not None:
            result = self.dependencies.chunk_count_async(owner_user_id)
            if hasattr(result, "__await__"):
                return await result
            return result
        return await _chunk_count_async(owner_user_id)

    async def _hydrate_content_ids_async(self, documents: list[Document]) -> None:
        if self.dependencies.hydrate_content_ids_async is not None:
            result = self.dependencies.hydrate_content_ids_async(documents)
            if hasattr(result, "__await__"):
                await result
            return
        await _hydrate_content_ids_async(documents)

    async def _delete_content_async(self, knowledge: Any, content_id: str) -> None:
        if self.dependencies.delete_content_async is not None:
            result = self.dependencies.delete_content_async(knowledge, content_id)
            if hasattr(result, "__await__"):
                await result
            return
        await _delete_content_async(knowledge, content_id)

    async def _deletable_content_ids_async(
        self,
        owner_user_id: str | None,
    ) -> list[str]:
        contents, _ = await self._knowledge_content_rows_async()
        return [
            content.id
            for content in contents
            if content.id and _content_visible_to_owner(content, owner_user_id)
        ]

    async def add_text_document_async(
        self,
        title: str,
        content: str,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        clean_title = title.strip() or "未命名知识"
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("知识内容不能为空")

        base_metadata = _safe_metadata(metadata)
        filename = str(base_metadata.get("file_name") or clean_title)
        profile = knowledge_profile_for_filename(filename)
        safe_metadata = {
            **base_metadata,
            **_owner_metadata(owner_user_id),
            "title": clean_title,
            "source": source.strip() or "manual",
            "file_type": Path(filename).suffix.lower() or "text",
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": base_metadata.get("input_mode", "manual"),
        }
        knowledge = await self._async_knowledge_async()
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await knowledge.ainsert(
                name=clean_title,
                description=source.strip() or "manual",
                text_content=clean_content,
                metadata=safe_metadata,
                reader=reader_for_profile(profile, filename),
                upsert=True,
                skip_if_exists=False,
            )
        contents, _ = await knowledge.aget_content(
            limit=1,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        for content_row in contents:
            if content_row.name == clean_title:
                return _content_to_document(content_row)
        raise RuntimeError("知识写入完成但未能读取内容登记记录")

    async def add_file_document_async(
        self,
        path: str,
        title: str | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        file_path = await _resolve_existing_file_async(path)
        if file_path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
            supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
            raise ValueError(f"当前知识库支持的文件后缀: {supported}")

        clean_title = (title or file_path.stem).strip() or file_path.stem
        profile = knowledge_profile_for_filename(file_path.name)
        metadata = {
            **_owner_metadata(owner_user_id),
            "title": clean_title,
            "source": str(file_path),
            "file_path": str(file_path),
            "file_name": file_path.name,
            "file_type": file_path.suffix.lower(),
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": "path",
        }
        reader = reader_for_profile(profile, file_path.name)
        knowledge = await self._async_knowledge_async()
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await knowledge.ainsert(
                name=clean_title,
                description=str(file_path),
                path=str(file_path),
                metadata=metadata,
                reader=reader,
                upsert=True,
                skip_if_exists=False,
            )
        contents, _ = await knowledge.aget_content(
            limit=1,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        for content_row in contents:
            if content_row.name == clean_title:
                return _content_to_document(content_row)
        raise RuntimeError("知识写入完成但未能读取内容登记记录")

    async def list_documents_async(self, owner_user_id: str | None = None) -> list[dict[str, Any]]:
        await self._ensure_contents_storage_async()
        contents, _ = await self._knowledge_content_rows_async(
            limit=500,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        chunk_counts = await self._chunk_counts_by_content_id_async(owner_user_id)
        documents = []
        for content in contents:
            if not _content_visible_to_owner(content, owner_user_id):
                continue
            document = _content_to_document(content)
            document["chunks"] = chunk_counts.get(document["id"], document["chunks"])
            documents.append(document)
        return documents

    async def delete_document_async(
        self,
        doc_id: str,
        owner_user_id: str | None = None,
    ) -> bool:
        await self._ensure_contents_storage_async()
        content = await self._knowledge_content_by_id_async(doc_id)
        if content is None or not _content_visible_to_owner(content, owner_user_id):
            return False
        await self._delete_content_async(None, doc_id)
        return True

    async def clear_knowledge_base_async(
        self,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        await self._ensure_contents_storage_async()
        content_ids = await self._deletable_content_ids_async(owner_user_id)
        for content_id in content_ids:
            await self._delete_content_async(None, content_id)
        return {"documents": 0, "chunks": 0}

    async def search_documents_async(
        self,
        query: str,
        limit: int = 5,
        search_type: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clean_query = query.strip()
        if not clean_query:
            return []
        effective_search_type = (
            _search_type_from_name(search_type) if search_type else search_type_from_env()
        )
        await self._ensure_storage_async()
        knowledge = await self._async_knowledge_async(effective_search_type)
        settings = knowledge_settings()
        retrieval_limit = retrieval_candidate_limit(
            limit,
            rerank_enabled=settings.rerank_enabled,
            rerank_candidate_multiplier=settings.rerank_candidate_multiplier,
            rerank_min_candidates=settings.rerank_min_candidates,
        )
        documents = await knowledge.asearch(
            clean_query,
            max_results=retrieval_limit,
            filters=_owner_metadata(owner_user_id) or None,
            search_type=effective_search_type.value,
        )
        await self._hydrate_content_ids_async(documents)
        return [_result_from_document(document) for document in documents[:limit]]

    async def knowledge_status_async(
        self,
        owner_user_id: str | None = None,
        documents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        docs = (
            documents
            if documents is not None
            else await self.list_documents_async(owner_user_id=owner_user_id)
        )
        chunk_count = await self._chunk_count_async(owner_user_id)
        settings = knowledge_settings()
        device = _model_device()
        return {
            **pipeline_status(),
            "collection": settings.pgvector_table,
            "storage": "pgvector",
            "database": postgres_label(settings.postgres_schema, settings.pgvector_table),
            "contents_db": postgres_label(settings.postgres_schema, settings.postgres_knowledge_table),
            "postgres_schema": settings.postgres_schema,
            "documents": len(docs),
            "chunks": chunk_count,
            "embedding": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
            "rerank": settings.rerank_model,
            "device": device,
            "rerank_enabled": settings.rerank_enabled,
            "top_k": settings.top_k,
            "retrieval_candidates": retrieval_candidate_limit(
                settings.top_k,
                rerank_enabled=settings.rerank_enabled,
                rerank_candidate_multiplier=settings.rerank_candidate_multiplier,
                rerank_min_candidates=settings.rerank_min_candidates,
            ),
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "cold_start_note": COLD_START_NOTE,
            "runtime_loaded": knowledge_runtime_loaded(),
            "torch_runtime_ok": find_spec("torch") is not None,
        }


DEFAULT_KNOWLEDGE_BASE_LIFECYCLE = KnowledgeBaseLifecycle()


def get_knowledge_base_lifecycle() -> KnowledgeBaseLifecycle:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE


async def add_text_document_async(
    title: str,
    content: str,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.add_text_document_async(
        title,
        content,
        source=source,
        metadata=metadata,
        owner_user_id=owner_user_id,
    )


async def add_file_document_async(
    path: str,
    title: str | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.add_file_document_async(
        path,
        title=title,
        owner_user_id=owner_user_id,
    )


async def list_documents_async(owner_user_id: str | None = None) -> list[dict[str, Any]]:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.list_documents_async(
        owner_user_id=owner_user_id
    )


async def delete_document_async(doc_id: str, owner_user_id: str | None = None) -> bool:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.delete_document_async(
        doc_id,
        owner_user_id=owner_user_id,
    )


async def clear_knowledge_base_async(owner_user_id: str | None = None) -> dict[str, Any]:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.clear_knowledge_base_async(
        owner_user_id=owner_user_id,
    )


async def search_documents_async(
    query: str,
    limit: int = 5,
    search_type: str | None = None,
    owner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.search_documents_async(
        query,
        limit=limit,
        search_type=search_type,
        owner_user_id=owner_user_id,
    )


async def knowledge_status_async(
    owner_user_id: str | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return await DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.knowledge_status_async(
        owner_user_id=owner_user_id,
        documents=documents,
    )
