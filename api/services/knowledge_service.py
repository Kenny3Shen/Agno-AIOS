from __future__ import annotations

import asyncio
import mimetypes
from importlib.util import find_spec
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Callable, Mapping, cast

from agno.knowledge.content import Content
from agno.db.schemas.knowledge import KnowledgeRow
from agno.knowledge.document import Document
from agno.knowledge.embedder.sentence_transformer import SentenceTransformerEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.reranker.sentence_transformer import SentenceTransformerReranker
from agno.vectordb.search import SearchType
from sqlalchemy import Column, Integer, MetaData, Table, Text, cast as sql_cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from api.auth.claims import ActorLike
from api.auth.visibility import can_manage_resource, normalize_visibility
from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.knowledge_sources import (
    delete_knowledge_source_async as _delete_knowledge_source_async,
    get_knowledge_source_async as _get_knowledge_source_async,
    upsert_knowledge_source_async as _upsert_knowledge_source_async,
)
from api.services.postgres_store import (
    get_async_knowledge_postgres_db,
    postgres_label,
    postgres_sqlalchemy_url,
)
from api.services.knowledge_document_service import (
    KnowledgeDocumentPayload,
    KnowledgeSearchResultPayload,
    content_to_document as _content_to_document,
    content_visible_to_owner as _content_visible_to_owner,
    int_value as _int_value,
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
    KnowledgeIngestOverrides,
    KnowledgeIngestProfile,
    KnowledgeReader,
    KnowledgeReaderConfig,
    coerce_ingest_overrides as _coerce_ingest_overrides,
    profile_for_filename as _profile_for_filename,
    profile_for_filename_or_strategy as _profile_for_filename_or_strategy,
    reader_for_profile as _reader_for_profile,
)
from api.services.knowledge_rag_settings_service import (
    COLD_START_NOTE,
    current_rag_settings,
    knowledge_settings,
    model_device,
    pipeline_status,
    search_type_from_env,
    search_type_from_name,
    update_runtime_rag_settings as _update_runtime_rag_settings,
)
from api.services.knowledge_runtime_service import (
    KnowledgeRuntimeDependencies,
    KnowledgeRuntimeSettings,
    build_knowledge_base,
    retrieval_candidate_limit,
)
from api.services.knowledge_source_service import (
    SOURCE_METADATA_KEY,
    ainsert_source_snapshot_async,
    mapping_metadata,
    metadata_with_source_ref,
    path_source_snapshot,
    resolve_existing_file_async,
    safe_public_metadata,
    source_digest,
    source_ref as make_source_ref,
    text_source_snapshot,
)
from api.services.knowledge_progress import emit_progress
from api.services.knowledge_upload_service import remove_managed_upload_async

_knowledge_async_lock = asyncio.Lock()
_knowledge_runtime_async_lock = asyncio.Lock()


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


def _clear_knowledge_runtime_caches() -> None:
    get_settings.cache_clear()
    _get_embedder.cache_clear()
    _get_reranker.cache_clear()
    get_async_knowledge_base.cache_clear()


def _clean_optional_metadata_text(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field}不能为空")
    return text


def _safe_metadata_patch(metadata: Mapping[str, object] | None) -> dict[str, object]:
    blocked_keys = {"owner_user_id", "user_id", "visibility", "source", "title"}
    return {
        key: value
        for key, value in _safe_metadata(metadata).items()
        if not key.startswith("_") and key not in blocked_keys
    }


def update_runtime_rag_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    return _update_runtime_rag_settings(
        values,
        clear_runtime_caches=_clear_knowledge_runtime_caches,
    )


def _reader_config(
    needs_embedder: bool,
    overrides: KnowledgeIngestOverrides | None = None,
) -> KnowledgeReaderConfig:
    settings = knowledge_settings()
    options = overrides or KnowledgeIngestOverrides()
    chunk_size = options.chunk_size or settings.chunk_size
    chunk_overlap = (
        options.chunk_overlap
        if options.chunk_overlap is not None
        else settings.chunk_overlap
    )
    return KnowledgeReaderConfig(
        embedder=_get_embedder() if needs_embedder else None,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        markdown_split_on_headings=options.markdown_split_on_headings,
        csv_skip_header=options.csv_skip_header is True,
        csv_clean_rows=True if options.csv_clean_rows is None else options.csv_clean_rows,
        code_chunk_size=options.code_chunk_size or settings.code_chunk_size,
        code_tokenizer=options.code_tokenizer or "character",
        code_include_nodes=options.code_include_nodes is True,
        semantic_threshold=(
            options.semantic_threshold
            if options.semantic_threshold is not None
            else settings.semantic_threshold
        ),
        semantic_similarity_window=options.semantic_similarity_window,
        semantic_min_sentences_per_chunk=options.semantic_min_sentences_per_chunk,
        semantic_min_characters_per_sentence=options.semantic_min_characters_per_sentence,
    )


def knowledge_profile_for_filename(filename: str | None) -> KnowledgeIngestProfile:
    return _profile_for_filename(filename)


def knowledge_profile_for_filename_or_strategy(
    filename: str | None,
    strategy: str | None,
) -> KnowledgeIngestProfile:
    return _profile_for_filename_or_strategy(filename, strategy)


