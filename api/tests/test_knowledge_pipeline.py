from __future__ import annotations
import os
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from agno.knowledge.embedder import Embedder
from agno.vectordb.search import SearchType

from api.services import knowledge_document_service
from api.services import knowledge_ingest_service
from api.services import knowledge_runtime_service
from api.services import knowledge_service


class FakeEmbedder(Embedder):
    def __init__(self) -> None:
        super().__init__(dimensions=3)

    def get_embedding(self, text: str) -> list[float]:
        return [0.0, 0.0, float(len(text))]

    def get_embedding_and_usage(self, text: str) -> tuple[list[float], None]:
        return (self.get_embedding(text), None)

    async def async_get_embedding(self, text: str) -> list[float]:
        return self.get_embedding(text)

    async def async_get_embedding_and_usage(
        self, text: str
    ) -> tuple[list[float], None]:
        return self.get_embedding_and_usage(text)


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


def test_knowledge_service_keeps_compatible_profile_interface() -> None:
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


def test_runtime_builds_async_pgvector_knowledge_with_small_interface() -> None:
    captured: dict[str, Any] = {}

    class FakeAsyncPgVector:
        def __init__(self, **kwargs: Any) -> None:
            captured["vector"] = kwargs

    class FakeKnowledge:
        def __init__(self, **kwargs: Any) -> None:
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
        patch.object(knowledge_runtime_service, "AsyncPgVector", FakeAsyncPgVector),
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


@pytest.mark.asyncio
async def test_bge_async_query_embedding_runs_sync_encoder_off_event_loop() -> None:
    event_loop_thread_id = threading.get_ident()
    encoder_thread_id: int | None = None

    def fake_get_embedding(
        _self: knowledge_service.BGEKnowledgeEmbedder,
        text: str,
    ) -> list[float]:
        nonlocal encoder_thread_id
        encoder_thread_id = threading.get_ident()
        return [float(len(text))]

    embedder = knowledge_service.BGEKnowledgeEmbedder()

    with patch.object(
        knowledge_service.BGEKnowledgeEmbedder,
        "get_embedding",
        fake_get_embedding,
    ):
        result = await embedder.async_get_embedding("policy")

    assert result == [6.0]
    assert encoder_thread_id is not None
    assert encoder_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_bge_async_document_embedding_runs_sync_encoder_off_event_loop() -> None:
    event_loop_thread_id = threading.get_ident()
    encoder_thread_id: int | None = None

    def fake_get_embedding_and_usage(
        _self: knowledge_service.BGEKnowledgeEmbedder,
        text: str,
    ) -> tuple[list[float], None]:
        nonlocal encoder_thread_id
        encoder_thread_id = threading.get_ident()
        return [float(len(text))], None

    embedder = knowledge_service.BGEKnowledgeEmbedder()

    with patch.object(
        knowledge_service.BGEKnowledgeEmbedder,
        "get_embedding_and_usage",
        fake_get_embedding_and_usage,
    ):
        result = await embedder.async_get_embedding_and_usage("runbook")

    assert result == ([7.0], None)
    assert encoder_thread_id is not None
    assert encoder_thread_id != event_loop_thread_id


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


def test_owner_visibility_hides_foreign_knowledge_content() -> None:
    owned = SimpleNamespace(metadata={"user_id": "u1"})
    foreign = SimpleNamespace(metadata={"user_id": "u2"})
    legacy = SimpleNamespace(metadata={})
    assert knowledge_document_service.content_visible_to_owner(owned, "u1")
    assert not knowledge_document_service.content_visible_to_owner(foreign, "u1")
    assert not knowledge_document_service.content_visible_to_owner(legacy, "u1")
    assert knowledge_document_service.content_visible_to_owner(foreign, None)


def test_document_projection_compacts_metadata_and_formats_timestamps() -> None:
    content = SimpleNamespace(
        id="doc-1",
        name="Policy",
        created_at=0,
        metadata={
            "user_id": "u1",
            "source": "/kb/policy.md",
            "chunks": 3,
            "custom": "x" * 200,
            "ignored": None,
        },
    )
    document = knowledge_document_service.content_to_document(content)
    assert document["id"] == "doc-1"
    assert document["title"] == "Policy"
    assert document["source"] == "/kb/policy.md"
    assert document["chunks"] == 3
    assert document["created_at"] == "1970-01-01T00:00:00+00:00"
    assert document["metadata"]["user_id"] == "u1"
    assert "ignored" not in document["metadata"]
    assert len(document["metadata"]["custom"]) == 160


