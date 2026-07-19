"""Read-only PgVector schema and index verification.

The knowledge runtime delegates table creation to Agno's ``PgVector`` class.
This module deliberately does *not* call ``optimize()`` or issue DDL: the
right HNSW/IVFFlat parameters depend on the corpus, query distribution,
recall target, and observed query plans.  It instead collects the facts an
operator needs before encoding an approved index change in a migration.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from api.persistence.database import get_async_control_plane_engine
from api.services.knowledge_rag_settings_service import knowledge_settings, search_type_from_name

CheckStatus = Literal["ok", "warning", "error", "info", "not_requested"]

_DIMENSION_PATTERN = re.compile(r"^(?:vector|halfvec)\s*\(\s*(\d+)\s*\)$", re.IGNORECASE)
_INDEX_METHOD_PATTERN = re.compile(r"\bUSING\s+([a-z_][a-z0-9_]*)\b", re.IGNORECASE)
_VECTOR_OPERATOR_CLASS_PATTERN = re.compile(
    r"\b(?:vector|halfvec|sparsevec)_(?:l2|ip|cosine)_ops\b", re.IGNORECASE
)
_DANGEROUS_EXPLAIN_TOKENS = re.compile(
    r"\b(?:"
    r"ALTER|ANALYZE|CALL|COMMENT|COPY|CREATE|DEALLOCATE|DELETE|DISCARD|DO|"
    r"DROP|EXECUTE|GRANT|INSERT|LISTEN|LOCK|MERGE|NOTIFY|PREPARE|REASSIGN|"
    r"REFRESH|REINDEX|RESET|REVOKE|SECURITY|SET|TRUNCATE|UNLISTEN|UPDATE|"
    r"VACUUM"
    r")\b",
    re.IGNORECASE,
)


class PgVectorVerificationError(ValueError):
    """Raised when optional diagnostic input would not be read-only."""


@dataclass(frozen=True, slots=True)
class PgVectorColumnReport:
    name: str
    data_type: str
    type_name: str
    nullable: bool
    declared_dimensions: int | None


@dataclass(frozen=True, slots=True)
class PgVectorIndexReport:
    name: str
    definition: str
    access_method: str | None
    vector_operator_class: str | None
    is_vector_index: bool
    is_full_text_gin_index: bool
    is_metadata_gin_index: bool


@dataclass(frozen=True, slots=True)
class PgVectorCheck:
    name: str
    status: CheckStatus
    message: str


@dataclass(frozen=True, slots=True)
class PgVectorIndexVerificationReport:
    """A JSON-serializable, read-only view of the configured PgVector table."""

    schema: str
    table: str
    qualified_table: str
    configured_search_type: str
    expected_embedding_dimensions: int
    vector_extension_installed: bool
    vector_extension_version: str | None
    vector_extension_schema: str | None
    table_exists: bool
    table_oid: int | None
    estimated_row_count: int | None
    total_relation_bytes: int | None
    columns: tuple[PgVectorColumnReport, ...]
    embedding_column: str | None
    declared_embedding_dimensions: int | None
    observed_embedding_dimensions: int | None
    indexes: tuple[PgVectorIndexReport, ...]
    checks: tuple[PgVectorCheck, ...]
    recommendations: tuple[str, ...]
    explain_sql: str | None
    explain_plan: object | None

    def as_dict(self) -> dict[str, object]:
        """Return stable built-in containers suitable for JSON output."""
        return asdict(self)


_EXTENSION_QUERY = """
SELECT extension.extversion, namespace.nspname AS extension_schema
FROM pg_catalog.pg_extension AS extension
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = extension.extnamespace
WHERE extension.extname = 'vector'
"""

_TABLE_QUERY = """
SELECT
    relation.oid::bigint AS table_oid,
    relation.reltuples::bigint AS estimated_row_count,
    pg_total_relation_size(relation.oid)::bigint AS total_relation_bytes
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = :schema
  AND relation.relname = :table
  AND relation.relkind IN ('r', 'p')
