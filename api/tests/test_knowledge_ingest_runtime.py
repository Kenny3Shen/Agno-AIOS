from __future__ import annotations

import os
from typing import get_type_hints
from unittest.mock import patch

import pytest
from agno.knowledge.embedder.sentence_transformer import SentenceTransformerEmbedder
from agno.knowledge.reranker.sentence_transformer import SentenceTransformerReranker
from agno.vectordb.search import SearchType

from api.services import knowledge_ingest_service
from api.services import knowledge_runtime_service
from api.services import knowledge_service
from api.services.knowledge_ingest_service import (
    coerce_ingest_overrides,
    profile_for_filename_or_strategy,
    profile_for_strategy,
)
from api.tests.knowledge_fakes import FakeEmbedder


@pytest.mark.parametrize(
    ("filename", "expected_strategy", "expected_reader"),
    [
        ("runbook.md", "markdown", "MarkdownReader"),
        ("events.csv", "csv_row", "CSVReader"),
        ("finding.json", "json", "JSONReader"),
        ("agent.py", "code", "TextReader"),
        ("incident.txt", "semantic", "TextReader"),
    ],
)
def test_suffix_profile_chooses_agno_aligned_chunkers(
    filename: str,
    expected_strategy: str,
    expected_reader: str,
) -> None:
    profile = knowledge_ingest_service.profile_for_filename(filename)
    assert profile.strategy == expected_strategy
    reader = knowledge_ingest_service.reader_for_profile(
        profile,
        knowledge_ingest_service.KnowledgeReaderConfig(
            embedder=FakeEmbedder(),
            chunk_size=1200,
            chunk_overlap=160,
            code_chunk_size=1800,
            semantic_threshold=0.52,
        ),
        filename,
    )
    assert reader.__class__.__name__ == expected_reader


def test_javascript_code_reader_uses_explicit_language_to_avoid_auto_detection() -> None:
    reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_CODE,
        knowledge_ingest_service.KnowledgeReaderConfig(
            embedder=FakeEmbedder(),
            chunk_size=1200,
            chunk_overlap=160,
            code_chunk_size=1800,
            semantic_threshold=0.52,
        ),
        "policy.js",
    )

    chunking_strategy = reader.chunking_strategy
    assert chunking_strategy.__class__.__name__ == "CodeChunking"
    assert getattr(chunking_strategy, "language", None) == "javascript"


def test_knowledge_service_keeps_profile_interface() -> None:
    profile = knowledge_service.knowledge_profile_for_filename("runbook.md")
    assert profile.strategy == "markdown"
    assert (
        knowledge_service.reader_for_profile(profile).__class__.__name__
        == "MarkdownReader"
    )


def test_runtime_candidate_limit_respects_rerank_policy() -> None:
    assert (
        knowledge_runtime_service.retrieval_candidate_limit(
            5,
            rerank_enabled=True,
            rerank_candidate_multiplier=3,
            rerank_min_candidates=10,
        )
        == 15
    )
    assert (
        knowledge_runtime_service.retrieval_candidate_limit(
            5,
            rerank_enabled=True,
            rerank_candidate_multiplier=1,
            rerank_min_candidates=10,
        )
        == 10
    )
    assert (
        knowledge_runtime_service.retrieval_candidate_limit(
            5,
            rerank_enabled=False,
            rerank_candidate_multiplier=3,
            rerank_min_candidates=10,
        )
        == 5
    )


def test_runtime_builds_agno_pgvector_knowledge_with_small_interface() -> None:
    captured: dict[str, dict[str, object]] = {}

    class FakePgVector:
        def __init__(self, **kwargs: object) -> None:
            captured["vector"] = kwargs

    class FakeKnowledge:
        def __init__(self, **kwargs: object) -> None:
            captured["knowledge"] = kwargs

    settings = knowledge_runtime_service.KnowledgeRuntimeSettings(
        name="security",
        description="Security KB",
        pgvector_table="vectors",
        postgres_schema="knowledge",
        db_url="postgresql://example",
        prefix_match=True,
        vector_score_weight=0.7,
        content_language="english",
        top_k=5,
        rerank_enabled=True,
        rerank_candidate_multiplier=3,
        rerank_min_candidates=10,
    )
    contents_db = object()
    readers = {"text": object()}
    with (
        patch.object(knowledge_runtime_service, "PgVector", FakePgVector),
        patch.object(knowledge_runtime_service, "Knowledge", FakeKnowledge),
    ):
        result = knowledge_runtime_service.build_knowledge_base(
            settings,
            knowledge_runtime_service.KnowledgeRuntimeDependencies(
                embedder=FakeEmbedder(), reranker=None, contents_db=contents_db
            ),
            search_type=SearchType.hybrid,
            readers=readers,
        )
    assert isinstance(result, FakeKnowledge)
    assert captured["vector"]["table_name"] == "vectors"
    assert captured["vector"]["schema"] == "knowledge"
    assert captured["vector"]["search_type"] == SearchType.hybrid
    assert captured["vector"]["prefix_match"] is True
    assert captured["knowledge"]["name"] == "security"
    assert captured["knowledge"]["contents_db"] == contents_db
    assert captured["knowledge"]["max_results"] == 15
    assert captured["knowledge"]["readers"] == readers


