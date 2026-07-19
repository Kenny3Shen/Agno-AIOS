from __future__ import annotations

import asyncio
from typing import Any

import pytest

from api.services.pgvector_index_verification import (
    PgVectorCheck,
    PgVectorIndexVerificationReport,
    PgVectorVerificationError,
    _validated_explain_sql,
    verify_pgvector_indexes_async,
)


class _Mappings:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _Result:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        scalar: object | None = None,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class _Connection:
    def __init__(
        self,
        *,
        table_exists: bool = True,
        observed_dimensions: int | None = 512,
        expected_explain_plan: object | None = None,
        indexes: list[dict[str, object]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.table_exists = table_exists
        self.observed_dimensions = observed_dimensions
        self.expected_explain_plan = expected_explain_plan
        self.indexes = indexes if indexes is not None else _healthy_indexes()

    async def execute(self, statement: object, parameters: dict[str, object] | None = None) -> _Result:
        sql = str(statement)
        self.calls.append((sql, parameters or {}))
        if "pg_catalog.pg_extension" in sql:
            return _Result(rows=[{"extversion": "0.8.1", "extension_schema": "public"}])
        if "pg_catalog.pg_class AS relation" in sql:
            return _Result(
                rows=(
                    [
                        {
                            "table_oid": 42,
                            "estimated_row_count": 24_000,
                            "total_relation_bytes": 8_192_000,
                        }
                    ]
                    if self.table_exists
                    else []
                )
            )
        if "pg_catalog.pg_attribute AS attribute" in sql:
            return _Result(
                rows=[
                    {
                        "name": "id",
                        "data_type": "character varying",
                        "type_name": "varchar",
                        "not_null": True,
                    },
                    {
                        "name": "embedding",
                        "data_type": "vector(512)",
                        "type_name": "vector",
                        "not_null": False,
                    },
                    {
                        "name": "meta_data",
                        "data_type": "jsonb",
                        "type_name": "jsonb",
                        "not_null": False,
                    },
                ]
            )
        if "pg_catalog.pg_indexes AS indexes" in sql:
            return _Result(rows=self.indexes)
        if ".vector_dims" in sql:
            rows = (
                [{"dimensions": self.observed_dimensions}]
                if self.observed_dimensions is not None
                else []
            )
            return _Result(rows=rows)
        if sql.startswith("EXPLAIN "):
            return _Result(scalar=self.expected_explain_plan)
        raise AssertionError(f"Unexpected SQL: {sql}")


class _ConnectContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _ConnectContext:
        return _ConnectContext(self.connection)


def _healthy_indexes() -> list[dict[str, object]]:
    return [
        {
            "name": "knowledge_vectors_hnsw_index",
            "definition": (
                "CREATE INDEX knowledge_vectors_hnsw_index ON knowledge.vectors "
                "USING hnsw (embedding vector_cosine_ops)"
            ),
            "access_method": "hnsw",
        },
        {
            "name": "knowledge_vectors_content_gin_index",
            "definition": (
                "CREATE INDEX knowledge_vectors_content_gin_index ON knowledge.vectors "
                "USING gin (to_tsvector('english'::regconfig, content))"
            ),
            "access_method": "gin",
        },
        {
            "name": "knowledge_vectors_metadata_gin_index",
            "definition": (
                "CREATE INDEX knowledge_vectors_metadata_gin_index ON knowledge.vectors "
                "USING gin (meta_data jsonb_path_ops)"
            ),
            "access_method": "gin",
        },
    ]


def _verify(
    connection: _Connection, **kwargs: Any
) -> PgVectorIndexVerificationReport:
    return asyncio.run(
        verify_pgvector_indexes_async(
            engine=_Engine(connection),
            schema="knowledge",
            table_name="vectors",
            expected_embedding_dimensions=512,
            search_type="hybrid",
            **kwargs,
        )
    )


def _checks_by_name(report: PgVectorIndexVerificationReport) -> dict[str, PgVectorCheck]:
    return {check.name: check for check in report.checks}


def test_verifier_reports_actual_schema_dimensions_and_index_definitions() -> None:
    connection = _Connection()

    report = _verify(connection)

    assert report.schema == "knowledge"
    assert report.table == "vectors"
    assert report.qualified_table == '"knowledge"."vectors"'
    assert report.vector_extension_version == "0.8.1"
    assert report.vector_extension_schema == "public"
    assert report.estimated_row_count == 24_000
    assert report.embedding_column == "embedding"
    assert report.declared_embedding_dimensions == 512
    assert report.observed_embedding_dimensions == 512
    assert len(report.indexes) == 3
    assert _checks_by_name(report)["vector_index"].status == "ok"
    assert _checks_by_name(report)["full_text_gin_index"].status == "ok"
    assert _checks_by_name(report)["metadata_gin_index"].status == "ok"
    assert _checks_by_name(report)["explain_plan"].status == "not_requested"
    assert not any(sql.startswith("EXPLAIN ") for sql, _params in connection.calls)
    assert report.columns[1].declared_dimensions == 512
    assert report.as_dict()["qualified_table"] == '"knowledge"."vectors"'


def test_verifier_marks_missing_indexes_as_evidence_gated_recommendations() -> None:
    connection = _Connection(indexes=[])

    report = _verify(connection)

    checks = _checks_by_name(report)
    assert checks["vector_index"].status == "warning"
    assert checks["full_text_gin_index"].status == "warning"
    assert checks["metadata_gin_index"].status == "info"
    joined_recommendations = " ".join(report.recommendations)
    assert "Alembic" in joined_recommendations
    assert "EXPLAIN" in joined_recommendations
    assert "never creates" in joined_recommendations


def test_verifier_detects_embedding_dimension_mismatch() -> None:
    connection = _Connection(observed_dimensions=384)

    report = _verify(connection)

    check = _checks_by_name(report)["embedding_dimensions"]
    assert check.status == "error"
    assert "512" in check.message and "384" in check.message


def test_verifier_warns_for_an_incompatible_vector_operator_class() -> None:
    indexes = _healthy_indexes()
    indexes[0]["definition"] = (
        "CREATE INDEX knowledge_vectors_hnsw_index ON knowledge.vectors "
        "USING hnsw (embedding vector_l2_ops)"
    )
    connection = _Connection(indexes=indexes)

    report = _verify(connection)

    assert _checks_by_name(report)["vector_index"].status == "warning"


def test_verifier_only_captures_explain_when_explicitly_requested() -> None:
    expected_plan = [{"Plan": {"Node Type": "Index Scan"}}]
    connection = _Connection(expected_explain_plan=expected_plan)

    report = _verify(connection, explain_sql="SELECT id FROM knowledge.vectors LIMIT 5")

    assert report.explain_sql == "SELECT id FROM knowledge.vectors LIMIT 5"
    assert report.explain_plan == expected_plan
    explain_calls = [sql for sql, _params in connection.calls if sql.startswith("EXPLAIN ")]
    assert len(explain_calls) == 1
    assert "ANALYZE" not in explain_calls[0]
    assert _checks_by_name(report)["explain_plan"].status == "info"


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM knowledge.vectors",
        "SELECT 1; DELETE FROM knowledge.vectors",
        "WITH x AS (DELETE FROM knowledge.vectors RETURNING id) SELECT * FROM x",
        "SELECT 1 -- hidden change",
        "SELECT * INTO copied_vectors FROM knowledge.vectors",
    ],
)
def test_explain_input_rejects_non_read_only_or_multi_statement_sql(statement: str) -> None:
    with pytest.raises(PgVectorVerificationError):
        _validated_explain_sql(statement)


def test_catalog_queries_bind_untrusted_schema_and_table_names() -> None:
    connection = _Connection(table_exists=False)
    schema = 'knowledge"; DROP TABLE app.users; --'
    table_name = "vectors; DROP TABLE app.users"

    report = asyncio.run(
        verify_pgvector_indexes_async(
            engine=_Engine(connection),
            schema=schema,
            table_name=table_name,
            expected_embedding_dimensions=512,
            search_type="vector",
        )
    )

    assert report.table_exists is False
    table_sql, table_parameters = next(
        (sql, parameters)
        for sql, parameters in connection.calls
        if "pg_catalog.pg_class AS relation" in sql
    )
    assert "DROP TABLE app.users" not in table_sql
    assert table_parameters == {"schema": schema, "table": table_name}
    assert _checks_by_name(report)["explain_plan"].status == "not_requested"
