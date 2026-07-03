import inspect
import unittest

from api.services import audit_service, llm_service, postgres_store


class PostgresSqlTemplateTest(unittest.TestCase):
    def test_jsonb_defaults_escape_psycopg_format_braces(self) -> None:
        for function in (postgres_store.ensure_app_tables, audit_service.ensure_audit_log_table):
            with self.subTest(function=function.__name__):
                source = inspect.getsource(function)

                self.assertNotIn("DEFAULT '{}'::jsonb", source)
                self.assertIn("DEFAULT '{{}}'::jsonb", source)

    def test_session_owner_filter_casts_nullable_user_id_to_text(self) -> None:
        source = inspect.getsource(llm_service.get_all_sessions)

        self.assertIn("%s::text IS NULL OR s.user_id = %s::text", source)


if __name__ == "__main__":
    unittest.main()
