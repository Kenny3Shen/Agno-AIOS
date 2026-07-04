import inspect
from typing import Any, cast
from api.persistence.audit_logs import audit_logs_table
from api.persistence.mcp import (
    _token_insert_values,
    mcp_tokens_table,
)
from api.mcp import config as mcp_config
from api.services import llm_service, postgres_store


def test_app_table_bootstrap_no_longer_creates_audit_logs_with_raw_sql() -> None:
    source = inspect.getsource(postgres_store.ensure_app_tables)
    assert "idx_audit_logs" not in source
    assert "actor_user_id TEXT NOT NULL" not in source


def test_audit_log_metadata_uses_jsonb_default_in_sqlalchemy_table() -> None:
    metadata_column = audit_logs_table().c.metadata
    server_default = metadata_column.server_default
    assert server_default is not None
    default_arg = cast(Any, server_default).arg
    assert metadata_column.type.__class__.__name__ == "JSONB"
    assert str(default_arg) == "'{}'::jsonb"


def test_session_listing_no_longer_joins_archive_table() -> None:
    source = inspect.getsource(llm_service.get_all_sessions)
    assert "get_sessions" in source
    assert "chat_session_archives" not in source


def test_mcp_config_no_longer_uses_raw_sql_for_runtime_tables() -> None:
    source = inspect.getsource(mcp_config)
    assert "postgres_connect" not in source
    assert "sql.SQL" not in source
    assert "async def list_tokens" in source
    assert "await list_token_rows" in source


def test_mcp_tables_are_declared_in_sqlalchemy_persistence() -> None:
    token_table = mcp_tokens_table()
    assert token_table.c.id.identity.__class__.__name__ == "Identity"
    assert token_table.c.token.unique


def test_mcp_token_insert_omits_identity_id_when_absent() -> None:
    values = _token_insert_values(
        {
            "id": None,
            "name": "Agno AIOS Agent",
            "token": "token",
            "created_at": 1,
            "expires_at": 0,
        }
    )

    assert "id" not in values
    assert values["name"] == "Agno AIOS Agent"
