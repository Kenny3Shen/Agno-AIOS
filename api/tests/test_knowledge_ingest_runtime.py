from __future__ import annotations

from unittest.mock import patch

import pytest
from agno.knowledge.document import Document
from agno.vectordb.search import SearchType

from api.services import knowledge_ingest_service
from api.services import knowledge_rag_settings_service
from api.services import knowledge_runtime_service
from api.services import knowledge_service
from api.services.knowledge_ingest_service import (
    coerce_ingest_overrides,
    profile_for_filename_or_strategy,
    profile_for_strategy,
)
from api.tests.knowledge_fakes import FakeEmbedder


def reader_config(**overrides: object) -> knowledge_ingest_service.KnowledgeReaderConfig:
    values = {
        "embedder": FakeEmbedder(),
        "chunk_size": 1200,
        "chunk_overlap": 160,
        "markdown_split_on_headings": None,
        "csv_skip_header": False,
        "csv_clean_rows": True,
        "code_chunk_size": 1800,
        "code_tokenizer": "character",
        "code_include_nodes": False,
        "semantic_threshold": 0.52,
        "semantic_similarity_window": None,
        "semantic_min_sentences_per_chunk": None,
        "semantic_min_characters_per_sentence": None,
    }
    values.update(overrides)
    return knowledge_ingest_service.KnowledgeReaderConfig(**values)


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
        reader_config(),
        filename,
    )
    assert reader.__class__.__name__ == expected_reader


def test_javascript_code_reader_uses_explicit_language_to_avoid_auto_detection() -> None:
    reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_CODE,
        reader_config(),
        "policy.js",
    )

    chunking_strategy = reader.chunking_strategy
    assert chunking_strategy.__class__.__name__ == "CodeChunking"
    assert getattr(chunking_strategy, "language", None) == "javascript"


def test_markdown_heading_level_and_size_based_modes_configure_chunking() -> None:
    heading_reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_MARKDOWN,
        reader_config(markdown_split_on_headings=2, chunk_size=1400, chunk_overlap=0),
        "runbook.md",
    )
    size_reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_MARKDOWN,
        reader_config(markdown_split_on_headings=0, chunk_size=900),
        "runbook.md",
    )

    heading_strategy = heading_reader.chunking_strategy
    assert heading_strategy is not None
    assert heading_strategy.__class__.__name__ == "MarkdownHeadingChunking"
    assert getattr(heading_strategy, "split_on_headings", None) == 2
    assert getattr(heading_strategy, "chunk_size", None) == 1400
    assert getattr(size_reader.chunking_strategy, "split_on_headings", None) is False
    assert getattr(size_reader.chunking_strategy, "chunk_size", None) == 900

    chunks = heading_strategy.chunk(
        Document(
            id="runbook",
            name="Runbook",
            content="# Overview\nContext.\n\n## Operations\nDetails.\n\n### Escalation\nNested details.",
        )
    )
    assert [chunk.content for chunk in chunks] == [
        "# Overview\nContext.",
        "## Operations\nDetails.\n\n### Escalation\nNested details.",
    ]


def test_csv_row_options_configure_row_chunking() -> None:
    reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_CSV,
        reader_config(
            chunk_size=500,
            chunk_overlap=600,
            csv_skip_header=True,
            csv_clean_rows=False,
        ),
        "assets.csv",
    )

    assert getattr(reader.chunking_strategy, "skip_header", None) is True
    assert getattr(reader.chunking_strategy, "clean_rows", None) is False


def test_overlap_validation_only_applies_to_chunkers_that_use_overlap() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        knowledge_ingest_service.reader_for_profile(
            knowledge_ingest_service.PROFILE_MARKDOWN,
            reader_config(chunk_size=500, chunk_overlap=600),
            "runbook.md",
        )


def test_code_tokenizer_and_nodes_configure_code_chunking() -> None:
    reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_CODE,
        reader_config(
            code_chunk_size=2400,
            code_tokenizer="gpt2",
            code_include_nodes=True,
        ),
        "agent.py",
    )

    assert getattr(reader.chunking_strategy, "tokenizer", None) == "gpt2"
    assert getattr(reader.chunking_strategy, "chunk_size", None) == 2400
    assert getattr(reader.chunking_strategy, "include_nodes", None) is True


def test_semantic_advanced_options_configure_semantic_chunking() -> None:
    reader = knowledge_ingest_service.reader_for_profile(
        knowledge_ingest_service.PROFILE_TEXT,
        reader_config(
            semantic_threshold=0.64,
            semantic_similarity_window=4,
            semantic_min_sentences_per_chunk=2,
            semantic_min_characters_per_sentence=12,
        ),
        "notes.txt",
    )

    assert getattr(reader.chunking_strategy, "similarity_threshold", None) == 0.64
    assert getattr(reader.chunking_strategy, "similarity_window", None) == 4
    assert getattr(reader.chunking_strategy, "min_sentences_per_chunk", None) == 2
    assert getattr(reader.chunking_strategy, "min_characters_per_sentence", None) == 12


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
        similarity_threshold=0.35,
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
    assert captured["vector"]["similarity_threshold"] == 0.35
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


def test_current_ingest_defaults_only_expose_form_fields() -> None:
    defaults = knowledge_rag_settings_service.current_ingest_defaults()

    assert set(defaults) == {
        "chunk_size",
        "chunk_overlap",
        "code_chunk_size",
        "semantic_threshold",
        "search_type",
    }
    assert defaults["search_type"] == knowledge_service.search_type_from_env().value


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
            "markdown_split_on_headings": "2",
            "csv_skip_header": "true",
            "csv_clean_rows": "false",
            "code_chunk_size": "2200",
            "code_tokenizer": "gpt2",
            "code_include_nodes": "true",
            "semantic_threshold": "0.61",
            "semantic_similarity_window": "4",
            "semantic_min_sentences_per_chunk": "2",
            "semantic_min_characters_per_sentence": "12",
            "reader_strategy": "markdown",
        }
    )

    assert overrides.chunk_size == 1500
    assert overrides.chunk_overlap == 120
    assert overrides.markdown_split_on_headings == 2
    assert overrides.csv_skip_header is True
    assert overrides.csv_clean_rows is False
    assert overrides.code_chunk_size == 2200
    assert overrides.code_tokenizer == "gpt2"
    assert overrides.code_include_nodes is True
    assert overrides.semantic_threshold == 0.61
    assert overrides.semantic_similarity_window == 4
    assert overrides.semantic_min_sentences_per_chunk == 2
    assert overrides.semantic_min_characters_per_sentence == 12
    assert overrides.reader_strategy == "markdown"


def test_coerce_ingest_overrides_rejects_invalid_strategy_values() -> None:
    with pytest.raises(ValueError, match="markdown_split_on_headings"):
        coerce_ingest_overrides({"markdown_split_on_headings": 7})
    with pytest.raises(ValueError, match="code_tokenizer"):
        coerce_ingest_overrides({"code_tokenizer": "words"})
    with pytest.raises(ValueError, match="reader_strategy"):
        coerce_ingest_overrides({"reader_strategy": "spreadsheet"})