def test_result_projection_uses_rerank_score_and_source_metadata() -> None:
    document = SimpleNamespace(
        content="answer",
        content_id="content-1",
        name="Runbook",
        meta_data={"rerank_score": "0.87654", "source": "manual", "chunk": "2"},
    )
    result = knowledge_document_service.result_from_document(document)
    assert result["content"] == "answer"
    assert result["score"] == 0.8765
    assert result["doc_id"] == "content-1"
    assert result["title"] == "Runbook"
    assert result["source"] == "manual"
    assert result["chunk_index"] == 2


@pytest.mark.asyncio
async def test_search_documents_passes_owner_filter_to_vector_search() -> None:
    captured: dict[str, object] = {}

    class FakeKnowledge:
        async def asearch(self, *args, **kwargs):
            captured["filters"] = kwargs.get("filters")
            return []

    async def noop() -> None:
        return None

    async def hydrate_noop(_documents) -> None:
        return None

    with (
        patch.object(knowledge_service, "_ensure_knowledge_storage_async", noop),
        patch.object(
            knowledge_service, "get_async_knowledge_base", return_value=FakeKnowledge()
        ),
        patch.object(
            knowledge_service, "_hydrate_content_ids_async", hydrate_noop
        ),
    ):
        results = await knowledge_service.search_documents_async(
            "policy", owner_user_id="u1"
        )
    assert results == []
    assert captured["filters"] == {"user_id": "u1"}


@pytest.mark.asyncio
async def test_lifecycle_search_uses_one_interface_for_owner_filter() -> None:
    captured: dict[str, object] = {}

    class FakeKnowledge:
        async def asearch(self, *args, **kwargs):
            captured["query"] = args[0]
            captured["filters"] = kwargs.get("filters")
            captured["search_type"] = kwargs.get("search_type")
            return []

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: FakeKnowledge(),
            ensure_storage_async=lambda: None,
            hydrate_content_ids_async=lambda _documents: None,
        )
    )
    results = await lifecycle.search_documents_async(
        "policy", search_type="hybrid", owner_user_id="u1"
    )
    assert results == []
    assert captured["query"] == "policy"
    assert captured["filters"] == {"user_id": "u1"}
    assert captured["search_type"] == "hybrid"


@pytest.mark.asyncio
async def test_delete_document_rejects_foreign_owner() -> None:
    removed: list[str] = []

    class FakeKnowledge:
        async def aget_content_by_id(self, content_id: str):
            return SimpleNamespace(id=content_id, metadata={"user_id": "u2"})

        async def aremove_content_by_id(self, content_id: str):
            removed.append(content_id)

    async def noop() -> None:
        return None

    with (
        patch.object(knowledge_service, "_ensure_knowledge_storage_async", noop),
        patch.object(
            knowledge_service, "get_async_knowledge_base", return_value=FakeKnowledge()
        ),
    ):
        result = await knowledge_service.delete_document_async(
            "doc-1", owner_user_id="u1"
        )
    assert not result
    assert removed == []


@pytest.mark.asyncio
async def test_delete_document_uses_async_delete_dependency_for_owned_content() -> None:
    deleted: list[str] = []

    class FakeKnowledge:
        async def aget_content_by_id(self, content_id: str):
            return SimpleNamespace(id=content_id, metadata={"user_id": "u1"})

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: FakeKnowledge(),
            ensure_storage_async=lambda: None,
            delete_content_async=delete_content_async,
        )
    )

    result = await lifecycle.delete_document_async("doc-1", owner_user_id="u1")

    assert result
    assert deleted == ["doc-1"]


@pytest.mark.asyncio
async def test_clear_knowledge_base_deletes_all_visible_content_with_async_dependency() -> None:
    deleted: list[str] = []

    class FakeKnowledge:
        async def aget_content(self):
            return (
                [
                    SimpleNamespace(id="doc-1", metadata={"user_id": "u1"}),
                    SimpleNamespace(id="doc-2", metadata={"user_id": "u1"}),
                    SimpleNamespace(id="doc-3", metadata={"user_id": "u2"}),
                ],
                3,
            )

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: FakeKnowledge(),
            ensure_storage_async=lambda: None,
            delete_content_async=delete_content_async,
        )
    )

    result = await lifecycle.clear_knowledge_base_async(owner_user_id="u1")

    assert result == {"documents": 0, "chunks": 0}
    assert deleted == ["doc-1", "doc-2"]