"""

_COLUMNS_QUERY = """
SELECT
    attribute.attname AS name,
    format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
    type.typname AS type_name,
    attribute.attnotnull AS not_null
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_type AS type ON type.oid = attribute.atttypid
WHERE attribute.attrelid = :table_oid
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped
ORDER BY attribute.attnum
"""

# ``pg_indexes`` intentionally remains the source of the rendered index
# definition.  The definition contains the operator class/expression we need
# to audit, while the catalog joins expose the access method without parsing
# every PostgreSQL spelling variation.
_INDEXES_QUERY = """
SELECT
    indexes.indexname AS name,
    indexes.indexdef AS definition,
    access_method.amname AS access_method
FROM pg_catalog.pg_indexes AS indexes
JOIN pg_catalog.pg_namespace AS table_namespace
  ON table_namespace.nspname = indexes.schemaname
JOIN pg_catalog.pg_class AS table_relation
  ON table_relation.relname = indexes.tablename
 AND table_relation.relnamespace = table_namespace.oid
JOIN pg_catalog.pg_index AS index_relation_info
  ON index_relation_info.indrelid = table_relation.oid
JOIN pg_catalog.pg_class AS index_relation
  ON index_relation.oid = index_relation_info.indexrelid
 AND index_relation.relname = indexes.indexname
 AND index_relation.relnamespace = table_namespace.oid
JOIN pg_catalog.pg_am AS access_method
  ON access_method.oid = index_relation.relam
WHERE indexes.schemaname = :schema
  AND indexes.tablename = :table
