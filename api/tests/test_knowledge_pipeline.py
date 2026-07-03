from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agno.vectordb.search import SearchType

from api.services import knowledge_service


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
                profile = knowledge_service.knowledge_profile_for_filename(filename)
                self.assertEqual(profile.strategy, expected_strategy)

                reader = knowledge_service.reader_for_profile(profile)
                self.assertEqual(reader.__class__.__name__, expected_reader)

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

        status = knowledge_service.pipeline_status()
        self.assertIn(".md", status["supported_suffixes"])
        self.assertIn(".csv", status["supported_suffixes"])
        self.assertIn(".py", status["supported_suffixes"])
        self.assertIn(status["search_type"], {"vector", "keyword", "hybrid"})

    def test_owner_visibility_hides_foreign_knowledge_content(self) -> None:
        owned = SimpleNamespace(metadata={"user_id": "u1"})
        foreign = SimpleNamespace(metadata={"user_id": "u2"})
        legacy = SimpleNamespace(metadata={})

        self.assertTrue(knowledge_service._content_visible_to_owner(owned, "u1"))
        self.assertFalse(knowledge_service._content_visible_to_owner(foreign, "u1"))
        self.assertFalse(knowledge_service._content_visible_to_owner(legacy, "u1"))
        self.assertTrue(knowledge_service._content_visible_to_owner(foreign, None))

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
