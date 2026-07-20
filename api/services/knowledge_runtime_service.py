from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from agno.knowledge.embedder import Embedder
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.reranker.base import Reranker
from agno.vectordb.distance import Distance
from agno.vectordb.search import SearchType
from agno.vectordb.pgvector import PgVector



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
    similarity_threshold: float | None = None


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
    vector_db = PgVector(
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
        similarity_threshold=settings.similarity_threshold,
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


def document_retrieval_score(document: object) -> float:
    """Prefer rerank score, then vector/hybrid similarity metadata."""
    reranking_score = getattr(document, "reranking_score", None)
    if isinstance(reranking_score, (int, float)):
        return float(reranking_score)
    meta = getattr(document, "meta_data", None) or {}
    if not isinstance(meta, dict):
        return 0.0
    for key in ("rerank_score", "similarity_score"):
        value = meta.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (str, bytes, bytearray)):
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0


TDocument = TypeVar("TDocument")


def filter_documents_by_score(
    documents: list[TDocument],
    *,
    min_score: float | None,
    limit: int | None = None,
) -> list[TDocument]:
    """Drop low-score retrieval hits; empty results are allowed."""
    filtered: list[TDocument] = []
    threshold = None if min_score is None or min_score <= 0 else float(min_score)
    for document in documents:
        score = document_retrieval_score(document)
        if threshold is not None and score < threshold:
            continue
        filtered.append(document)
    if limit is not None and limit >= 0:
        return filtered[:limit]
    return filtered


def project_document_for_agent(document: object) -> dict[str, object]:
    """Project an Agno Document for tool output with explicit score fields."""
    content = str(getattr(document, "content", "") or "")
    name = getattr(document, "name", None)
    meta = getattr(document, "meta_data", None)
    metadata = dict(meta) if isinstance(meta, dict) else {}
    score = document_retrieval_score(document)
    if score and "rerank_score" not in metadata and getattr(document, "reranking_score", None) is not None:
        metadata["rerank_score"] = score
    if score and "similarity_score" not in metadata and "rerank_score" not in metadata:
        metadata["similarity_score"] = score
    metadata["score"] = round(float(score), 4)
    payload: dict[str, object] = {
        "content": content,
        "meta_data": metadata,
        "score": round(float(score), 4),
    }
    if name is not None:
        payload["name"] = name
    content_id = getattr(document, "content_id", None)
    if content_id is not None:
        payload["content_id"] = str(content_id)
    return payload


async def retrieve_knowledge_documents(
    knowledge: object,
    *,
    query: str,
    num_documents: int | None,
    filters: object | None = None,
    min_score: float | None = None,
) -> list[dict[str, object]]:
    """Retrieve docs, drop low scores, allow empty results."""
    max_results = num_documents
    if max_results is None:
        max_results = getattr(knowledge, "max_results", 10)
    aretrieve = getattr(knowledge, "aretrieve", None)
    retrieve = getattr(knowledge, "retrieve", None)
    documents: list[object]
    if callable(aretrieve):
        documents = await aretrieve(query=query, max_results=max_results, filters=filters)
    elif callable(retrieve):
        documents = retrieve(query=query, max_results=max_results, filters=filters)
    else:
        return []
    filtered = filter_documents_by_score(
        list(documents or []),
        min_score=min_score,
        limit=max_results if isinstance(max_results, int) else None,
    )
    return [project_document_for_agent(document) for document in filtered]