ORDER BY indexes.indexname
"""


def _quote_identifier(identifier: str) -> str:
    """Quote one PostgreSQL identifier without interpreting dots or quotes."""
    if not identifier or "\x00" in identifier:
        raise PgVectorVerificationError("PostgreSQL schema and table names must be non-empty identifiers")
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _qualified_identifier(schema: str, table_name: str) -> str:
    return f"{_quote_identifier(schema)}.{_quote_identifier(table_name)}"


def _declared_dimensions(data_type: str) -> int | None:
    match = _DIMENSION_PATTERN.match(data_type.strip())
    return int(match.group(1)) if match else None


def _optional_integer(value: object | None, *, field: str) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except ValueError as exc:
        raise PgVectorVerificationError(f"PostgreSQL returned a non-integer {field}: {value!r}") from exc


def _index_report(row: Mapping[str, object]) -> PgVectorIndexReport:
    definition = str(row.get("definition") or "")
    access_method = str(row.get("access_method") or "").lower() or None
    if access_method is None:
        method_match = _INDEX_METHOD_PATTERN.search(definition)
        access_method = method_match.group(1).lower() if method_match else None

    lower_definition = definition.casefold()
    vector_operator_class_match = _VECTOR_OPERATOR_CLASS_PATTERN.search(definition)
    vector_operator_class = (
        vector_operator_class_match.group(0).casefold()
        if vector_operator_class_match is not None
        else None
    )
    is_vector_index = access_method in {"hnsw", "ivfflat"} and "embedding" in lower_definition
    is_full_text_gin_index = (
        access_method == "gin"
        and "to_tsvector" in lower_definition
        and "content" in lower_definition
    )
    is_metadata_gin_index = access_method == "gin" and any(
        column in lower_definition for column in ("meta_data", "metadata", "filters")
    )
    return PgVectorIndexReport(
        name=str(row.get("name") or ""),
        definition=definition,
        access_method=access_method,
        vector_operator_class=vector_operator_class,
        is_vector_index=is_vector_index,
        is_full_text_gin_index=is_full_text_gin_index,
        is_metadata_gin_index=is_metadata_gin_index,
    )


def _validated_explain_sql(explain_sql: str) -> str:
    """Allow a single read-only SELECT/WITH statement for plan capture.

    ``EXPLAIN`` without ``ANALYZE`` does not execute the statement.  We still
    reject data-definition and data-modification syntax so this diagnostic
    cannot quietly become a generic SQL runner if its implementation changes.
    """
    statement = explain_sql.strip()
    if not statement:
        raise PgVectorVerificationError("--explain-sql cannot be blank")
    if ";" in statement or "--" in statement or "/*" in statement or "*/" in statement:
        raise PgVectorVerificationError(
            "--explain-sql must be one comment-free SELECT or WITH statement"
        )
    if not re.match(r"^(?:SELECT|WITH)\b", statement, re.IGNORECASE):
        raise PgVectorVerificationError("--explain-sql must start with SELECT or WITH")
    if _DANGEROUS_EXPLAIN_TOKENS.search(statement) or re.search(
        r"\bINTO\b", statement, re.IGNORECASE
    ):
        raise PgVectorVerificationError(
            "--explain-sql must not contain data-changing or session-changing SQL"
        )
    return statement


async def _query_rows(
    connection: Any,
    statement: str,
    parameters: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    result = await connection.execute(text(statement), parameters or {})
    return [dict(row) for row in result.mappings().all()]


async def _query_scalar(
    connection: Any,
    statement: str,
) -> object | None:
    result = await connection.execute(text(statement))
    return result.scalar_one_or_none()


async def _observed_dimensions(
    connection: Any,
    *,
    qualified_table: str,
    embedding_column: str,
    vector_extension_schema: str,
) -> int | None:
    # The relation and column names come from the catalog/config and are
    # individually quoted. PostgreSQL cannot bind identifiers as parameters.
    statement = (
        f"SELECT {_quote_identifier(vector_extension_schema)}.vector_dims("
        f"{_quote_identifier(embedding_column)}) AS dimensions "
        f"FROM {qualified_table} "
        f"WHERE {_quote_identifier(embedding_column)} IS NOT NULL "
        "LIMIT 1"
    )
    rows = await _query_rows(connection, statement)
    return _optional_integer(rows[0].get("dimensions") if rows else None, field="embedding dimension")


def _base_recommendations(*, explain_requested: bool) -> list[str]:
    recommendations = [
        "This command is read-only and never creates HNSW, IVFFlat, GIN, or metadata indexes.",
        (
            "Before any index migration, measure corpus size, representative-query recall, "
            "and latency; then capture an EXPLAIN plan for the exact retrieval SQL."
        ),
    ]
    if not explain_requested:
        recommendations.append(
            "Use --explain-sql with a single representative SELECT/WITH statement to capture "
            "a non-ANALYZE JSON plan; plans are intentionally not collected by default."
        )
    return recommendations


def _build_checks(
    *,
    vector_extension_installed: bool,
    table_exists: bool,
    embedding_column: str | None,
    expected_embedding_dimensions: int,
    declared_embedding_dimensions: int | None,
    observed_embedding_dimensions: int | None,
    configured_search_type: str,
    indexes: Sequence[PgVectorIndexReport],
    explain_requested: bool,
) -> tuple[list[PgVectorCheck], list[str]]:
    checks: list[PgVectorCheck] = []
    recommendations = _base_recommendations(explain_requested=explain_requested)

    if vector_extension_installed:
        checks.append(PgVectorCheck("vector_extension", "ok", "pgvector extension is installed."))
    else:
        checks.append(
            PgVectorCheck(
                "vector_extension",
                "error",
                "The PostgreSQL vector extension is not installed in this database.",
            )
        )

    if not table_exists:
        checks.append(
            PgVectorCheck(
                "knowledge_table",
                "error",
                "Configured PgVector table was not found; initialize the knowledge store before auditing indexes.",
            )
        )
        recommendations.append(
            "Run a controlled knowledge-store initialization first; do not create an index for a table that is absent."
        )
        return checks, recommendations

    checks.append(PgVectorCheck("knowledge_table", "ok", "Configured PgVector table exists."))
    if embedding_column is None:
        checks.append(
            PgVectorCheck(
                "embedding_column",
                "error",
                "No pgvector embedding column was found in the configured table.",
            )
        )
        return checks, recommendations

    checks.append(
        PgVectorCheck("embedding_column", "ok", f"Embedding column is {embedding_column!r}."))
    if (
        declared_embedding_dimensions is not None
        and observed_embedding_dimensions is not None
        and declared_embedding_dimensions != observed_embedding_dimensions
    ):
        checks.append(
            PgVectorCheck(
                "embedding_dimension_consistency",
                "warning",
                (
                    f"Column declaration reports {declared_embedding_dimensions} dimensions, "
                    f"but the sampled row reports {observed_embedding_dimensions}."
                ),
            )
        )
        recommendations.append(
            "Investigate inconsistent stored embedding dimensions before relying on an approximate vector index."
        )
    actual_dimensions = observed_embedding_dimensions or declared_embedding_dimensions
    if actual_dimensions is None:
        checks.append(
            PgVectorCheck(
                "embedding_dimensions",
                "warning",
                "Could not determine an embedding dimension from the column definition or a stored row.",
            )
        )
    elif actual_dimensions != expected_embedding_dimensions:
        checks.append(
            PgVectorCheck(
                "embedding_dimensions",
                "error",
                (
                    f"Configured embedder expects {expected_embedding_dimensions} dimensions, "
                    f"but the table reports {actual_dimensions}."
                ),
            )
        )
        recommendations.append(
            "Resolve the embedder/table dimension mismatch before adding or tuning indexes."
        )
    else:
        checks.append(
            PgVectorCheck(
                "embedding_dimensions",
                "ok",
                f"Configured and observed/declared embedding dimensions match ({actual_dimensions}).",
            )
        )

    needs_vector_index = configured_search_type in {"vector", "hybrid"}
    needs_full_text_index = configured_search_type in {"keyword", "hybrid"}
    vector_indexes = [index for index in indexes if index.is_vector_index]
    full_text_indexes = [index for index in indexes if index.is_full_text_gin_index]
    metadata_indexes = [index for index in indexes if index.is_metadata_gin_index]

    if needs_vector_index and not vector_indexes:
        checks.append(
            PgVectorCheck(
                "vector_index",
                "warning",
                "No HNSW or IVFFlat index on the embedding column was found.",
            )
        )
        recommendations.append(
            "A vector index may be appropriate for vector retrieval, but choose HNSW/IVFFlat and "
            "parameters only after corpus-size, recall, latency, and representative EXPLAIN evidence; "
            "encode an approved choice in Alembic rather than calling Agno optimize() at runtime."
        )
    elif vector_indexes:
        wrong_operator_class = [
            index
            for index in vector_indexes
            if index.vector_operator_class not in {None, "vector_cosine_ops"}
        ]
        if wrong_operator_class:
            checks.append(
                PgVectorCheck(
                    "vector_index",
                    "warning",
                    "A vector index exists, but its operator class does not match the runtime cosine distance.",
                )
            )
        else:
            checks.append(
                PgVectorCheck(
                    "vector_index",
                    "ok",
                    f"Found {len(vector_indexes)} HNSW/IVFFlat embedding index(es).",
                )
            )
    else:
        checks.append(
            PgVectorCheck(
                "vector_index",
                "info",
                "Configured search type does not require a vector index.",
            )
        )

    if needs_full_text_index and not full_text_indexes:
        checks.append(
            PgVectorCheck(
                "full_text_gin_index",
                "warning",
                "No GIN to_tsvector(content) index was found for keyword/hybrid search.",
            )
        )
        recommendations.append(
            "Consider a full-text GIN index only if the representative query has a matching @@ predicate "
            "and EXPLAIN shows it can be used. Ranking-only scans are not proof that a GIN index will help."
        )
    elif full_text_indexes:
        checks.append(
            PgVectorCheck(
                "full_text_gin_index",
                "ok",
                f"Found {len(full_text_indexes)} GIN full-text index(es).",
            )
        )
    else:
        checks.append(
            PgVectorCheck(
                "full_text_gin_index",
                "info",
                "Configured search type does not require a full-text GIN index.",
            )
        )

    if metadata_indexes:
        checks.append(
            PgVectorCheck(
                "metadata_gin_index",
                "ok",
                f"Found {len(metadata_indexes)} GIN metadata/filter index(es).",
            )
        )
    else:
        checks.append(
            PgVectorCheck(
                "metadata_gin_index",
                "info",
                "No GIN metadata/filter index was found; this is advisory, not automatically a defect.",
            )
        )
        recommendations.append(
            "Add a JSONB GIN metadata/filter index only when meta_data/filters containment queries are frequent "
            "and an EXPLAIN plan demonstrates a benefit."
        )

    return checks, recommendations


async def verify_pgvector_indexes_async(
    *,
    engine: AsyncEngine | Any | None = None,
    schema: str | None = None,
    table_name: str | None = None,
    expected_embedding_dimensions: int | None = None,
    search_type: str | None = None,
    explain_sql: str | None = None,
) -> PgVectorIndexVerificationReport:
    """Inspect the configured PgVector table without creating or changing indexes.

    The optional ``explain_sql`` is deliberately opt-in.  It must be a single
    read-only SELECT/WITH statement and is wrapped in ``EXPLAIN (FORMAT JSON)``
    without ``ANALYZE`` so this verifier does not execute it.
    """
    settings = knowledge_settings()
    resolved_schema = schema if schema is not None else settings.postgres_schema
    resolved_table_name = table_name if table_name is not None else settings.pgvector_table
    resolved_dimensions = (
        expected_embedding_dimensions
        if expected_embedding_dimensions is not None
        else settings.embedding_dimensions
    )
    if resolved_dimensions < 1:
        raise PgVectorVerificationError("Expected embedding dimensions must be positive")
    resolved_search_type = search_type_from_name(search_type or settings.search_type).value
    normalized_explain_sql = _validated_explain_sql(explain_sql) if explain_sql is not None else None
    qualified_table = _qualified_identifier(resolved_schema, resolved_table_name)
    resolved_engine = engine or get_async_control_plane_engine()

    async with resolved_engine.connect() as connection:
        extension_rows = await _query_rows(connection, _EXTENSION_QUERY)
        extension_row = extension_rows[0] if extension_rows else None
        extension_version_value = extension_row.get("extversion") if extension_row is not None else None
        extension_schema_value = (
            extension_row.get("extension_schema") if extension_row is not None else None
        )
        extension_version = str(extension_version_value) if extension_version_value is not None else None
        extension_schema = str(extension_schema_value) if extension_schema_value is not None else None
        vector_extension_installed = extension_row is not None
        table_rows = await _query_rows(
            connection,
            _TABLE_QUERY,
            {"schema": resolved_schema, "table": resolved_table_name},
        )
        if not table_rows:
            checks, recommendations = _build_checks(
                vector_extension_installed=vector_extension_installed,
                table_exists=False,
                embedding_column=None,
                expected_embedding_dimensions=resolved_dimensions,
                declared_embedding_dimensions=None,
                observed_embedding_dimensions=None,
                configured_search_type=resolved_search_type,
                indexes=(),
                explain_requested=normalized_explain_sql is not None,
            )
            checks.append(
                PgVectorCheck(
                    "explain_plan",
                    "warning" if normalized_explain_sql is not None else "not_requested",
                    (
                        "No EXPLAIN plan was captured because the configured PgVector table was not found."
                        if normalized_explain_sql is not None
                        else "No EXPLAIN plan was captured; pass --explain-sql to request one explicitly."
                    ),
                )
            )
            return PgVectorIndexVerificationReport(
                schema=resolved_schema,
                table=resolved_table_name,
                qualified_table=qualified_table,
                configured_search_type=resolved_search_type,
                expected_embedding_dimensions=resolved_dimensions,
                vector_extension_installed=vector_extension_installed,
                vector_extension_version=extension_version,
                vector_extension_schema=extension_schema,
                table_exists=False,
                table_oid=None,
                estimated_row_count=None,
                total_relation_bytes=None,
                columns=(),
                embedding_column=None,
                declared_embedding_dimensions=None,
                observed_embedding_dimensions=None,
                indexes=(),
                checks=tuple(checks),
                recommendations=tuple(recommendations),
                explain_sql=normalized_explain_sql,
                explain_plan=None,
            )

        table_row = table_rows[0]
        table_oid = _optional_integer(table_row.get("table_oid"), field="table OID")
        if table_oid is None:
            raise PgVectorVerificationError("PostgreSQL did not return the configured table OID")
        column_rows = await _query_rows(connection, _COLUMNS_QUERY, {"table_oid": table_oid})
        columns = tuple(
            PgVectorColumnReport(
                name=str(row["name"]),
                data_type=str(row["data_type"]),
                type_name=str(row["type_name"]),
                nullable=not bool(row["not_null"]),
                declared_dimensions=_declared_dimensions(str(row["data_type"])),
            )
            for row in column_rows
        )
        embedding = next((column for column in columns if column.name == "embedding"), None)
        if embedding is None:
            embedding = next(
                (
                    column
                    for column in columns
                    if column.type_name.casefold() in {"vector", "halfvec", "sparsevec"}
                ),
                None,
            )

        index_rows = await _query_rows(
            connection,
            _INDEXES_QUERY,
            {"schema": resolved_schema, "table": resolved_table_name},
        )
        indexes = tuple(_index_report(row) for row in index_rows)
        observed_dimensions: int | None = None
        if vector_extension_installed and extension_schema is not None and embedding is not None:
            observed_dimensions = await _observed_dimensions(
                connection,
                qualified_table=qualified_table,
                embedding_column=embedding.name,
                vector_extension_schema=extension_schema,
            )

        explain_plan: object | None = None
        if normalized_explain_sql is not None:
            explain_plan = await _query_scalar(
                connection,
                f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {normalized_explain_sql}",
            )

    checks, recommendations = _build_checks(
        vector_extension_installed=vector_extension_installed,
        table_exists=True,
        embedding_column=embedding.name if embedding is not None else None,
        expected_embedding_dimensions=resolved_dimensions,
        declared_embedding_dimensions=(embedding.declared_dimensions if embedding is not None else None),
        observed_embedding_dimensions=observed_dimensions,
        configured_search_type=resolved_search_type,
        indexes=indexes,
        explain_requested=normalized_explain_sql is not None,
    )
    if normalized_explain_sql is not None:
        checks.append(
            PgVectorCheck(
                "explain_plan",
                "info",
                "Captured a non-ANALYZE JSON plan for the explicitly supplied SQL.",
            )
        )
    else:
        checks.append(
            PgVectorCheck(
                "explain_plan",
                "not_requested",
                "No EXPLAIN plan was captured; pass --explain-sql to request one explicitly.",
            )
        )

    return PgVectorIndexVerificationReport(
        schema=resolved_schema,
        table=resolved_table_name,
        qualified_table=qualified_table,
        configured_search_type=resolved_search_type,
        expected_embedding_dimensions=resolved_dimensions,
        vector_extension_installed=vector_extension_installed,
        vector_extension_version=extension_version,
        vector_extension_schema=extension_schema,
        table_exists=True,
        table_oid=table_oid,
        estimated_row_count=_optional_integer(
            table_row.get("estimated_row_count"), field="estimated row count"
        ),
        total_relation_bytes=_optional_integer(
            table_row.get("total_relation_bytes"), field="relation size"
        ),
        columns=columns,
        embedding_column=embedding.name if embedding is not None else None,
        declared_embedding_dimensions=(embedding.declared_dimensions if embedding is not None else None),
        observed_embedding_dimensions=observed_dimensions,
        indexes=indexes,
        checks=tuple(checks),
        recommendations=tuple(recommendations),
        explain_sql=normalized_explain_sql,
        explain_plan=explain_plan,
    )