def _metadata_ingest_options(overrides: KnowledgeIngestOverrides) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if overrides.chunk_size is not None:
        metadata["chunk_size"] = str(overrides.chunk_size)
    if overrides.chunk_overlap is not None:
        metadata["chunk_overlap"] = str(overrides.chunk_overlap)
    if overrides.markdown_split_on_headings is not None:
        metadata["markdown_split_on_headings"] = str(overrides.markdown_split_on_headings)
    if overrides.csv_skip_header is not None:
        metadata["csv_skip_header"] = str(overrides.csv_skip_header).lower()
    if overrides.csv_clean_rows is not None:
        metadata["csv_clean_rows"] = str(overrides.csv_clean_rows).lower()
    if overrides.code_chunk_size is not None:
        metadata["code_chunk_size"] = str(overrides.code_chunk_size)
    if overrides.code_tokenizer is not None:
        metadata["code_tokenizer"] = overrides.code_tokenizer
    if overrides.code_include_nodes is not None:
        metadata["code_include_nodes"] = str(overrides.code_include_nodes).lower()
    if overrides.semantic_threshold is not None:
        metadata["semantic_threshold"] = str(overrides.semantic_threshold)
    if overrides.semantic_similarity_window is not None:
        metadata["semantic_similarity_window"] = str(overrides.semantic_similarity_window)
    if overrides.semantic_min_sentences_per_chunk is not None:
        metadata["semantic_min_sentences_per_chunk"] = str(overrides.semantic_min_sentences_per_chunk)
    if overrides.semantic_min_characters_per_sentence is not None:
        metadata["semantic_min_characters_per_sentence"] = str(overrides.semantic_min_characters_per_sentence)
    if overrides.reader_strategy is not None:
        metadata["reader_strategy"] = overrides.reader_strategy
    return metadata


def reader_for_profile(
    profile: KnowledgeIngestProfile,
    filename: str | None = None,
    overrides: KnowledgeIngestOverrides | None = None,
) -> KnowledgeReader:
    return _reader_for_profile(
        profile,
        _reader_config(
            needs_embedder=profile.strategy == "semantic",
            overrides=overrides,
        ),
        filename,
    )


def reader_for_filename(
    filename: str | None,
    overrides: Mapping[str, object] | KnowledgeIngestOverrides | None = None,
) -> KnowledgeReader:
    ingest_overrides = (
        overrides
        if isinstance(overrides, KnowledgeIngestOverrides)
        else _coerce_ingest_overrides(overrides)
    )
    profile = knowledge_profile_for_filename_or_strategy(
        filename,
        ingest_overrides.reader_strategy,
    )
    return _reader_for_profile(
        profile,
        _reader_config(
            needs_embedder=profile.strategy == "semantic",
            overrides=ingest_overrides,
        ),
        filename,
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


def _knowledge_contents_projection_table() -> Table:
    settings = knowledge_settings()
    return Table(
        settings.postgres_knowledge_table,
        MetaData(schema=settings.postgres_schema),
        Column("id", Text),
        Column("name", Text),
        Column("description", Text),
        Column("metadata", JSONB),
        Column("type", Text),
        Column("size", Integer),
        Column("linked_to", Text),
        Column("access_count", Integer),
        Column("status", Text),
        Column("status_message", Text),
        Column("created_at", Integer),
        Column("updated_at", Integer),
        Column("external_id", Text),
    )


def _visible_metadata_clause(metadata_column: Any, owner_user_id: str | None) -> Any:
    clean_owner = (owner_user_id or "").strip()
    if not clean_owner:
        return None
    return or_(
        metadata_column["visibility"].astext == "public",
        metadata_column["owner_user_id"].astext == clean_owner,
        metadata_column["user_id"].astext == clean_owner,
    )


async def _knowledge_document_page_rows_async(
    *,
    owner_user_id: str | None,
    query: str | None,
    page: int,
    limit: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[KnowledgeRow], int]:
    table = _knowledge_contents_projection_table()
    stmt = select(table).where(table.c.linked_to == knowledge_settings().name)
    visibility_clause = _visible_metadata_clause(table.c.metadata, owner_user_id)
    if visibility_clause is not None:
        stmt = stmt.where(visibility_clause)
    clean_query = (query or "").strip().casefold()
    if clean_query:
        search_value = f"%{clean_query}%"
        stmt = stmt.where(
            func.lower(
                func.concat_ws(
                    " ",
                    table.c.id,
                    table.c.name,
                    table.c.description,
                    sql_cast(table.c.metadata, Text),
                )
            ).like(search_value)
        )

    total_stmt = select(func.count()).select_from(stmt.subquery())
    sort_columns = {
        "created_at": table.c.created_at,
        "name": func.lower(table.c.name),
        "status": func.lower(table.c.status),
        "updated_at": table.c.updated_at,
    }
    sort_column = sort_columns.get(sort_by, table.c.updated_at)
    stmt = stmt.order_by(sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc())
    safe_page = max(1, page)
    safe_limit = min(100, max(1, limit))
    stmt = stmt.limit(safe_limit).offset((safe_page - 1) * safe_limit)

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(total_stmt)).scalar() or 0)
        rows = (await conn.execute(stmt)).mappings().all()
    return [KnowledgeRow.model_validate(dict(row)) for row in rows], total


def _chunk_counts_by_content_id_statement(owner_user_id: str | None = None) -> Any:
    table = _pgvector_projection_table()
    stmt = select(table.c.content_id, func.count()).where(table.c.content_id.is_not(None))
    visibility_clause = _visible_metadata_clause(table.c.meta_data, owner_user_id)
    if visibility_clause is not None:
        stmt = stmt.where(visibility_clause)
    return stmt.group_by(table.c.content_id)


