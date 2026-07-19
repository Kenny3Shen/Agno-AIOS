from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

from api.persistence import collect_articles


def test_collect_article_table_persists_cve_ids_as_text_array() -> None:
    table = collect_articles.collect_articles_table()

    assert "cve_ids" in table.c
    assert str(table.c.cve_ids.type) == "ARRAY"
    assert collect_articles._normalize_cve_ids(
        ["cve-2024-1234", "CVE-2024-1234", "", "CVE-2021-44228"]
    ) == ["CVE-2024-1234", "CVE-2021-44228"]


def test_error_upsert_keeps_an_existing_successful_payload() -> None:
    table = collect_articles.collect_articles_table()
    stmt = insert(table).values(
        url="https://example.test/article",
        status="error",
        markdown="",
        cve_ids=[],
    )
    update_values = collect_articles._collect_article_conflict_update_values(
        table,
        stmt.excluded,
    )

    for column in ("markdown", "cve_ids", "status", "fetched_at"):
        rendered = str(
            update_values[column].compile(dialect=postgresql.dialect())
        )
        assert "CASE WHEN" in rendered
        assert f"collect_articles.{column}" in rendered
        assert f"excluded.{column}" in rendered


@pytest.mark.asyncio
async def test_collect_articles_schema_migration_adds_cve_ids_column() -> None:
    class Connection:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, statement: object) -> None:
            self.statements.append(statement)

        async def run_sync(self, *_args: object, **_kwargs: object) -> None:
            return None

    class Engine:
        def __init__(self, connection: Connection) -> None:
            self.connection = connection

        def begin(self) -> Connection:
            return self.connection

    connection = Connection()
    with patch.object(
        collect_articles,
        "get_async_control_plane_engine",
        return_value=Engine(connection),
    ):
        await collect_articles._create_collect_articles_table()

    ddl = "\n".join(str(statement) for statement in connection.statements)
    assert "ADD COLUMN IF NOT EXISTS cve_ids TEXT[]" in ddl
