from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agno.vectordb.search import SearchType

from api.config import get_settings
from api.services.knowledge_ingest_service import pipeline_status as ingest_pipeline_status


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


COLD_START_NOTE = (
    "首次触发知识写入、向量检索或重排时会在线程中加载/下载本地模型，"
    "当前操作可能等待 30-120 秒，但不会阻塞其它页面请求。"
)

RAG_SETTING_ENV_KEYS: dict[str, str] = {
    "embedding_model": "AGNO_KNOWLEDGE_EMBEDDING_MODEL",
    "embedding_dimensions": "AGNO_KNOWLEDGE_EMBEDDING_DIMENSIONS",
    "rerank_model": "AGNO_KNOWLEDGE_RERANK_MODEL",
    "query_prompt": "AGNO_KNOWLEDGE_QUERY_PROMPT",
    "top_k": "AGNO_KNOWLEDGE_TOP_K",
    "chunk_size": "AGNO_KNOWLEDGE_CHUNK_SIZE",
    "chunk_overlap": "AGNO_KNOWLEDGE_CHUNK_OVERLAP",
    "code_chunk_size": "AGNO_KNOWLEDGE_CODE_CHUNK_SIZE",
    "semantic_threshold": "AGNO_KNOWLEDGE_SEMANTIC_THRESHOLD",
    "vector_score_weight": "AGNO_KNOWLEDGE_VECTOR_SCORE_WEIGHT",
    "content_language": "AGNO_KNOWLEDGE_CONTENT_LANGUAGE",
    "prefix_match": "AGNO_KNOWLEDGE_PREFIX_MATCH",
    "rerank_enabled": "AGNO_KNOWLEDGE_RERANK_ENABLED",
    "rerank_candidate_multiplier": "AGNO_KNOWLEDGE_RERANK_CANDIDATE_MULTIPLIER",
    "rerank_min_candidates": "AGNO_KNOWLEDGE_RERANK_MIN_CANDIDATES",
    "device": "AGNO_KNOWLEDGE_DEVICE",
    "search_type": "AGNO_KNOWLEDGE_SEARCH_TYPE",
}

RAG_BOOLEAN_FIELDS = {"prefix_match", "rerank_enabled"}
RAG_INTEGER_FIELDS = {
    "embedding_dimensions",
    "top_k",
    "chunk_size",
    "chunk_overlap",
    "code_chunk_size",
    "rerank_candidate_multiplier",
    "rerank_min_candidates",
}
RAG_FLOAT_FIELDS = {"semantic_threshold", "vector_score_weight"}
RAG_STRING_FIELDS = {
    "embedding_model",
    "rerank_model",
    "query_prompt",
    "content_language",
    "device",
    "search_type",
}


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


def model_device() -> str:
    device = knowledge_settings().model_device
    return "cpu" if device == "auto" else device


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


def parse_rag_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        clean_value = value.strip().lower()
        if clean_value in {"1", "true", "yes", "on"}:
            return True
        if clean_value in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field} 必须是布尔值")


def coerce_rag_setting_value(field: str, value: Any) -> str:
    if field in RAG_BOOLEAN_FIELDS:
        return "true" if parse_rag_bool(value, field=field) else "false"

    if field in RAG_INTEGER_FIELDS:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 必须是整数") from exc
        if parsed < 1 and field != "chunk_overlap":
            raise ValueError(f"{field} 必须大于 0")
        if field == "chunk_overlap" and parsed < 0:
            raise ValueError("chunk_overlap 必须大于等于 0")
        return str(parsed)

    if field in RAG_FLOAT_FIELDS:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 必须是数字") from exc
        if field in {"semantic_threshold", "vector_score_weight"} and not 0 <= parsed <= 1:
            raise ValueError(f"{field} 必须在 0 到 1 之间")
        return str(parsed)

    if field in RAG_STRING_FIELDS:
        parsed = str(value or "").strip()
        if field == "search_type":
            return search_type_from_name(parsed).value
        if field in {"embedding_model", "rerank_model"} and not parsed:
            raise ValueError(f"{field} 不能为空")
        return parsed

    raise ValueError(f"不支持的 RAG 参数: {field}")


def current_rag_settings() -> dict[str, Any]:
    settings = knowledge_settings()
    return {
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "rerank_model": settings.rerank_model,
        "query_prompt": settings.query_prompt,
        "top_k": settings.top_k,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "code_chunk_size": settings.code_chunk_size,
        "semantic_threshold": settings.semantic_threshold,
        "vector_score_weight": settings.vector_score_weight,
        "bm25_score_weight": round(1 - settings.vector_score_weight, 4),
        "content_language": settings.content_language,
        "prefix_match": settings.prefix_match,
        "rerank_enabled": settings.rerank_enabled,
        "rerank_candidate_multiplier": settings.rerank_candidate_multiplier,
        "rerank_min_candidates": settings.rerank_min_candidates,
        "device": settings.model_device,
        "search_type": search_type_from_name(settings.search_type).value,
    }


def pipeline_status() -> dict[str, Any]:
    settings = knowledge_settings()
    return ingest_pipeline_status(
        search_type=search_type_from_env().value,
        vector_score_weight=settings.vector_score_weight,
        prefix_match=settings.prefix_match,
        content_language=settings.content_language,
        semantic_threshold=settings.semantic_threshold,
        code_chunk_size=settings.code_chunk_size,
    )


def update_runtime_rag_settings(
    values: Mapping[str, Any],
    *,
    clear_runtime_caches: Callable[[], None],
) -> dict[str, Any]:
    updates: dict[str, str] = {}
    for field, value in values.items():
        if field not in RAG_SETTING_ENV_KEYS:
            continue
        updates[RAG_SETTING_ENV_KEYS[field]] = coerce_rag_setting_value(field, value)

    if not updates:
        return current_rag_settings()

    previous_values = {env_key: os.environ.get(env_key) for env_key in updates}
    try:
        for env_key, value in updates.items():
            os.environ[env_key] = value

        clear_runtime_caches()

        settings = knowledge_settings()
        if settings.chunk_overlap >= settings.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
    except Exception:
        for env_key, previous in previous_values.items():
            if previous is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = previous
        clear_runtime_caches()
        raise

    return current_rag_settings()