async def _chunk_counts_by_content_id_async(owner_user_id: str | None = None) -> dict[str, int]:
    stmt = _chunk_counts_by_content_id_statement(owner_user_id)
    try:
        async with get_async_control_plane_engine().begin() as conn:
            rows = (await conn.execute(stmt)).all()
    except Exception:
        return {}
    return {str(content_id): int(count) for content_id, count in rows if content_id}


async def _chunk_count_async(owner_user_id: str | None = None) -> int:
    table = _pgvector_projection_table()
    stmt = select(func.count()).select_from(table)
    visibility_clause = _visible_metadata_clause(table.c.meta_data, owner_user_id)
    if visibility_clause is not None:
        stmt = stmt.where(visibility_clause)
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


async def _delete_content_async(knowledge: Any, content_id: str) -> None:
    if knowledge is None:
        knowledge = await _get_async_knowledge_base_async()
    await knowledge.aremove_content_by_id(content_id)


async def _latest_inserted_content_async(
    knowledge: Any,
    *,
    title: str,
    source: str,
    source_ref: Mapping[str, object],
) -> Any | None:
    contents, _ = await knowledge.aget_content(
        limit=20,
        page=1,
        sort_by="updated_at",
        sort_order="desc",
    )
    expected_digest = source_ref.get("digest")
    for content in contents:
        metadata = _safe_metadata(getattr(content, "metadata", None))
        ref = metadata.get(SOURCE_METADATA_KEY)
        if isinstance(ref, Mapping) and ref.get("digest") == expected_digest:
            return content
    for content in contents:
        metadata = _safe_metadata(getattr(content, "metadata", None))
        if getattr(content, "name", None) == title and metadata.get("source") == source:
            return content
    return None


