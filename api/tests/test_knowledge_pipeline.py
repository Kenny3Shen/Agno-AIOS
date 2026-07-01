from __future__ import annotations

import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
