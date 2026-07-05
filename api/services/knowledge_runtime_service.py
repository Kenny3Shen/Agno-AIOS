from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agno.knowledge.embedder import Embedder
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.reranker.base import Reranker
from agno.vectordb.distance import Distance
from agno.vectordb.search import SearchType

from api.services.async_pgvector import AsyncPgVector


@dataclass(frozen=True)
class KnowledgeRuntimeSettings:
    name: str
    description: str
    pgvector_table: str
    postgres_schema: str
    db_url: str
    prefix_match: bool
    vector_score_weight: float
    content_language: str
    top_k: int
    rerank_enabled: bool
    rerank_candidate_multiplier: int
    rerank_min_candidates: int


@dataclass(frozen=True)
class KnowledgeRuntimeDependencies:
    embedder: Embedder
    reranker: Reranker | None
    contents_db: Any


def retrieval_candidate_limit(
    limit: int,
    *,
    rerank_enabled: bool,
    rerank_candidate_multiplier: int,
    rerank_min_candidates: int,
) -> int:
    if not rerank_enabled:
        return limit
    return max(limit * rerank_candidate_multiplier, rerank_min_candidates)


def build_knowledge_base(
    settings: KnowledgeRuntimeSettings,
    dependencies: KnowledgeRuntimeDependencies,
    *,
    search_type: SearchType,
    readers: dict[str, Any],
) -> Knowledge:
    vector_db = AsyncPgVector(
        table_name=settings.pgvector_table,
        schema=settings.postgres_schema,
        db_url=settings.db_url,
        embedder=dependencies.embedder,
        search_type=search_type,
        distance=Distance.cosine,
        prefix_match=settings.prefix_match,
        vector_score_weight=settings.vector_score_weight,
        content_language=settings.content_language,
        reranker=dependencies.reranker,
    )
    return Knowledge(
        name=settings.name,
        description=settings.description,
        vector_db=vector_db,
        contents_db=dependencies.contents_db,
        max_results=retrieval_candidate_limit(
            settings.top_k,
            rerank_enabled=settings.rerank_enabled,
            rerank_candidate_multiplier=settings.rerank_candidate_multiplier,
            rerank_min_candidates=settings.rerank_min_candidates,
        ),
        readers=readers,
    )
