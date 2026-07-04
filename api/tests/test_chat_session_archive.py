import inspect
import unittest

from api.routes import chat
from api.services import llm_service


class ChatSessionArchiveContractTest(unittest.TestCase):
    def test_chat_route_uses_archive_service_for_delete_endpoint(self):
        source = inspect.getsource(chat.remove_session)

        self.assertIn("archive_session", source)
        self.assertNotIn("delete_session(", source)

    def test_session_service_exposes_archive_without_hiding_trace_data(self):
        self.assertTrue(hasattr(llm_service, "archive_session"))
        self.assertTrue(hasattr(llm_service, "is_session_archived"))
        self.assertFalse(hasattr(llm_service, "ensure_chat_session_archive_table"))

        signature = inspect.signature(llm_service.get_all_sessions)
        self.assertIn("include_archived", signature.parameters)

        archive_source = inspect.getsource(llm_service.archive_session)
        self.assertNotIn("delete_session", archive_source)
        self.assertIn("upsert_session", archive_source)
        self.assertNotIn("chat_session_archives", archive_source)


if __name__ == "__main__":
    unittest.main()
