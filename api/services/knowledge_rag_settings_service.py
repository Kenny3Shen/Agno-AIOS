from __future__ import annotations

from dataclasses import dataclass

from agno.vectordb.search import SearchType

from api.config import get_settings


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
    search_type: str


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
        search_type=settings.agno_knowledge_search_type,
    )


def search_type_from_name(value: str | None) -> SearchType:
    clean_value = (value or "").strip().lower()
    if not clean_value:
        return SearchType.hybrid
    try:
        return SearchType(clean_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SearchType)
        raise ValueError(f"不支持的 search_type: {value}. 可选值: {allowed}") from exc


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
