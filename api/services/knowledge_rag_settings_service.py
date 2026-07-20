from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agno.vectordb.search import SearchType

from api.config import get_settings
from api.persistence.knowledge_rag_settings import (
    get_knowledge_rag_settings_row,
    update_knowledge_rag_settings_row,
)
from api.utils.ttl_cache import TtlCache

_SETTINGS_CACHE: TtlCache[dict[str, Any]] = TtlCache(ttl_sec=5.0)


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
    similarity_threshold: float | None
    content_language: str
    prefix_match: bool
    rerank_enabled: bool
    rerank_candidate_multiplier: int
    rerank_min_candidates: int
    search_type: str


def normalize_similarity_threshold(value: float | None) -> float | None:
    """Return a usable PgVector similarity threshold, or None when disabled."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 1:
        return 1.0
    return number


def search_type_from_name(value: str | None) -> SearchType:
    clean_value = (value or "").strip().lower()
    if not clean_value:
        return SearchType.hybrid
    try:
        return SearchType(clean_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SearchType)
        raise ValueError(f"不支持的 search_type: {value}. 可选值: {allowed}") from exc


def _env_knowledge_settings() -> KnowledgeServiceSettings:
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
        similarity_threshold=settings.agno_knowledge_similarity_threshold,
        content_language=settings.agno_knowledge_content_language,
        prefix_match=settings.agno_knowledge_prefix_match,
        rerank_enabled=settings.agno_knowledge_rerank_enabled,
        rerank_candidate_multiplier=max(
            1,
            settings.agno_knowledge_rerank_candidate_multiplier,
        ),
        rerank_min_candidates=max(1, settings.agno_knowledge_rerank_min_candidates),
        search_type=settings.agno_knowledge_search_type,
    )


def _merge_runtime_overrides(
    base: KnowledgeServiceSettings,
    overrides: Mapping[str, Any] | None,
) -> KnowledgeServiceSettings:
    if not overrides:
        return base
    search_type = str(overrides.get("search_type") or base.search_type)
    try:
        search_type = search_type_from_name(search_type).value
    except ValueError:
        search_type = base.search_type
    top_k = overrides.get("top_k", base.top_k)
    vector_score_weight = overrides.get("vector_score_weight", base.vector_score_weight)
    similarity_threshold = overrides.get(
        "similarity_threshold", base.similarity_threshold
    )
    content_language = str(overrides.get("content_language") or base.content_language)
    prefix_match = overrides.get("prefix_match", base.prefix_match)
    rerank_enabled = overrides.get("rerank_enabled", base.rerank_enabled)
    rerank_candidate_multiplier = overrides.get(
        "rerank_candidate_multiplier", base.rerank_candidate_multiplier
    )
    rerank_min_candidates = overrides.get(
        "rerank_min_candidates", base.rerank_min_candidates
    )
    return KnowledgeServiceSettings(
        name=base.name,
        pgvector_table=base.pgvector_table,
        postgres_schema=base.postgres_schema,
        postgres_knowledge_table=base.postgres_knowledge_table,
        embedding_model=base.embedding_model,
        embedding_dimensions=base.embedding_dimensions,
        rerank_model=base.rerank_model,
        query_prompt=base.query_prompt,
        top_k=max(1, int(top_k)),
        chunk_size=base.chunk_size,
        chunk_overlap=base.chunk_overlap,
        code_chunk_size=base.code_chunk_size,
        semantic_threshold=base.semantic_threshold,
        vector_score_weight=float(vector_score_weight),
        similarity_threshold=normalize_similarity_threshold(
            float(similarity_threshold)
            if similarity_threshold is not None
            else None
        ),
        content_language=content_language,
        prefix_match=bool(prefix_match),
        rerank_enabled=bool(rerank_enabled),
        rerank_candidate_multiplier=max(1, int(rerank_candidate_multiplier)),
        rerank_min_candidates=max(1, int(rerank_min_candidates)),
        search_type=search_type,
    )


def knowledge_settings() -> KnowledgeServiceSettings:
    """Sync settings view used by hot retrieval paths.

    Prefer process cache of DB overrides when available; otherwise env defaults.
    Callers that need a guaranteed fresh DB read should use
    ``get_knowledge_rag_settings_async``.
    """
    base = _env_knowledge_settings()
    cached = _SETTINGS_CACHE.get()
    return _merge_runtime_overrides(base, cached)


def search_type_from_env() -> SearchType:
    return search_type_from_name(knowledge_settings().search_type)


def current_ingest_defaults() -> dict[str, int | float | str]:
    settings = knowledge_settings()
    return {
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "code_chunk_size": settings.code_chunk_size,
        "semantic_threshold": settings.semantic_threshold,
        "search_type": search_type_from_name(settings.search_type).value,
    }


def current_retrieval_settings() -> dict[str, object]:
    """PgVector / Agno retrieval knobs exposed to Settings UI and search meta."""
    settings = knowledge_settings()
    return {
        "search_type": search_type_from_name(settings.search_type).value,
        "top_k": settings.top_k,
        "vector_score_weight": settings.vector_score_weight,
        "similarity_threshold": normalize_similarity_threshold(
            settings.similarity_threshold
        ),
        "content_language": settings.content_language,
        "prefix_match": settings.prefix_match,
        "rerank_enabled": settings.rerank_enabled,
        "rerank_model": settings.rerank_model,
        "rerank_candidate_multiplier": settings.rerank_candidate_multiplier,
        "rerank_min_candidates": settings.rerank_min_candidates,
    }


def _project_settings(row: Mapping[str, Any]) -> dict[str, Any]:
    settings = _merge_runtime_overrides(_env_knowledge_settings(), row)
    return {
        "search_type": search_type_from_name(settings.search_type).value,
        "top_k": settings.top_k,
        "vector_score_weight": settings.vector_score_weight,
        "similarity_threshold": normalize_similarity_threshold(
            settings.similarity_threshold
        ),
        "content_language": settings.content_language,
        "prefix_match": settings.prefix_match,
        "rerank_enabled": settings.rerank_enabled,
        "rerank_model": settings.rerank_model,
        "rerank_candidate_multiplier": settings.rerank_candidate_multiplier,
        "rerank_min_candidates": settings.rerank_min_candidates,
    }


async def get_knowledge_rag_settings() -> dict[str, Any]:
    cached = _SETTINGS_CACHE.get()
    if cached is not None:
        return dict(cached)
    row = await get_knowledge_rag_settings_row()
    projected = _project_settings(row)
    _SETTINGS_CACHE.set(projected)
    return dict(projected)


async def get_knowledge_rag_settings_async() -> KnowledgeServiceSettings:
    values = await get_knowledge_rag_settings()
    return _merge_runtime_overrides(_env_knowledge_settings(), values)


def invalidate_knowledge_runtime_caches() -> None:
    """Drop process caches so the next retrieval rebuilds PgVector with new knobs."""
    _SETTINGS_CACHE.clear()
    try:
        from api.services.knowledge_service import (
            _get_embedder,
            _get_reranker,
            get_async_knowledge_base,
        )

        get_async_knowledge_base.cache_clear()
        _get_embedder.cache_clear()
        _get_reranker.cache_clear()
    except Exception:
        # Avoid import cycles / cold-start failures during tests.
        pass


async def update_knowledge_rag_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    if "search_type" in values:
        allowed["search_type"] = search_type_from_name(str(values["search_type"])).value
    if "top_k" in values and values["top_k"] is not None:
        allowed["top_k"] = max(1, min(50, int(values["top_k"])))
    if "vector_score_weight" in values and values["vector_score_weight"] is not None:
        weight = float(values["vector_score_weight"])
        if not 0.0 <= weight <= 1.0:
            raise ValueError("vector_score_weight must be between 0 and 1")
        allowed["vector_score_weight"] = weight
    if "similarity_threshold" in values:
        threshold = values["similarity_threshold"]
        if threshold is None or threshold == "":
            allowed["similarity_threshold"] = None
        else:
            allowed["similarity_threshold"] = normalize_similarity_threshold(
                float(threshold)
            )
    if "content_language" in values and values["content_language"] is not None:
        language = str(values["content_language"]).strip() or "english"
        allowed["content_language"] = language
    if "prefix_match" in values and values["prefix_match"] is not None:
        allowed["prefix_match"] = bool(values["prefix_match"])
    if "rerank_enabled" in values and values["rerank_enabled"] is not None:
        allowed["rerank_enabled"] = bool(values["rerank_enabled"])
    if (
        "rerank_candidate_multiplier" in values
        and values["rerank_candidate_multiplier"] is not None
    ):
        allowed["rerank_candidate_multiplier"] = max(
            1, min(20, int(values["rerank_candidate_multiplier"]))
        )
    if (
        "rerank_min_candidates" in values
        and values["rerank_min_candidates"] is not None
    ):
        allowed["rerank_min_candidates"] = max(
            1, min(100, int(values["rerank_min_candidates"]))
        )

    row = await update_knowledge_rag_settings_row(allowed)
    projected = _project_settings(row)
    invalidate_knowledge_runtime_caches()
    _SETTINGS_CACHE.set(projected)
    return dict(projected)


__all__ = [
    "KnowledgeServiceSettings",
    "current_ingest_defaults",
    "current_retrieval_settings",
    "get_knowledge_rag_settings",
    "get_knowledge_rag_settings_async",
    "invalidate_knowledge_runtime_caches",
    "knowledge_settings",
    "normalize_similarity_threshold",
    "search_type_from_env",
    "search_type_from_name",
    "update_knowledge_rag_settings",
]
