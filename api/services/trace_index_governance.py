"""Read-only auditing and explicitly gated governance for Agno trace indexes.

``agno.agno_traces`` is owned by Agno rather than this repository's Alembic
control plane.  This module consequently keeps two responsibilities separate:

* inspect the live table, its catalog indexes, and representative *read-only*
  ``EXPLAIN (ANALYZE, BUFFERS)`` evidence; and
* render/apply the two approved extension indexes only after an operator has
  opted in through the CLI.  The DDL uses PostgreSQL autocommit because
  ``CREATE INDEX CONCURRENTLY`` is forbidden inside a transaction block.

The default caller path is inspection-only.  Nothing in this module performs
DDL unless ``apply_trace_indexes`` is called deliberately.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import re
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

TraceIndexState = Literal["missing", "present", "equivalent", "conflicting"]
TracePlanState = Literal["captured", "not_available", "not_requested"]

_TRACE_TABLE = "agno_traces"
_SPANS_TABLE = "agno_spans"
_INDEX_KEY_WHITESPACE = re.compile(r"\s+")


class TraceIndexGovernanceError(ValueError):
    """Raised when a trace-index audit or apply precondition is unsafe."""


@dataclass(frozen=True, slots=True)
class TraceIndexSpec:
    """One approved btree extension index for Agno's trace table."""

    name: str
    key_definitions: tuple[str, ...]
    purpose: str


