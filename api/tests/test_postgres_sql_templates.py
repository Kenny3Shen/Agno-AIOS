import inspect
import unittest
from typing import Any, cast

from api.persistence.audit_logs import audit_logs_table
from api.services import llm_service, postgres_store


class PostgresSqlTemplateTest(unittest.TestCase):
    def test_app_table_bootstrap_no_longer_creates_audit_logs_with_raw_sql(self) -> None:
        source = inspect.getsource(postgres_store.ensure_app_tables)

        self.assertNotIn("idx_audit_logs", source)
        self.assertNotIn("actor_user_id TEXT NOT NULL", source)

    def test_audit_log_metadata_uses_jsonb_default_in_sqlalchemy_table(self) -> None:
        metadata_column = audit_logs_table().c.metadata
        server_default = metadata_column.server_default
        assert server_default is not None
        default_arg = cast(Any, server_default).arg

        self.assertEqual(metadata_column.type.__class__.__name__, "JSONB")
        self.assertEqual(str(default_arg), "'{}'::jsonb")

    def test_session_listing_no_longer_joins_archive_table(self) -> None:
        source = inspect.getsource(llm_service.get_all_sessions)

        self.assertIn("get_sessions", source)
        self.assertNotIn("chat_session_archives", source)


if __name__ == "__main__":
    unittest.main()
