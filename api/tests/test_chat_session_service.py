import unittest
from unittest.mock import patch

from api.services import chat_session_service


class FakeCursor:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.params = params

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


class ChatSessionServiceTest(unittest.TestCase):
    def test_get_all_sessions_projects_sorted_archived_session_rows(self):
        rows = [
            {
                "session_id": "older",
                "created_at": 1,
                "updated_at": 2,
                "user_id": "u1",
                "runs": [{"input": {"input_content": "older preview"}}],
                "metadata": {},
                "archived_at": None,
            },
            {
                "session_id": "newer",
                "created_at": 3,
                "updated_at": 4,
                "user_id": "u1",
                "runs": [{"input": "newer preview"}],
                "metadata": {"agno_aios_archived": True},
                "archived_at": None,
            },
        ]
        cursor = FakeCursor(rows)

        with (
            patch.object(chat_session_service, "ensure_agno_postgres_tables"),
            patch.object(chat_session_service, "ensure_chat_session_archive_table"),
            patch.object(
                chat_session_service,
                "postgres_connect",
                return_value=FakeConnection(cursor),
            ),
        ):
            sessions = chat_session_service.get_all_sessions(
                include_archived=True,
                owner_user_id="u1",
                include_runs=True,
            )

        self.assertEqual(cursor.params, (True, "u1", "u1"))
        self.assertEqual([session["session_id"] for session in sessions], ["newer", "older"])
        self.assertEqual(sessions[0]["preview"], "newer preview")
        self.assertTrue(sessions[0]["archived"])
        self.assertEqual(sessions[0]["runs"], [{"input": "newer preview"}])
        self.assertFalse(sessions[1]["archived"])
        self.assertEqual(sessions[1]["preview"], "older preview")


if __name__ == "__main__":
    unittest.main()
