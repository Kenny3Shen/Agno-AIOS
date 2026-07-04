from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

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
        return self.get_embedding(text), None

    async def async_get_embedding(self, text: str) -> list[float]:
        return self.get_embedding(text)

    async def async_get_embedding_and_usage(self, text: str) -> tuple[list[float], None]:
        return self.get_embedding_and_usage(text)


class KnowledgePipelineContractTest(unittest.TestCase):
    def test_suffix_profile_chooses_agno_aligned_chunkers(self) -> None:
        cases = {
            "runbook.md": ("markdown", "MarkdownReader"),
            "events.csv": ("csv_row", "CSVReader"),
            "finding.json": ("json", "JSONReader"),
            "agent.py": ("code", "TextReader"),
            "incident.txt": ("semantic", "TextReader"),
        }

        for filename, (expected_strategy, expected_reader) in cases.items():
            with self.subTest(filename=filename):
                profile = knowledge_ingest_service.profile_for_filename(filename)
                self.assertEqual(profile.strategy, expected_strategy)

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
                self.assertEqual(reader.__class__.__name__, expected_reader)

    def test_knowledge_service_keeps_compatible_profile_interface(self) -> None:
        profile = knowledge_service.knowledge_profile_for_filename("runbook.md")

        self.assertEqual(profile.strategy, "markdown")
        self.assertEqual(knowledge_service.reader_for_profile(profile).__class__.__name__, "MarkdownReader")

    def test_runtime_candidate_limit_respects_rerank_policy(self) -> None:
        self.assertEqual(
            knowledge_runtime_service.retrieval_candidate_limit(
                5,
                rerank_enabled=True,
                rerank_candidate_multiplier=3,
                rerank_min_candidates=10,
            ),
            15,
        )
        self.assertEqual(
            knowledge_runtime_service.retrieval_candidate_limit(
                5,
                rerank_enabled=True,
                rerank_candidate_multiplier=1,
                rerank_min_candidates=10,
            ),
            10,
        )
        self.assertEqual(
            knowledge_runtime_service.retrieval_candidate_limit(
                5,
                rerank_enabled=False,
                rerank_candidate_multiplier=3,
                rerank_min_candidates=10,
            ),
            5,
        )

    def test_runtime_builds_pgvector_knowledge_with_small_interface(self) -> None:
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
                    embedder=FakeEmbedder(),
                    reranker=None,
                    contents_db=contents_db,
                ),
                search_type=SearchType.hybrid,
                readers=readers,
            )

        self.assertIsInstance(result, FakeKnowledge)
        self.assertEqual(captured["vector"]["table_name"], "vectors")
        self.assertEqual(captured["vector"]["schema"], "knowledge")
        self.assertEqual(captured["vector"]["search_type"], SearchType.hybrid)
        self.assertEqual(captured["vector"]["prefix_match"], True)
        self.assertEqual(captured["knowledge"]["name"], "security")
        self.assertEqual(captured["knowledge"]["contents_db"], contents_db)
        self.assertEqual(captured["knowledge"]["max_results"], 15)
        self.assertEqual(captured["knowledge"]["readers"], readers)

    def test_status_exposes_supported_suffixes_and_search_type(self) -> None:
        original = os.environ.get("AGNO_KNOWLEDGE_SEARCH_TYPE")
        os.environ["AGNO_KNOWLEDGE_SEARCH_TYPE"] = "hybrid"
        try:
            self.assertEqual(
                knowledge_service.search_type_from_env(),
                SearchType.hybrid,
            )
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
        self.assertIn(".md", status["supported_suffixes"])
        self.assertIn(".csv", status["supported_suffixes"])
        self.assertIn(".py", status["supported_suffixes"])
        self.assertIn(status["search_type"], {"vector", "keyword", "hybrid"})

        service_status = knowledge_service.pipeline_status()
        self.assertEqual(service_status["search_type"], "hybrid")
        self.assertEqual(service_status["code_chunk_size"], knowledge_service.CODE_CHUNK_SIZE)

    def test_owner_visibility_hides_foreign_knowledge_content(self) -> None:
        owned = SimpleNamespace(metadata={"user_id": "u1"})
        foreign = SimpleNamespace(metadata={"user_id": "u2"})
        legacy = SimpleNamespace(metadata={})

        self.assertTrue(knowledge_document_service.content_visible_to_owner(owned, "u1"))
        self.assertFalse(knowledge_document_service.content_visible_to_owner(foreign, "u1"))
        self.assertFalse(knowledge_document_service.content_visible_to_owner(legacy, "u1"))
        self.assertTrue(knowledge_document_service.content_visible_to_owner(foreign, None))

    def test_document_projection_compacts_metadata_and_formats_timestamps(self) -> None:
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

        self.assertEqual(document["id"], "doc-1")
        self.assertEqual(document["title"], "Policy")
        self.assertEqual(document["source"], "/kb/policy.md")
        self.assertEqual(document["chunks"], 3)
        self.assertEqual(document["created_at"], "1970-01-01T00:00:00+00:00")
        self.assertEqual(document["metadata"]["user_id"], "u1")
        self.assertNotIn("ignored", document["metadata"])
        self.assertEqual(len(document["metadata"]["custom"]), 160)

    def test_result_projection_uses_rerank_score_and_source_metadata(self) -> None:
        document = SimpleNamespace(
            content="answer",
            content_id="content-1",
            name="Runbook",
            meta_data={
                "rerank_score": "0.87654",
                "source": "manual",
                "chunk": "2",
            },
        )

        result = knowledge_document_service.result_from_document(document)

        self.assertEqual(result["content"], "answer")
        self.assertEqual(result["score"], 0.8765)
        self.assertEqual(result["doc_id"], "content-1")
        self.assertEqual(result["title"], "Runbook")
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["chunk_index"], 2)

    def test_search_documents_passes_owner_filter_to_vector_search(self) -> None:
        captured: dict[str, object] = {}

        class FakeKnowledge:
            def search(self, *args, **kwargs):
                captured["filters"] = kwargs.get("filters")
                return []

        with (
            patch.object(knowledge_service, "_ensure_knowledge_storage", lambda: None),
            patch.object(knowledge_service, "get_knowledge_base", return_value=FakeKnowledge()),
            patch.object(knowledge_service, "_hydrate_content_ids", lambda documents: None),
        ):
            results = knowledge_service.search_documents("policy", owner_user_id="u1")

        self.assertEqual(results, [])
        self.assertEqual(captured["filters"], {"user_id": "u1"})

    def test_lifecycle_search_uses_one_interface_for_owner_filter(self) -> None:
        captured: dict[str, object] = {}

        class FakeKnowledge:
            def search(self, *args, **kwargs):
                captured["query"] = args[0]
                captured["filters"] = kwargs.get("filters")
                captured["search_type"] = kwargs.get("search_type")
                return []

        lifecycle = knowledge_service.KnowledgeBaseLifecycle(
            knowledge_service.KnowledgeBaseLifecycleDependencies(
                get_knowledge_base=lambda _search_type=None: FakeKnowledge(),
                ensure_storage=lambda: None,
                hydrate_content_ids=lambda _documents: None,
            )
        )

        results = lifecycle.search_documents(
            "policy",
            search_type="hybrid",
            owner_user_id="u1",
        )

        self.assertEqual(results, [])
        self.assertEqual(captured["query"], "policy")
        self.assertEqual(captured["filters"], {"user_id": "u1"})
        self.assertEqual(captured["search_type"], "hybrid")

    def test_delete_document_rejects_foreign_owner(self) -> None:
        removed: list[str] = []

        class FakeKnowledge:
            def get_content_by_id(self, content_id: str):
                return SimpleNamespace(id=content_id, metadata={"user_id": "u2"})

            def remove_content_by_id(self, content_id: str):
                removed.append(content_id)

        with (
            patch.object(knowledge_service, "_ensure_knowledge_storage", lambda: None),
            patch.object(knowledge_service, "get_knowledge_base", return_value=FakeKnowledge()),
        ):
            result = knowledge_service.delete_document("doc-1", owner_user_id="u1")

        self.assertFalse(result)
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
