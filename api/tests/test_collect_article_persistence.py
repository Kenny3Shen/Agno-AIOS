from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
async def test_collect_articles_schema_ensure_only_checks_applied_migration() -> None:
    schema_check = AsyncMock()
    with patch.object(
        collect_articles,
        "ensure_control_plane_schema_current",
        schema_check,
    ):
        await collect_articles._create_collect_articles_table()

    schema_check.assert_awaited_once_with()
