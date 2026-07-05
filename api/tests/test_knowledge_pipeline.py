from __future__ import annotations
import os
from types import SimpleNamespace
from typing import Any, Callable, get_type_hints
from unittest.mock import patch

import pytest
from agno.knowledge.embedder import Embedder
from agno.knowledge.embedder.sentence_transformer import SentenceTransformerEmbedder
from agno.knowledge.reranker.sentence_transformer import SentenceTransformerReranker
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


class StrictAsyncKnowledge:
    def __init__(
        self,
        *,
        contents: list[Any] | None = None,
        content_by_id: dict[str, Any] | None = None,
        search_results: list[Any] | None = None,
        search_callback: Callable[..., Any] | None = None,
    ) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._contents = contents or []
        self._content_by_id = content_by_id or {}
        self._search_results = search_results or []
        self._search_callback = search_callback

    def insert(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync insert must not be called")

    def search(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync search must not be called")

    def load(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync load must not be called")

    def get_content(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync get_content must not be called")

    def get_content_by_id(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync get_content_by_id must not be called")

    def remove_content_by_id(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync remove_content_by_id must not be called")

    def remove_all_content(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync remove_all_content must not be called")

    async def ainsert(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("ainsert", args, kwargs))

    async def aget_content(self, *args: Any, **kwargs: Any):
        self.calls.append(("aget_content", args, kwargs))
        return self._contents, len(self._contents)

    async def aget_content_by_id(self, content_id: str):
        self.calls.append(("aget_content_by_id", content_id))
        return self._content_by_id.get(content_id)

    async def asearch(self, *args: Any, **kwargs: Any):
        self.calls.append(("asearch", args, kwargs))
        if self._search_callback is not None:
            result = self._search_callback(*args, **kwargs)
            if hasattr(result, "__await__"):
                return await result
            return result
        return self._search_results


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


def test_runtime_builds_agno_pgvector_knowledge_with_small_interface() -> None:
    captured: dict[str, Any] = {}

    class FakePgVector:
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
    captured: dict[str, Any] = {}

    class FakeSentenceTransformerEmbedder:
        def __init__(self, **kwargs: Any) -> None:
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
    captured: dict[str, Any] = {}

    class FakeSentenceTransformerReranker:
        def __init__(self, **kwargs: Any) -> None:
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

    async def noop() -> None:
        return None

    async def hydrate_noop(_documents) -> None:
        return None

    async def search(*args, **kwargs):
        captured["filters"] = kwargs.get("filters")
        captured["max_results"] = kwargs.get("max_results")
        captured["search_type"] = kwargs.get("search_type")
        return []

    knowledge = StrictAsyncKnowledge(search_callback=search)

    with (
        patch.object(knowledge_service, "_ensure_knowledge_storage_async", noop),
        patch.object(knowledge_service, "get_async_knowledge_base", return_value=knowledge),
        patch.object(knowledge_service, "_hydrate_content_ids_async", hydrate_noop),
    ):
        results = await knowledge_service.search_documents_async(
            "policy", owner_user_id="u1"
        )
    assert results == []
    assert captured["filters"] == {"user_id": "u1"}
    assert knowledge.calls == [
        (
            "asearch",
            ("policy",),
            {
                "filters": {"user_id": "u1"},
                "max_results": captured["max_results"],
                "search_type": captured["search_type"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_lifecycle_search_uses_one_interface_for_owner_filter() -> None:
    captured: dict[str, object] = {}

    async def search(*args, **kwargs):
        captured["query"] = args[0]
        captured["filters"] = kwargs.get("filters")
        captured["max_results"] = kwargs.get("max_results")
        captured["search_type"] = kwargs.get("search_type")
        return []

    knowledge = StrictAsyncKnowledge(search_callback=search)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
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
    assert knowledge.calls == [
        (
            "asearch",
            ("policy",),
            {
                "filters": {"user_id": "u1"},
                "max_results": captured["max_results"],
                "search_type": "hybrid",
            },
        )
    ]


@pytest.mark.asyncio
async def test_add_text_document_uses_async_insert_and_reload() -> None:
    content_row = SimpleNamespace(
        id="content-1",
        name="Runbook",
        metadata={"user_id": "u1", "source": "manual", "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[content_row])

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
        )
    )

    with patch.object(knowledge_service, "reader_for_profile", return_value=object()):
        result = await lifecycle.add_text_document_async(
            "Runbook",
            "  content  ",
            owner_user_id="u1",
        )

    assert result["id"] == "content-1"
    assert result["title"] == "Runbook"
    assert knowledge.calls[0][0] == "ainsert"
    assert knowledge.calls[1][0] == "aget_content"


@pytest.mark.asyncio
async def test_add_file_document_uses_async_insert_and_reload(tmp_path) -> None:
    file_path = tmp_path / "runbook.md"
    file_path.write_text("# runbook\n", encoding="utf-8")
    content_row = SimpleNamespace(
        id="content-2",
        name="Runbook",
        metadata={"user_id": "u1", "source": str(file_path), "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[content_row])

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
        )
    )

    with patch.object(knowledge_service, "reader_for_profile", return_value=object()):
        result = await lifecycle.add_file_document_async(
            str(file_path),
            title="Runbook",
            owner_user_id="u1",
        )

    assert result["id"] == "content-2"
    assert result["title"] == "Runbook"
    assert knowledge.calls[0][0] == "ainsert"
    assert knowledge.calls[1][0] == "aget_content"


@pytest.mark.asyncio
async def test_list_documents_uses_contents_db_without_runtime() -> None:
    content_row = SimpleNamespace(
        id="content-3",
        name="Runbook",
        metadata={"user_id": "u1", "source": "/kb/runbook.md", "chunks": 1},
        created_at=0,
    )
    content_calls: list[dict[str, Any]] = []

    async def content_rows_async(**kwargs: Any):
        content_calls.append(kwargs)
        return [content_row], 1

    def fail_runtime(_search_type=None):
        raise AssertionError("status/list must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            chunk_counts_by_content_id_async=lambda _owner_user_id=None: {
                "content-3": 4
            },
        )
    )

    documents = await lifecycle.list_documents_async(owner_user_id="u1")

    assert documents == [
        {
            "id": "content-3",
            "title": "Runbook",
            "source": "/kb/runbook.md",
            "chunks": 4,
            "created_at": "1970-01-01T00:00:00+00:00",
            "metadata": {
                "user_id": "u1",
                "source": "/kb/runbook.md",
                "chunks": "1",
            },
        }
    ]
    assert content_calls == [
        {"limit": 500, "page": 1, "sort_by": "updated_at", "sort_order": "desc"}
    ]


@pytest.mark.asyncio
async def test_knowledge_status_uses_prefetched_documents_without_runtime() -> None:
    def fail_runtime(_search_type=None):
        raise AssertionError("status must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            chunk_count_async=lambda _owner_user_id=None: 7,
        )
    )

    status = await lifecycle.knowledge_status_async(
        owner_user_id="u1",
        documents=[{"id": "content-1"}],
    )

    assert status["documents"] == 1
    assert status["chunks"] == 7
    assert "runtime_loaded" in status


@pytest.mark.asyncio
async def test_delete_document_rejects_foreign_owner() -> None:
    lookups: list[str] = []

    async def noop() -> None:
        return None

    async def content_by_id(content_id: str):
        lookups.append(content_id)
        return SimpleNamespace(id="doc-1", metadata={"user_id": "u2"})

    def fail_runtime(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("delete authorization must not load Knowledge runtime")

    with (
        patch.object(knowledge_service, "_ensure_knowledge_contents_storage_async", noop),
        patch.object(knowledge_service, "_knowledge_content_by_id_async", content_by_id),
        patch.object(knowledge_service, "get_async_knowledge_base", fail_runtime),
    ):
        result = await knowledge_service.delete_document_async(
            "doc-1", owner_user_id="u1"
        )
    assert not result
    assert lookups == ["doc-1"]


@pytest.mark.asyncio
async def test_delete_document_uses_async_delete_dependency_for_owned_content() -> None:
    deleted: list[str] = []

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)

    async def content_by_id(content_id: str):
        assert content_id == "doc-1"
        return SimpleNamespace(id="doc-1", metadata={"user_id": "u1"})

    def fail_runtime(_search_type=None):
        raise AssertionError("delete must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
        )
    )

    result = await lifecycle.delete_document_async("doc-1", owner_user_id="u1")

    assert result
    assert deleted == ["doc-1"]


@pytest.mark.asyncio
async def test_clear_knowledge_base_deletes_all_visible_content_with_async_dependency() -> None:
    deleted: list[str] = []
    contents = [
        SimpleNamespace(id="doc-1", metadata={"user_id": "u1"}),
        SimpleNamespace(id="doc-2", metadata={"user_id": "u1"}),
        SimpleNamespace(id="doc-3", metadata={"user_id": "u2"}),
    ]

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)

    async def content_rows_async(**_kwargs: Any):
        return contents, len(contents)

    def fail_runtime(_search_type=None):
        raise AssertionError("clear must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            delete_content_async=delete_content_async,
        )
    )

    result = await lifecycle.clear_knowledge_base_async(owner_user_id="u1")

    assert result == {"documents": 0, "chunks": 0}
    assert deleted == ["doc-1", "doc-2"]