TRACE_INDEX_SPECS: tuple[TraceIndexSpec, ...] = (
    TraceIndexSpec(
        name="idx_agno_traces_user_start_time",
        key_definitions=("user_id", "start_time DESC"),
        purpose=(
            "Permission-scoped Overview SQL aggregates over user_id and the trace start-time window."
        ),
    ),
    TraceIndexSpec(
        name="idx_agno_traces_user_status_start_time",
        key_definitions=("user_id", "status", "start_time DESC"),
        purpose=(
            "Scoped ERROR trace counts and recent-failure pages before the Agno spans aggregation."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class TraceTableReport:
    """Non-sensitive live-table facts used to interpret query plans."""

    exists: bool
    oid: int | None
    owner: str | None
    estimated_rows: int | None
    live_rows: int | None
    dead_rows: int | None
    total_relation_bytes: int | None
    last_analyze: datetime | None
    last_autoanalyze: datetime | None


@dataclass(frozen=True, slots=True)
class TraceIndexCatalogEntry:
    """Relevant PostgreSQL catalog attributes for one existing trace index."""

    name: str
    definition: str
    access_method: str
    key_definitions: tuple[str, ...]
    is_valid: bool
    is_ready: bool
    is_partial: bool
    has_expressions: bool
    scans: int | None
    tuples_read: int | None
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class TraceIndexCheck:
    """Whether one approved index needs operator action."""

    name: str
    state: TraceIndexState
    purpose: str
    matching_index: str | None
    message: str
    create_sql: str


@dataclass(frozen=True, slots=True)
class TraceExplainReport:
    """A redacted representative plan; no raw user identifier is retained."""

    name: str
    state: TracePlanState
    description: str
    window_start: str | None
    window_end: str | None
    plan: object | None
    message: str | None


@dataclass(frozen=True, slots=True)
class TraceIndexVerificationReport:
    """JSON-ready audit output for the trace-index operator workflow."""

    schema: str
    table: str
    qualified_table: str
    table_report: TraceTableReport
    indexes: tuple[TraceIndexCatalogEntry, ...]
    checks: tuple[TraceIndexCheck, ...]
    explain_reports: tuple[TraceExplainReport, ...]
    recommendations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return only standard containers for predictable CLI JSON output."""
        return asdict(self)


_TABLE_QUERY = """
SELECT
    relation.oid::bigint AS oid,
    pg_get_userbyid(relation.relowner) AS owner,
    relation.reltuples::bigint AS estimated_rows,
    statistics.n_live_tup::bigint AS live_rows,
    statistics.n_dead_tup::bigint AS dead_rows,
    pg_total_relation_size(relation.oid)::bigint AS total_relation_bytes,
    statistics.last_analyze,
    statistics.last_autoanalyze
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
LEFT JOIN pg_catalog.pg_stat_all_tables AS statistics ON statistics.relid = relation.oid
WHERE namespace.nspname = :schema
  AND relation.relname = :table
  AND relation.relkind IN ('r', 'p')
"""

# ``pg_get_indexdef(indexrelid, key_position, true)`` preserves key order and
# DESC/ASC direction without brittle parsing of the full CREATE INDEX string.
_INDEXES_QUERY = """
SELECT
    index_relation.relname AS name,
    pg_get_indexdef(index_info.indexrelid) AS definition,
    access_method.amname AS access_method,
    COALESCE(
        array_agg(
            pg_get_indexdef(index_info.indexrelid, key_position.ordinality::integer, true)
            ORDER BY key_position.ordinality
        ) FILTER (
            WHERE key_position.attnum > 0
              AND key_position.ordinality <= index_info.indnkeyatts
        ),
        ARRAY[]::text[]
    ) AS key_definitions,
    index_info.indisvalid AS is_valid,
    index_info.indisready AS is_ready,
    index_info.indpred IS NOT NULL AS is_partial,
    index_info.indexprs IS NOT NULL AS has_expressions,
    usage.idx_scan::bigint AS scans,
    usage.idx_tup_read::bigint AS tuples_read,
    pg_relation_size(index_info.indexrelid)::bigint AS size_bytes
FROM pg_catalog.pg_index AS index_info
JOIN pg_catalog.pg_class AS index_relation ON index_relation.oid = index_info.indexrelid
JOIN pg_catalog.pg_class AS table_relation ON table_relation.oid = index_info.indrelid
JOIN pg_catalog.pg_namespace AS table_namespace ON table_namespace.oid = table_relation.relnamespace
JOIN pg_catalog.pg_am AS access_method ON access_method.oid = index_relation.relam
LEFT JOIN pg_catalog.pg_stat_all_indexes AS usage ON usage.indexrelid = index_info.indexrelid
LEFT JOIN LATERAL unnest(index_info.indkey) WITH ORDINALITY AS key_position(attnum, ordinality) ON true
WHERE table_namespace.nspname = :schema
  AND table_relation.relname = :table
GROUP BY
    index_relation.relname,
    index_info.indexrelid,
    index_info.indnkeyatts,
    access_method.amname,
    index_info.indisvalid,
    index_info.indisready,
    index_info.indpred,
    index_info.indexprs,
    usage.idx_scan,
    usage.idx_tup_read
ORDER BY index_relation.relname
"""


def _quote_identifier(identifier: str) -> str:
    """Quote a PostgreSQL identifier without treating dots as syntax."""
    if not identifier or "\x00" in identifier:
        raise TraceIndexGovernanceError(
            "PostgreSQL identifiers must be non-empty and cannot contain NUL"
        )
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def qualified_trace_table(schema: str) -> str:
    """Return the safely quoted Agno trace relation identifier."""
    return f"{_quote_identifier(schema)}.{_quote_identifier(_TRACE_TABLE)}"


def _normalized_index_key(value: object) -> str:
    text_value = str(value).replace('"', "").strip().casefold()
    return _INDEX_KEY_WHITESPACE.sub(" ", text_value)


def _normalized_keys(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(_normalized_index_key(value) for value in values)


def create_index_sql(spec: TraceIndexSpec, *, schema: str) -> str:
    """Render idempotent concurrent DDL for a vetted trace-index spec."""
    key_definitions = ", ".join(spec.key_definitions)
    return (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_quote_identifier(spec.name)} "
        f"ON {qualified_trace_table(schema)} USING btree ({key_definitions})"
    )


def _as_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    return int(str(value))


def _catalog_entry(row: Mapping[str, object]) -> TraceIndexCatalogEntry:
    raw_keys_value = row.get("key_definitions")
    if isinstance(raw_keys_value, str):
        raw_keys: Sequence[object] = (raw_keys_value,)
    elif isinstance(raw_keys_value, Sequence):
        raw_keys = raw_keys_value
    else:
        raw_keys = ()
    return TraceIndexCatalogEntry(
        name=str(row.get("name") or ""),
        definition=str(row.get("definition") or ""),
        access_method=str(row.get("access_method") or "").casefold(),
        key_definitions=tuple(str(value) for value in raw_keys),
        is_valid=bool(row.get("is_valid")),
        is_ready=bool(row.get("is_ready")),
        is_partial=bool(row.get("is_partial")),
        has_expressions=bool(row.get("has_expressions")),
        scans=_as_optional_int(row.get("scans")),
        tuples_read=_as_optional_int(row.get("tuples_read")),
        size_bytes=_as_optional_int(row.get("size_bytes")),
    )


def _is_equivalent_index(entry: TraceIndexCatalogEntry, spec: TraceIndexSpec) -> bool:
    """Return true only for an online, plain btree with exactly the target keys."""
    return (
        entry.access_method == "btree"
        and entry.is_valid
        and entry.is_ready
        and not entry.is_partial
        and not entry.has_expressions
        and _normalized_keys(entry.key_definitions)
        == _normalized_keys(spec.key_definitions)
    )


def evaluate_trace_index_checks(
    indexes: Sequence[TraceIndexCatalogEntry], *, schema: str
) -> tuple[TraceIndexCheck, ...]:
    """Classify known specs without creating duplicate or invalid indexes."""
    checks: list[TraceIndexCheck] = []
    for spec in TRACE_INDEX_SPECS:
        named = next((entry for entry in indexes if entry.name == spec.name), None)
        equivalent = next(
            (entry for entry in indexes if _is_equivalent_index(entry, spec)), None
        )
        create_sql = create_index_sql(spec, schema=schema)
        if named is not None and _is_equivalent_index(named, spec):
            checks.append(
                TraceIndexCheck(
                    name=spec.name,
                    state="present",
                    purpose=spec.purpose,
                    matching_index=named.name,
                    message="The expected valid btree index is already present.",
                    create_sql=create_sql,
                )
            )
        elif named is not None:
            checks.append(
                TraceIndexCheck(
                    name=spec.name,
                    state="conflicting",
                    purpose=spec.purpose,
                    matching_index=named.name,
                    message=(
                        "An index with the approved name exists but is not a valid equivalent; "
                        "refuse automatic DDL until it is reviewed."
                    ),
                    create_sql=create_sql,
                )
            )
        elif equivalent is not None:
            checks.append(
                TraceIndexCheck(
                    name=spec.name,
                    state="equivalent",
                    purpose=spec.purpose,
                    matching_index=equivalent.name,
                    message=(
                        "A valid equivalent index with a different name already exists; "
                        "no duplicate will be created."
                    ),
                    create_sql=create_sql,
                )
            )
        else:
            checks.append(
                TraceIndexCheck(
                    name=spec.name,
                    state="missing",
                    purpose=spec.purpose,
                    matching_index=None,
                    message="No valid equivalent index was found.",
                    create_sql=create_sql,
                )
            )
    return tuple(checks)


def _table_report(row: Mapping[str, object] | None) -> TraceTableReport:
    if row is None:
        return TraceTableReport(
            exists=False,
            oid=None,
            owner=None,
            estimated_rows=None,
            live_rows=None,
            dead_rows=None,
            total_relation_bytes=None,
            last_analyze=None,
            last_autoanalyze=None,
        )
    last_analyze = row.get("last_analyze")
    last_autoanalyze = row.get("last_autoanalyze")
    return TraceTableReport(
        exists=True,
        oid=_as_optional_int(row.get("oid")),
        owner=str(row.get("owner")) if row.get("owner") is not None else None,
        estimated_rows=_as_optional_int(row.get("estimated_rows")),
        live_rows=_as_optional_int(row.get("live_rows")),
        dead_rows=_as_optional_int(row.get("dead_rows")),
        total_relation_bytes=_as_optional_int(row.get("total_relation_bytes")),
        last_analyze=last_analyze if isinstance(last_analyze, datetime) else None,
        last_autoanalyze=last_autoanalyze
        if isinstance(last_autoanalyze, datetime)
        else None,
    )


def _query_mappings(
    connection: Connection,
    statement: str,
    parameters: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    result = connection.execute(text(statement), parameters or {})
    return [dict(row) for row in result.mappings().all()]


def _read_catalog(
    connection: Connection, *, schema: str
) -> tuple[TraceTableReport, tuple[TraceIndexCatalogEntry, ...]]:
    table_rows = _query_mappings(
        connection,
        _TABLE_QUERY,
        {"schema": schema, "table": _TRACE_TABLE},
    )
    table_report = _table_report(table_rows[0] if table_rows else None)
    if not table_report.exists:
        return table_report, ()
    index_rows = _query_mappings(
        connection,
        _INDEXES_QUERY,
        {"schema": schema, "table": _TRACE_TABLE},
    )
    return table_report, tuple(_catalog_entry(row) for row in index_rows)


def _read_only_transaction(
    connection: Connection, *, statement_timeout_ms: int
) -> None:
    """Start a bounded server-side read-only transaction before any catalog read."""
    if statement_timeout_ms < 1_000 or statement_timeout_ms > 60_000:
        raise TraceIndexGovernanceError(
            "statement_timeout_ms must be between 1000 and 60000"
        )
    connection.execute(text("BEGIN TRANSACTION READ ONLY"))
    connection.execute(
        text(f"SET LOCAL statement_timeout = '{statement_timeout_ms}ms'")
    )
    connection.execute(text("SET LOCAL lock_timeout = '2s'"))


def _redact_plan(value: object, *, secrets: Iterable[str]) -> object:
    """Recursively remove selected user ids from PostgreSQL JSON plan output."""
    values = tuple(value for value in secrets if value)
    if isinstance(value, str):
        redacted = value
        for secret in values:
            redacted = redacted.replace(secret, "<redacted-user-id>")
        return redacted
    if isinstance(value, list):
        return [_redact_plan(item, secrets=values) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_plan(item, secrets=values) for item in value)
    if isinstance(value, dict):
        return {
            str(key): _redact_plan(item, secrets=values) for key, item in value.items()
        }
    return value


def _parse_trace_time(value: object) -> datetime | None:
    # SQLAlchemy/psycopg decodes PostgreSQL timestamp columns to ``datetime``;
    # retain string support for alternate drivers and lightweight test rows.
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def _anchor_window(
    start_time: object, end_time: object, *, hours: int = 24
) -> tuple[str, str] | None:
    start = _parse_trace_time(start_time)
    end = _parse_trace_time(end_time) or start
    if start is None or end is None:
        return None
    upper = max(start, end) + timedelta(seconds=1)
    lower = upper - timedelta(hours=hours)
    return lower.isoformat(), upper.isoformat()


def _explain_json(
    connection: Connection,
    *,
    statement: str,
    parameters: Mapping[str, object],
    redacted_values: Iterable[str] = (),
) -> object:
    result = connection.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}"), parameters
    )
    plan = result.scalar_one()
    return _redact_plan(plan, secrets=redacted_values)


def _not_available_plan(
    name: str, description: str, message: str
) -> TraceExplainReport:
    return TraceExplainReport(
        name=name,
        state="not_available",
        description=description,
        window_start=None,
        window_end=None,
        plan=None,
        message=message,
    )


def _collect_explain_reports(
    connection: Connection, *, schema: str
) -> tuple[TraceExplainReport, ...]:
    """Capture non-sensitive plans for the exact trace filters used by Overview.

    Each plan finds a recent anchor from the actual table, then uses a 24-hour
    window around it.  This avoids reporting a misleading all-zero plan when
    local/staging data happened to be written days before the command runs.
    """
    table = qualified_trace_table(schema)
    latest_rows = _query_mappings(
        connection,
        f"""
        SELECT start_time, end_time
        FROM {table}
        WHERE start_time IS NOT NULL
        ORDER BY start_time DESC
        LIMIT 1
        """,
    )
    if not latest_rows:
        missing = _not_available_plan(
            "overview_unscoped_window",
            "Overview SQL aggregate: start_time range.",
            "No trace row is available to derive a representative window.",
        )
        return (missing,)

    reports: list[TraceExplainReport] = []
    latest_window = _anchor_window(
        latest_rows[0].get("start_time"), latest_rows[0].get("end_time")
    )
    if latest_window is None:
        reports.append(
            _not_available_plan(
                "overview_unscoped_window",
                "Overview SQL aggregate: start_time range.",
                "The newest trace has an unparsable ISO timestamp.",
            )
        )
    else:
        start_time, end_time = latest_window
        plan = _explain_json(
            connection,
            statement=f"""
                SELECT count(*) AS n
                FROM {table}
                WHERE start_time >= :start_time AND start_time <= :end_time
            """,
            parameters={"start_time": start_time, "end_time": end_time},
        )
        reports.append(
            TraceExplainReport(
                name="overview_unscoped_window",
                state="captured",
                description="Overview SQL aggregate: start_time range.",
                window_start=start_time,
                window_end=end_time,
                plan=plan,
                message=None,
            )
        )

    scoped_rows = _query_mappings(
        connection,
        f"""
        SELECT user_id, start_time, end_time
        FROM {table}
        WHERE user_id IS NOT NULL AND user_id <> '' AND start_time IS NOT NULL
        ORDER BY start_time DESC
        LIMIT 1
        """,
    )
    if not scoped_rows:
        reports.append(
            _not_available_plan(
                "overview_scoped_window",
                "Overview SQL aggregate: user_id plus start_time range.",
                "No scoped trace row is available to derive a representative window.",
            )
        )
    else:
        scoped = scoped_rows[0]
        scoped_window = _anchor_window(scoped.get("start_time"), scoped.get("end_time"))
        user_id = str(scoped["user_id"])
        if scoped_window is None:
            reports.append(
                _not_available_plan(
                    "overview_scoped_window",
                    "Overview SQL aggregate: user_id plus start_time range.",
                    "The newest scoped trace has an unparsable ISO timestamp.",
                )
            )
        else:
            start_time, end_time = scoped_window
            plan = _explain_json(
                connection,
                statement=f"""
                    SELECT count(*) AS n
                    FROM {table}
                    WHERE user_id = :user_id
                      AND start_time >= :start_time
                      AND start_time <= :end_time
                """,
                parameters={
                    "user_id": user_id,
                    "start_time": start_time,
                    "end_time": end_time,
                },
                redacted_values=(user_id,),
            )
            reports.append(
                TraceExplainReport(
                    name="overview_scoped_window",
                    state="captured",
                    description="Overview SQL aggregate: user_id plus start_time range.",
                    window_start=start_time,
                    window_end=end_time,
                    plan=plan,
                    message=None,
                )
            )

    error_rows = _query_mappings(
        connection,
        f"""
        SELECT user_id, start_time, end_time
        FROM {table}
        WHERE user_id IS NOT NULL
          AND user_id <> ''
          AND status = 'ERROR'
          AND start_time IS NOT NULL
        ORDER BY start_time DESC
        LIMIT 1
        """,
    )
    if not error_rows:
        reports.append(
            _not_available_plan(
                "agno_error_trace_page",
                "Agno ERROR trace page: user_id, status, start_time, end_time, and spans join.",
                "No scoped ERROR trace is available to derive a representative window.",
            )
        )
    else:
        error = error_rows[0]
        error_window = _anchor_window(error.get("start_time"), error.get("end_time"))
        user_id = str(error["user_id"])
        if error_window is None:
            reports.append(
                _not_available_plan(
                    "agno_error_trace_page",
                    "Agno ERROR trace page: user_id, status, start_time, end_time, and spans join.",
                    "The newest scoped ERROR trace has an unparsable ISO timestamp.",
                )
            )
        else:
            start_time, end_time = error_window
            plan = _explain_json(
                connection,
                statement=f"""
                    SELECT t.*, coalesce(count(s.span_id), 0) AS total_spans,
                           coalesce(sum(CASE WHEN s.status_code = 'ERROR' THEN 1 ELSE 0 END), 0)
                             AS error_count
                    FROM {table} AS t
                    LEFT OUTER JOIN {_quote_identifier(schema)}.{_quote_identifier(_SPANS_TABLE)} AS s
                      ON t.trace_id = s.trace_id
                    WHERE t.user_id = :user_id
                      AND t.status = 'ERROR'
                      AND t.start_time >= :start_time
                      AND t.end_time <= :end_time
                    GROUP BY t.trace_id
                    ORDER BY t.start_time DESC
                    LIMIT 10
                """,
                parameters={
                    "user_id": user_id,
                    "start_time": start_time,
                    "end_time": end_time,
                },
                redacted_values=(user_id,),
            )
            reports.append(
                TraceExplainReport(
                    name="agno_error_trace_page",
                    state="captured",
                    description=(
                        "Agno ERROR trace page: user_id, status, start_time, end_time, and spans join."
                    ),
                    window_start=start_time,
                    window_end=end_time,
                    plan=plan,
                    message=None,
                )
            )
    return tuple(reports)


def _recommendations(
    *,
    table_report: TraceTableReport,
    checks: Sequence[TraceIndexCheck],
    explain_requested: bool,
) -> tuple[str, ...]:
    recommendations = [
        "Agno owns agno.agno_traces; do not add these indexes to the repository Alembic control-plane chain.",
        "The proposed DDL is idempotent and uses CREATE INDEX CONCURRENTLY, but it is never executed by a read-only audit.",
        "Review the redacted EXPLAIN evidence and write amplification on a production-like dataset before --apply.",
    ]
    if not table_report.exists:
        recommendations.append(
            "Initialize Agno's trace store before applying an index extension; no DDL is safe while the table is absent."
        )
    if any(check.state == "conflicting" for check in checks):
        recommendations.append(
            "Resolve conflicting/invalid existing index names manually; the apply mode intentionally refuses to guess."
        )
    if not explain_requested:
        recommendations.append(
            "Pass --explain to execute bounded read-only representative queries and capture EXPLAIN (ANALYZE, BUFFERS) JSON."
        )
    return tuple(recommendations)


def verify_trace_indexes(
    engine: Engine,
    *,
    schema: str,
    explain: bool = False,
    statement_timeout_ms: int = 15_000,
) -> TraceIndexVerificationReport:
    """Inspect trace indexes in a rollback-only, server-enforced read-only transaction."""
    # Validate early even if the database is unavailable, and quote internally
    # below because PostgreSQL parameters cannot bind relation identifiers.
    qualified_table = qualified_trace_table(schema)
    with engine.connect() as connection:
        _read_only_transaction(connection, statement_timeout_ms=statement_timeout_ms)
        try:
            table_report, indexes = _read_catalog(connection, schema=schema)
            checks = evaluate_trace_index_checks(indexes, schema=schema)
            if explain and table_report.exists:
                explain_reports = _collect_explain_reports(connection, schema=schema)
            elif explain:
                explain_reports = (
                    _not_available_plan(
                        "trace_table",
                        "Trace query plans.",
                        "The configured Agno trace table does not exist.",
                    ),
                )
            else:
                explain_reports = (
                    TraceExplainReport(
                        name="trace_queries",
                        state="not_requested",
                        description="Representative Overview and Agno trace query plans.",
                        window_start=None,
                        window_end=None,
                        plan=None,
                        message="Pass --explain to collect bounded read-only EXPLAIN evidence.",
                    ),
                )
            return TraceIndexVerificationReport(
                schema=schema,
                table=_TRACE_TABLE,
                qualified_table=qualified_table,
                table_report=table_report,
                indexes=indexes,
                checks=checks,
                explain_reports=explain_reports,
                recommendations=_recommendations(
                    table_report=table_report,
                    checks=checks,
                    explain_requested=explain,
                ),
            )
        finally:
            connection.rollback()


def assert_trace_indexes_applyable(
    report: TraceIndexVerificationReport,
) -> tuple[TraceIndexCheck, ...]:
    """Fail closed when a pre/postflight report is unsafe for index creation."""
    if not report.table_report.exists:
        raise TraceIndexGovernanceError(
            f"Cannot apply trace indexes: {report.qualified_table} does not exist."
        )
    conflicts = [check.name for check in report.checks if check.state == "conflicting"]
    if conflicts:
        raise TraceIndexGovernanceError(
            "Cannot apply trace indexes while conflicting names exist: "
            + ", ".join(conflicts)
        )
    return tuple(check for check in report.checks if check.state == "missing")


def apply_trace_indexes(
    engine: Engine,
    *,
    schema: str,
    statement_timeout_ms: int = 15_000,
) -> tuple[str, ...]:
    """Create only missing approved indexes using PostgreSQL autocommit.

    Callers must enforce their own human confirmation before this method.  A
    preflight catalog read refuses conflicting names, and each statement is
    explicitly ``CONCURRENTLY IF NOT EXISTS`` so re-runs are safe.
    """
    preflight = verify_trace_indexes(
        engine,
        schema=schema,
        explain=False,
        statement_timeout_ms=statement_timeout_ms,
    )
    missing = assert_trace_indexes_applyable(preflight)
    if not missing:
        return ()

    applied: list[str] = []
    with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
        for check in missing:
            # PostgreSQL prohibits CREATE INDEX CONCURRENTLY inside an explicit
            # transaction.  AUTOCOMMIT is therefore a correctness requirement,
            # not merely a performance preference.
            connection.execute(text(check.create_sql))
            applied.append(check.name)
    return tuple(applied)