async def _document_status_async(content_id: str) -> KnowledgeDocumentPayload | None:
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
    store_source_async: Callable[[str, Mapping[str, object]], Any] | None = None
    get_source_async: Callable[[str], Any] | None = None
    chunk_counts_by_content_id_async: Callable[[str | None], Any] | None = None
    chunk_count_async: Callable[[str | None], Any] | None = None
    hydrate_content_ids_async: Callable[[list[Document]], Any] | None = None
    delete_content_async: Callable[[Any, str], Any] | None = None
    delete_source_async: Callable[[str], Any] | None = None


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
            result = self.dependencies.get_async_knowledge_base(search_type)
            if hasattr(result, "__await__"):
                return await result
            return result
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

    async def _store_source_async(
        self,
        content_id: str,
        source: Mapping[str, object],
    ) -> None:
        if self.dependencies.store_source_async is not None:
            result = self.dependencies.store_source_async(content_id, source)
            if hasattr(result, "__await__"):
                await result
            return
        await _upsert_knowledge_source_async(content_id, source)

    async def _get_source_async(self, content_id: str) -> dict[str, Any] | None:
        if self.dependencies.get_source_async is not None:
            result = self.dependencies.get_source_async(content_id)
            if hasattr(result, "__await__"):
                result = await result
            return dict(result) if isinstance(result, Mapping) else None
        return await _get_knowledge_source_async(content_id)

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
        else:
            await _delete_content_async(knowledge, content_id)
        await self._delete_source_async(content_id)

    async def _delete_source_async(self, content_id: str) -> None:
        if self.dependencies.delete_source_async is not None:
            result = self.dependencies.delete_source_async(content_id)
            if hasattr(result, "__await__"):
                await result
            return
        await _delete_knowledge_source_async(content_id)

    async def add_text_document_async(
        self,
        title: str,
        content: str,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
        owner_user_id: str | None = None,
        visibility: str = "private",
        ingest_options: Mapping[str, object] | None = None,
        on_progress=None,
    ) -> KnowledgeDocumentPayload:
        clean_title = title.strip() or "未命名知识"
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("知识内容不能为空")
        normalized_visibility = normalize_visibility(visibility, strict=True)

        base_metadata = _safe_metadata(metadata)
        filename = str(base_metadata.get("file_name") or clean_title)
        ingest_overrides = _coerce_ingest_overrides(ingest_options)
        profile = knowledge_profile_for_filename_or_strategy(
            filename,
            ingest_overrides.reader_strategy,
        )
        clean_source = source.strip() or "manual"
        safe_metadata = {
            **base_metadata,
            **_metadata_ingest_options(ingest_overrides),
            **_owner_metadata(owner_user_id, normalized_visibility),
            "title": clean_title,
            "source": clean_source,
            "file_type": Path(filename).suffix.lower() or "text",
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": base_metadata.get("input_mode", "manual"),
        }
        source_reference = make_source_ref("text", source_digest(clean_content))
        safe_metadata = metadata_with_source_ref(safe_metadata, source_reference)
        source_snapshot = text_source_snapshot(
            name=clean_title,
            description=clean_source,
            text_content=clean_content,
            metadata=safe_metadata,
            filename=filename,
        )
        knowledge = await self._async_knowledge_async()
        await emit_progress(
            on_progress,
            "parse",
            "running",
            message="解析中",
            detail={"file_name": filename},
        )
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await emit_progress(
                on_progress,
                "parse",
                "completed",
                message="已解析",
                detail={"file_name": filename},
            )
            await emit_progress(
                on_progress,
                "vectorize",
                "running",
                message="向量化中",
                detail={"file_name": filename},
            )
            try:
                await knowledge.ainsert(
                    name=clean_title,
                    description=clean_source,
                    text_content=clean_content,
                    metadata=safe_metadata,
                    reader=reader_for_profile(profile, filename, ingest_overrides),
                    upsert=True,
                    skip_if_exists=False,
                )
            except Exception as exc:
                await emit_progress(
                    on_progress,
                    "vectorize",
                    "failed",
                    message="失败",
                    error=str(exc),
                )
                raise
            await emit_progress(
                on_progress,
                "vectorize",
                "completed",
                message="已写入",
                detail={"file_name": filename},
            )
        inserted = await _latest_inserted_content_async(
            knowledge,
            title=clean_title,
            source=clean_source,
            source_ref=source_reference,
        )
        if inserted is not None:
            await emit_progress(
                on_progress,
                "cleanup",
                "running",
                message="保存中",
                detail={"content_id": str(inserted.id)},
            )
            await self._store_source_async(str(inserted.id), source_snapshot)
            document = _content_to_document(inserted)
            await emit_progress(
                on_progress,
                "cleanup",
                "completed",
                message="完成",
                document=document,
            )
            return document
        raise RuntimeError("知识写入完成但未能读取内容登记记录")

    async def add_file_document_async(
        self,
        path: str,
        title: str | None = None,
        source: str | None = None,
        metadata: Mapping[str, object] | None = None,
        owner_user_id: str | None = None,
        visibility: str = "private",
        ingest_options: Mapping[str, object] | None = None,
        on_progress=None,
    ) -> KnowledgeDocumentPayload:
        file_path = await resolve_existing_file_async(path)
        if file_path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
            supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
            raise ValueError(f"当前知识库支持的文件后缀: {supported}")
        normalized_visibility = normalize_visibility(visibility, strict=True)

        clean_title = (title or file_path.stem).strip() or file_path.stem
        clean_source = (source or str(file_path)).strip() or str(file_path)
        base_metadata = _safe_metadata(metadata)
        ingest_overrides = _coerce_ingest_overrides(ingest_options)
        profile = knowledge_profile_for_filename_or_strategy(
            file_path.name,
            ingest_overrides.reader_strategy,
        )
        safe_metadata = {
            **base_metadata,
            **_metadata_ingest_options(ingest_overrides),
            **_owner_metadata(owner_user_id, normalized_visibility),
            "title": clean_title,
            "source": clean_source,
            "file_path": str(file_path),
            "file_name": str(base_metadata.get("file_name") or file_path.name),
            "file_type": file_path.suffix.lower(),
            "file_size": base_metadata.get("file_size", file_path.stat().st_size),
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": base_metadata.get("input_mode", "path"),
        }
        safe_metadata = metadata_with_source_ref(
            safe_metadata,
            make_source_ref("path", source_digest(str(file_path))),
        )
        source_snapshot = path_source_snapshot(
            name=clean_title,
            description=clean_source,
            path=str(file_path),
            metadata=safe_metadata,
            filename=file_path.name,
        )
        reader = reader_for_profile(profile, file_path.name, ingest_overrides)
        knowledge = await self._async_knowledge_async()
        await emit_progress(
            on_progress,
            "parse",
            "running",
            message="解析中",
            detail={"file_name": file_path.name},
        )
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await emit_progress(
                on_progress,
                "parse",
                "completed",
                message="已解析",
                detail={"file_name": file_path.name},
            )
            await emit_progress(
                on_progress,
                "vectorize",
                "running",
                message="向量化中",
                detail={"file_name": file_path.name},
            )
            try:
                await knowledge.ainsert(
                    name=clean_title,
                    description=clean_source,
                    path=str(file_path),
                    metadata=safe_metadata,
                    reader=reader,
                    upsert=True,
                    skip_if_exists=False,
                )
            except Exception as exc:
                await emit_progress(
                    on_progress,
                    "vectorize",
                    "failed",
                    message="失败",
                    error=str(exc),
                )
                raise
            await emit_progress(
                on_progress,
                "vectorize",
                "completed",
                message="已写入",
                detail={"file_name": file_path.name},
            )
        contents, _ = await knowledge.aget_content(
            limit=1,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        for content_row in contents:
            if content_row.name == clean_title:
                await emit_progress(
                    on_progress,
                    "cleanup",
                    "running",
                    message="保存中",
                    detail={"content_id": str(content_row.id)},
                )
                await self._store_source_async(str(content_row.id), source_snapshot)
                document = _content_to_document(content_row)
                await emit_progress(
                    on_progress,
                    "cleanup",
                    "completed",
                    message="完成",
                    document=document,
                )
                return document
        raise RuntimeError("知识写入完成但未能读取内容登记记录")

    async def list_documents_async(self, owner_user_id: str | None = None) -> list[KnowledgeDocumentPayload]:
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

    async def list_documents_page_async(
        self,
        *,
        owner_user_id: str | None = None,
        query: str | None = None,
        page: int = 1,
        limit: int = 50,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[KnowledgeDocumentPayload], int]:
        if self.dependencies.knowledge_content_rows_async is None:
            await self._ensure_contents_storage_async()
            contents, total = await _knowledge_document_page_rows_async(
                owner_user_id=owner_user_id,
                query=query,
                page=page,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            chunk_counts = await self._chunk_counts_by_content_id_async(owner_user_id)
            documents: list[KnowledgeDocumentPayload] = []
            for content in contents:
                document = _content_to_document(content)
                document["chunks"] = chunk_counts.get(document["id"], document["chunks"])
                documents.append(document)
            return documents, total

        documents = await self.list_documents_async(owner_user_id=owner_user_id)
        return self.paginate_documents(
            documents,
            query=query,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @staticmethod
    def paginate_documents(
        documents: list[KnowledgeDocumentPayload],
        *,
        query: str | None = None,
        page: int = 1,
        limit: int = 50,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[KnowledgeDocumentPayload], int]:
        documents = list(documents)
        clean_query = (query or "").strip().casefold()
        if clean_query:
            documents = [
                document
                for document in documents
                if clean_query
                in " ".join(
                    (
                        document["id"],
                        document["title"],
                        document["source"],
                        *document["metadata"].values(),
                    )
                ).casefold()
            ]

        sort_keys: dict[str, Callable[[KnowledgeDocumentPayload], str]] = {
            "created_at": lambda document: document["created_at"],
            "name": lambda document: document["title"].casefold(),
            "status": lambda document: document["status"],
            "updated_at": lambda document: document["updated_at"] or document["created_at"],
        }
        key = sort_keys.get(sort_by, sort_keys["updated_at"])
        documents.sort(key=key, reverse=sort_order.lower() != "asc")
        total = len(documents)
        safe_page = max(1, page)
        safe_limit = min(100, max(1, limit))
        start = (safe_page - 1) * safe_limit
        return documents[start : start + safe_limit], total

    async def delete_document_async(
        self,
        doc_id: str,
        owner_user_id: str | None = None,
        user: ActorLike | None = None,
    ) -> bool:
        await self._ensure_contents_storage_async()
        content = await self._knowledge_content_by_id_async(doc_id)
        if content is None:
            return False
        metadata = _safe_metadata(getattr(content, "metadata", None))
        if user is not None:
            if not can_manage_resource(user, metadata):
                return False
        elif not _content_visible_to_owner(content, owner_user_id):
            return False
        knowledge = (
            await self._async_knowledge_async()
            if self.dependencies.delete_content_async is None
            else None
        )
        await self._delete_content_async(knowledge, doc_id)
        await remove_managed_upload_async(metadata)
        return True

    async def rebuild_document_async(
        self,
        doc_id: str,
        owner_user_id: str | None = None,
        user: ActorLike | None = None,
        title: str | None = None,
        source: str | None = None,
        visibility: str | None = None,
        metadata: Mapping[str, object] | None = None,
        ingest_options: Mapping[str, object] | None = None,
        on_progress=None,
    ) -> KnowledgeDocumentPayload | None:
        await self._ensure_contents_storage_async()
        content = await self._knowledge_content_by_id_async(doc_id)
        if content is None:
            return None
        if user is not None:
            if not can_manage_resource(user, _safe_metadata(getattr(content, "metadata", None))):
                return None
        elif not _content_visible_to_owner(content, owner_user_id):
            return None
        knowledge = await self._async_knowledge_async()
        source_snapshot = await self._get_source_async(doc_id)
        if source_snapshot is None:
            raise ValueError("当前知识记录缺少可重建的原始 source 快照，请重新导入后再重建")
        current_metadata = _safe_metadata(getattr(content, "metadata", None))
        active_source_snapshot = dict(source_snapshot)
        source_metadata = mapping_metadata(active_source_snapshot.get("metadata"))
        restore_metadata = current_metadata or source_metadata
        next_title = _clean_optional_metadata_text(title, "文档标题")
        next_source = _clean_optional_metadata_text(source, "来源")
        next_visibility = (
            normalize_visibility(visibility, strict=True)
            if visibility is not None
            else None
        )
        metadata_patch = _safe_metadata_patch(metadata)
        if next_title is not None:
            active_source_snapshot["name"] = next_title
            source_metadata["title"] = next_title
            restore_metadata = {**restore_metadata, "title": next_title}
        if next_source is not None:
            active_source_snapshot["description"] = next_source
            source_metadata["source"] = next_source
            restore_metadata = {**restore_metadata, "source": next_source}
        if next_visibility is not None:
            source_metadata["visibility"] = next_visibility
            restore_metadata = {**restore_metadata, "visibility": next_visibility}
        if metadata_patch:
            source_metadata = {**source_metadata, **metadata_patch}
            restore_metadata = {**restore_metadata, **metadata_patch}
        if ingest_options:
            filename = str(
                active_source_snapshot.get("filename")
                or source_metadata.get("file_name")
                or getattr(content, "name", "")
            ).strip()
            ingest_overrides = _coerce_ingest_overrides(ingest_options)
            profile = knowledge_profile_for_filename_or_strategy(
                filename,
                ingest_overrides.reader_strategy,
            )
            override_metadata = {
                **_metadata_ingest_options(ingest_overrides),
                "chunk_strategy": profile.strategy,
                "reader": profile.reader,
            }
            source_metadata = {**source_metadata, **override_metadata}
            restore_metadata = {**restore_metadata, **override_metadata}
        if (
            metadata_patch
            or next_title is not None
            or next_source is not None
            or next_visibility is not None
            or ingest_options
        ):
            active_source_snapshot["metadata"] = source_metadata
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await emit_progress(
                on_progress,
                "parse",
                "running",
                message="重建中",
                detail={"content_id": doc_id},
            )
            await ainsert_source_snapshot_async(
                knowledge,
                active_source_snapshot,
                reader_for_filename=reader_for_filename,
                content_id=doc_id,
                on_progress=on_progress,
            )
            if restore_metadata and restore_metadata != source_metadata:
                patched = await knowledge.apatch_content(
                    Content(id=doc_id, metadata=restore_metadata)
                )
                if patched is None:
                    raise RuntimeError("知识重建完成但未能恢复当前 Metadata")
            if (
                metadata_patch
                or next_title is not None
                or next_source is not None
                or next_visibility is not None
                or ingest_options
            ):
                await self._store_source_async(doc_id, active_source_snapshot)
        await emit_progress(
            on_progress,
            "cleanup",
            "running",
            message="保存中",
            detail={"content_id": doc_id},
        )
        refreshed = await self._knowledge_content_by_id_async(doc_id)
        if refreshed is None:
            raise RuntimeError("知识重建完成但未能读取内容登记记录")
        document = _content_to_document(refreshed)
        await emit_progress(
            on_progress,
            "cleanup",
            "completed",
            message="完成",
            document=document,
        )
        return document

    async def replace_document_source_async(
        self,
        doc_id: str,
        *,
        content: str,
        file_name: str,
        title: str | None = None,
        source: str | None = None,
        visibility: str | None = None,
        metadata: dict[str, Any] | None = None,
        owner_user_id: str | None = None,
        user: ActorLike | None = None,
        ingest_options: Mapping[str, object] | None = None,
        on_progress=None,
    ) -> KnowledgeDocumentPayload | None:
        await self._ensure_contents_storage_async()
        current = await self._knowledge_content_by_id_async(doc_id)
        if current is None:
            return None
        current_metadata = _safe_metadata(getattr(current, "metadata", None))
        if user is not None:
            if not can_manage_resource(user, current_metadata):
                return None
        elif not _content_visible_to_owner(current, owner_user_id):
            return None

        clean_content = content.strip()
        if not clean_content:
            raise ValueError("知识内容不能为空")
        clean_file_name = Path(file_name.strip()).name
        if not clean_file_name:
            raise ValueError("source 文件名不能为空")
        suffix = Path(clean_file_name).suffix.lower()
        if suffix not in SUPPORTED_FILE_SUFFIXES:
            supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
            raise ValueError(f"当前知识库支持的文件后缀: {supported}")

        clean_title = (
            title
            or getattr(current, "name", None)
            or current_metadata.get("title")
            or Path(clean_file_name).stem
        )
        clean_title = str(clean_title).strip() or Path(clean_file_name).stem
        clean_source = (
            source
            or current_metadata.get("source")
            or f"upload:{clean_file_name}"
        )
        clean_source = str(clean_source).strip() or f"upload:{clean_file_name}"
        owner = str(
            current_metadata.get("owner_user_id")
            or current_metadata.get("user_id")
            or owner_user_id
            or ""
        ).strip()
        normalized_visibility = normalize_visibility(
            visibility
            if visibility is not None
            else str(current_metadata.get("visibility") or "private"),
            strict=visibility is not None,
        )
        ingest_overrides = _coerce_ingest_overrides(ingest_options)
        profile = knowledge_profile_for_filename_or_strategy(
            clean_file_name,
            ingest_overrides.reader_strategy,
        )
        source_reference = make_source_ref("text", source_digest(clean_content, clean_file_name))
        inherited_metadata = safe_public_metadata(current_metadata)
        for stale_key in ("file_path", "file_size", "mime_type"):
            inherited_metadata.pop(stale_key, None)
        metadata_patch = _safe_metadata(metadata)
        mime_type, _ = mimetypes.guess_type(clean_file_name)
        safe_metadata = {
            **inherited_metadata,
            **metadata_patch,
            **_metadata_ingest_options(ingest_overrides),
            **_owner_metadata(owner, normalized_visibility),
            "title": clean_title,
            "source": clean_source,
            "file_name": clean_file_name,
            "file_type": suffix or "text",
            "file_size": metadata_patch.get("file_size", len(clean_content.encode("utf-8"))),
            "mime_type": metadata_patch.get("mime_type", mime_type or "text/plain"),
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": "replacement",
            "upload_mode": "browser",
        }
        safe_metadata = metadata_with_source_ref(safe_metadata, source_reference)
        source_snapshot = text_source_snapshot(
            name=clean_title,
            description=clean_source,
            text_content=clean_content,
            metadata=safe_metadata,
            filename=clean_file_name,
        )
        knowledge = await self._async_knowledge_async()
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await emit_progress(
                on_progress,
                "parse",
                "running",
                message="解析中",
                detail={"content_id": doc_id, "file_name": clean_file_name},
            )
            await ainsert_source_snapshot_async(
                knowledge,
                source_snapshot,
                reader_for_filename=reader_for_filename,
                content_id=doc_id,
                on_progress=on_progress,
            )
            await emit_progress(
                on_progress,
                "cleanup",
                "running",
                message="清理中",
                detail={"content_id": doc_id},
            )
            await self._store_source_async(doc_id, source_snapshot)
            await remove_managed_upload_async(current_metadata)
            await emit_progress(
                on_progress,
                "cleanup",
                "completed",
                message="完成",
                detail={"content_id": doc_id},
            )

        refreshed = await self._knowledge_content_by_id_async(doc_id)
        if refreshed is None:
            raise RuntimeError("source 新版本写入完成但未能读取内容登记记录")
        document = _content_to_document(refreshed)
        return document

    async def replace_document_file_async(
        self,
        doc_id: str,
        *,
        path: str,
        title: str | None = None,
        source: str | None = None,
        visibility: str | None = None,
        metadata: Mapping[str, object] | None = None,
        owner_user_id: str | None = None,
        user: ActorLike | None = None,
        ingest_options: Mapping[str, object] | None = None,
        on_progress=None,
    ) -> KnowledgeDocumentPayload | None:
        await self._ensure_contents_storage_async()
        current = await self._knowledge_content_by_id_async(doc_id)
        if current is None:
            return None
        current_metadata = _safe_metadata(getattr(current, "metadata", None))
        if user is not None:
            if not can_manage_resource(user, current_metadata):
                return None
        elif not _content_visible_to_owner(current, owner_user_id):
            return None

        file_path = await resolve_existing_file_async(path)
        if file_path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
            supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
            raise ValueError(f"当前知识库支持的文件后缀: {supported}")

        clean_title = (
            title
            or getattr(current, "name", None)
            or current_metadata.get("title")
            or file_path.stem
        )
        clean_title = str(clean_title).strip() or file_path.stem
        clean_source = (
            source
            or current_metadata.get("source")
            or f"upload:{file_path.name}"
        )
        clean_source = str(clean_source).strip() or f"upload:{file_path.name}"
        owner = str(
            current_metadata.get("owner_user_id")
            or current_metadata.get("user_id")
            or owner_user_id
            or ""
        ).strip()
        normalized_visibility = normalize_visibility(
            visibility
            if visibility is not None
            else str(current_metadata.get("visibility") or "private"),
            strict=visibility is not None,
        )
        inherited_metadata = safe_public_metadata(current_metadata)
        for stale_key in (
            "file_path",
            "file_size",
            "mime_type",
            "_tais_managed_upload",
        ):
            inherited_metadata.pop(stale_key, None)
        metadata_patch = _safe_metadata(metadata)
        ingest_overrides = _coerce_ingest_overrides(ingest_options)
        profile = knowledge_profile_for_filename_or_strategy(
            file_path.name,
            ingest_overrides.reader_strategy,
        )
        mime_type, _ = mimetypes.guess_type(file_path.name)
        safe_metadata = {
            **inherited_metadata,
            **metadata_patch,
            **_metadata_ingest_options(ingest_overrides),
            **_owner_metadata(owner, normalized_visibility),
            "title": clean_title,
            "source": clean_source,
            "file_path": str(file_path),
            "file_name": str(metadata_patch.get("file_name") or file_path.name),
            "file_type": file_path.suffix.lower(),
            "file_size": metadata_patch.get("file_size", file_path.stat().st_size),
            "mime_type": metadata_patch.get("mime_type", mime_type or "application/octet-stream"),
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": "replacement",
            "upload_mode": metadata_patch.get("upload_mode", "browser"),
        }
        source_reference = make_source_ref("path", source_digest(str(file_path)))
        safe_metadata = metadata_with_source_ref(safe_metadata, source_reference)
        source_snapshot = path_source_snapshot(
            name=clean_title,
            description=clean_source,
            path=str(file_path),
            metadata=safe_metadata,
            filename=file_path.name,
        )
        knowledge = await self._async_knowledge_async()
        async with _knowledge_async_lock:
            await self._ensure_storage_async()
            await emit_progress(
                on_progress,
                "parse",
                "running",
                message="解析中",
                detail={"content_id": doc_id, "file_name": file_path.name},
            )
            await ainsert_source_snapshot_async(
                knowledge,
                source_snapshot,
                reader_for_filename=reader_for_filename,
                content_id=doc_id,
                on_progress=on_progress,
            )
            await emit_progress(
                on_progress,
                "cleanup",
                "running",
                message="清理中",
                detail={"content_id": doc_id},
            )
            await self._store_source_async(doc_id, source_snapshot)
            await remove_managed_upload_async(current_metadata)
            await emit_progress(
                on_progress,
                "cleanup",
                "completed",
                message="完成",
                detail={"content_id": doc_id},
            )

        refreshed = await self._knowledge_content_by_id_async(doc_id)
        if refreshed is None:
            raise RuntimeError("source 新版本写入完成但未能读取内容登记记录")
        document = _content_to_document(refreshed)
        return document

    async def update_document_visibility_async(
        self,
        doc_id: str,
        visibility: str,
        user: ActorLike,
    ) -> KnowledgeDocumentPayload | None:
        return await self.update_document_metadata_async(
            doc_id,
            visibility=visibility,
            user=user,
        )

    async def update_document_metadata_async(
        self,
        doc_id: str,
        *,
        title: str | None = None,
        source: str | None = None,
        visibility: str | None = None,
        metadata: Mapping[str, object] | None = None,
        user: ActorLike,
    ) -> KnowledgeDocumentPayload | None:
        await self._ensure_contents_storage_async()
        content = await self._knowledge_content_by_id_async(doc_id)
        if content is None:
            return None
        current_metadata = _safe_metadata(getattr(content, "metadata", None))
        if not can_manage_resource(user, current_metadata):
            return None

        next_title = _clean_optional_metadata_text(title, "文档标题")
        next_source = _clean_optional_metadata_text(source, "来源")
        next_visibility = (
            normalize_visibility(visibility, strict=True)
            if visibility is not None
            else None
        )
        metadata_patch = _safe_metadata_patch(metadata)
        if (
            next_title is None
            and next_source is None
            and next_visibility is None
            and not metadata_patch
        ):
            raise ValueError("至少提供一个可更新字段")

        patched_metadata = {
            **current_metadata,
            **metadata_patch,
        }
        if next_title is not None:
            patched_metadata["title"] = next_title
        if next_source is not None:
            patched_metadata["source"] = next_source
        if next_visibility is not None:
            patched_metadata["visibility"] = next_visibility

        source_snapshot = await self._get_source_async(doc_id)
        if source_snapshot is not None:
            updated_source_snapshot = dict(source_snapshot)
            if next_title is not None:
                updated_source_snapshot["name"] = next_title
            if next_source is not None:
                updated_source_snapshot["description"] = next_source
            updated_source_snapshot["metadata"] = patched_metadata
            await self._store_source_async(doc_id, updated_source_snapshot)

        knowledge = await self._async_knowledge_async()
        try:
            patched = await knowledge.apatch_content(
                Content(
                    id=doc_id,
                    name=next_title,
                    description=next_source,
                    metadata=patched_metadata,
                )
            )
        except Exception:
            if source_snapshot is not None:
                await self._store_source_async(doc_id, source_snapshot)
            raise
        if patched is None:
            if source_snapshot is not None:
                await self._store_source_async(doc_id, source_snapshot)
            return None

        if next_title is not None:
            content.name = next_title
        if next_source is not None:
            content.description = next_source
        content.metadata = patched_metadata

        return _content_to_document(content)

    async def clear_knowledge_base_async(
        self,
        owner_user_id: str | None = None,
        user: ActorLike | None = None,
    ) -> dict[str, Any]:
        await self._ensure_contents_storage_async()
        contents, _ = await self._knowledge_content_rows_async()
        managed_contents = [
            (content.id, _safe_metadata(getattr(content, "metadata", None)))
            for content in contents
            if content.id
            and (
                can_manage_resource(user, _safe_metadata(getattr(content, "metadata", None)))
                if user is not None
                else _content_visible_to_owner(content, owner_user_id)
            )
        ]
        knowledge = (
            await self._async_knowledge_async()
            if managed_contents and self.dependencies.delete_content_async is None
            else None
        )
        deleted_ids: list[str] = []
        failed_ids: list[str] = []
        for content_id, metadata in managed_contents:
            try:
                await self._delete_content_async(knowledge, content_id)
                await remove_managed_upload_async(metadata)
                deleted_ids.append(content_id)
            except Exception:
                failed_ids.append(content_id)
        remaining_documents = len(managed_contents) - len(deleted_ids)
        return {
            "documents": remaining_documents,
            "chunks": 0 if remaining_documents == 0 else await self._chunk_count_async(owner_user_id),
            "deleted_documents": len(deleted_ids),
            "deleted_ids": deleted_ids,
            "failed_ids": failed_ids,
        }

    async def search_documents_async(
        self,
        query: str,
        limit: int = 5,
        search_type: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[KnowledgeSearchResultPayload]:
        clean_query = query.strip()
        if not clean_query:
            return []
        effective_search_type = (
            search_type_from_name(search_type) if search_type else search_type_from_env()
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
        clean_owner = (owner_user_id or "").strip()
        if (owner_user_id or "").strip():
            documents = []
            for filters in (
                {"visibility": "public"},
                {"user_id": clean_owner},
            ):
                documents.extend(
                    await knowledge.asearch(
                        clean_query,
                        max_results=retrieval_limit,
                        filters=filters,
                        search_type=effective_search_type.value,
                    )
                )
        else:
            documents = await knowledge.asearch(
                clean_query,
                max_results=retrieval_limit,
                filters=None,
                search_type=effective_search_type.value,
            )
        await self._hydrate_content_ids_async(documents)
        results: list[KnowledgeSearchResultPayload] = []
        seen: set[tuple[str, str, str, int]] = set()
        for document in documents:
            result = _result_from_document(document)
            key = (
                result["doc_id"],
                result["title"],
                result["content"],
                result["chunk_index"],
            )
            if key in seen:
                continue
            seen.add(key)
            results.append(result)
        results.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return results[:limit]

    async def knowledge_status_async(
        self,
        owner_user_id: str | None = None,
        documents: Sequence[Mapping[str, object]] | None = None,
        document_count: int | None = None,
    ) -> dict[str, Any]:
        docs = documents
        if docs is None and document_count is None:
            docs = await self.list_documents_async(owner_user_id=owner_user_id)
        docs = docs or []
        visible_chunk_count = sum(_int_value(document.get("chunks")) for document in docs)
        chunk_count = max(await self._chunk_count_async(owner_user_id), visible_chunk_count)
        settings = knowledge_settings()
        device = model_device()
        return {
            **pipeline_status(),
            "collection": settings.pgvector_table,
            "storage": "pgvector",
            "database": postgres_label(settings.postgres_schema, settings.pgvector_table),
            "contents_db": postgres_label(settings.postgres_schema, settings.postgres_knowledge_table),
            "postgres_schema": settings.postgres_schema,
            "documents": document_count if document_count is not None else len(docs),
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
            "rerank_candidate_multiplier": settings.rerank_candidate_multiplier,
            "rerank_min_candidates": settings.rerank_min_candidates,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "rag_settings": current_rag_settings(),
            "cold_start_note": COLD_START_NOTE,
            "runtime_loaded": knowledge_runtime_loaded(),
            "torch_runtime_ok": find_spec("torch") is not None,
        }


DEFAULT_KNOWLEDGE_BASE_LIFECYCLE = KnowledgeBaseLifecycle()


def get_knowledge_base_lifecycle() -> KnowledgeBaseLifecycle:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE


async def update_rag_settings_async(values: Mapping[str, Any]) -> dict[str, Any]:
    async with _knowledge_runtime_async_lock:
        return await asyncio.to_thread(update_runtime_rag_settings, values)