def test_knowledge_service_uses_agno_sentence_transformer_embedder() -> None:
    captured: dict[str, dict[str, object]] = {}

    class FakeSentenceTransformerEmbedder:
        def __init__(self, **kwargs: object) -> None:
            captured["embedder"] = kwargs

    with patch.object(
        knowledge_service,
        "SentenceTransformerEmbedder",
        FakeSentenceTransformerEmbedder,
    ):
        knowledge_service._get_embedder.cache_clear()
        embedder = knowledge_service._get_embedder()
        knowledge_service._get_embedder.cache_clear()

    assert isinstance(embedder, FakeSentenceTransformerEmbedder)
    assert captured["embedder"] == {
        "id": knowledge_service.knowledge_settings().embedding_model,
        "dimensions": knowledge_service.knowledge_settings().embedding_dimensions,
        "prompt": knowledge_service.knowledge_settings().query_prompt,
        "normalize_embeddings": True,
    }


def test_knowledge_service_uses_agno_sentence_transformer_reranker() -> None:
    captured: dict[str, dict[str, object]] = {}

    class FakeSentenceTransformerReranker:
        def __init__(self, **kwargs: object) -> None:
            captured["reranker"] = kwargs

    with patch.object(
        knowledge_service,
        "SentenceTransformerReranker",
        FakeSentenceTransformerReranker,
    ):
        knowledge_service._get_reranker.cache_clear()
        reranker = knowledge_service._get_reranker()
        knowledge_service._get_reranker.cache_clear()

    assert isinstance(reranker, FakeSentenceTransformerReranker)
    assert captured["reranker"] == {
        "model": knowledge_service.knowledge_settings().rerank_model,
    }


def test_knowledge_service_no_longer_exposes_custom_model_adapters() -> None:
    assert not hasattr(knowledge_service, "BGEKnowledgeEmbedder")
    assert not hasattr(knowledge_service, "FlagEmbeddingReranker")
    assert get_type_hints(knowledge_service._get_embedder)["return"] is SentenceTransformerEmbedder
    assert (
        get_type_hints(knowledge_service._get_reranker)["return"]
        == SentenceTransformerReranker | None
    )


def test_status_exposes_supported_suffixes_and_search_type() -> None:
    original = os.environ.get("AGNO_KNOWLEDGE_SEARCH_TYPE")
    os.environ["AGNO_KNOWLEDGE_SEARCH_TYPE"] = "hybrid"
    try:
        assert knowledge_service.search_type_from_env() == SearchType.hybrid
    finally:
        if original is None:
            os.environ.pop("AGNO_KNOWLEDGE_SEARCH_TYPE", None)
        else:
            os.environ["AGNO_KNOWLEDGE_SEARCH_TYPE"] = original
    status = knowledge_ingest_service.pipeline_status(
        search_type=knowledge_service.search_type_from_env().value,
        vector_score_weight=0.55,
        prefix_match=False,
        content_language="english",
        semantic_threshold=0.52,
        code_chunk_size=1800,
    )
    assert ".md" in status["supported_suffixes"]
    assert ".csv" in status["supported_suffixes"]
    assert ".py" in status["supported_suffixes"]
    assert status["search_type"] in {"vector", "keyword", "hybrid"}
    service_status = knowledge_service.pipeline_status()
    assert service_status["search_type"] == "hybrid"
    assert (
        service_status["code_chunk_size"]
        == knowledge_service.knowledge_settings().code_chunk_size
    )


def test_update_runtime_rag_settings_updates_env_and_rolls_back_invalid_overlap(monkeypatch) -> None:
    monkeypatch.setenv("AGNO_KNOWLEDGE_TOP_K", "5")
    monkeypatch.setenv("AGNO_KNOWLEDGE_CHUNK_SIZE", "1200")
    monkeypatch.setenv("AGNO_KNOWLEDGE_CHUNK_OVERLAP", "160")
    monkeypatch.setenv("AGNO_KNOWLEDGE_SEARCH_TYPE", "hybrid")
    knowledge_service._clear_knowledge_runtime_caches()
    try:
        settings = knowledge_service.update_runtime_rag_settings(
            {
                "top_k": 8,
                "search_type": "vector",
                "prefix_match": True,
                "vector_score_weight": 0.6,
            }
        )
        assert settings["top_k"] == 8
        assert settings["search_type"] == "vector"
        assert settings["prefix_match"] is True
        assert os.environ["AGNO_KNOWLEDGE_TOP_K"] == "8"
        assert os.environ["AGNO_KNOWLEDGE_SEARCH_TYPE"] == "vector"

        with pytest.raises(ValueError, match="chunk_overlap"):
            knowledge_service.update_runtime_rag_settings(
                {"chunk_size": 500, "chunk_overlap": 500}
            )
        assert os.environ["AGNO_KNOWLEDGE_CHUNK_SIZE"] == "1200"
        assert os.environ["AGNO_KNOWLEDGE_CHUNK_OVERLAP"] == "160"
    finally:
        knowledge_service._clear_knowledge_runtime_caches()


def test_profile_for_strategy_resolves_known_reader_strategy() -> None:
    profile = profile_for_strategy("csv_row")

    assert profile is not None
    assert profile.strategy == "csv_row"
    assert profile.reader == "CSVReader"


def test_profile_for_filename_or_strategy_prefers_explicit_strategy() -> None:
    profile = profile_for_filename_or_strategy("alerts.json", "code")

    assert profile.strategy == "code"
    assert profile.reader == "TextReader"


def test_coerce_ingest_overrides_normalizes_numeric_values() -> None:
    overrides = coerce_ingest_overrides(
        {
            "chunk_size": "1500",
            "chunk_overlap": 120,
            "code_chunk_size": "2200",
            "semantic_threshold": "0.61",
            "reader_strategy": "markdown",
        }
    )

    assert overrides.chunk_size == 1500
    assert overrides.chunk_overlap == 120
    assert overrides.code_chunk_size == 2200
    assert overrides.semantic_threshold == 0.61
    assert overrides.reader_strategy == "markdown"
