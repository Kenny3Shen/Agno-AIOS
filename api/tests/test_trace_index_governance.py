from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.engine import Connection, Engine

from api.services import trace_index_governance as governance
from api.tasks import audit_trace_indexes as task


def _entry(
    *,
    name: str,
    keys: tuple[str, ...],
    valid: bool = True,
    ready: bool = True,
    method: str = "btree",
) -> governance.TraceIndexCatalogEntry:
    return governance.TraceIndexCatalogEntry(
        name=name,
        definition=f"CREATE INDEX {name}",
        access_method=method,
        key_definitions=keys,
        is_valid=valid,
        is_ready=ready,
        is_partial=False,
        has_expressions=False,
        scans=0,
        tuples_read=0,
        size_bytes=1024,
    )


def _report(
    *checks: governance.TraceIndexCheck,
) -> governance.TraceIndexVerificationReport:
    return governance.TraceIndexVerificationReport(
        schema="agno",
        table="agno_traces",
        qualified_table='"agno"."agno_traces"',
        table_report=governance.TraceTableReport(
            exists=True,
            oid=1,
            owner="operator",
            estimated_rows=1,
            live_rows=1,
            dead_rows=0,
            total_relation_bytes=1024,
            last_analyze=None,
            last_autoanalyze=None,
        ),
        indexes=(),
        checks=checks,
        explain_reports=(),
        recommendations=(),
    )


def test_create_sql_is_quoted_idempotent_and_concurrent() -> None:
    sql = governance.create_index_sql(governance.TRACE_INDEX_SPECS[0], schema='a"gno')

    assert sql == (
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_agno_traces_user_start_time" '
        'ON "a""gno"."agno_traces" USING btree (user_id, start_time DESC)'
    )


def test_index_checks_distinguish_present_equivalent_missing_and_conflicts() -> None:
    user_start, user_status_start = governance.TRACE_INDEX_SPECS
    indexes = (
        _entry(name=user_start.name, keys=("user_id", "start_time DESC")),
        _entry(
            name="operator_trace_error_index",
            keys=("user_id", "status", "start_time DESC"),
        ),
    )

    checks = governance.evaluate_trace_index_checks(indexes, schema="agno")

    assert [(check.name, check.state, check.matching_index) for check in checks] == [
        (user_start.name, "present", user_start.name),
        (user_status_start.name, "equivalent", "operator_trace_error_index"),
    ]

    conflicting = governance.evaluate_trace_index_checks(
        (_entry(name=user_start.name, keys=("status", "start_time DESC")),),
        schema="agno",
    )
    assert conflicting[0].state == "conflicting"
    assert conflicting[1].state == "missing"


def test_index_check_rejects_invalid_same_name_even_with_expected_keys() -> None:
    spec = governance.TRACE_INDEX_SPECS[0]
    checks = governance.evaluate_trace_index_checks(
        (_entry(name=spec.name, keys=spec.key_definitions, valid=False),), schema="agno"
    )

    assert checks[0].state == "conflicting"
    assert "refuse automatic DDL" in checks[0].message


def test_catalog_query_excludes_include_columns_from_equivalence_keys() -> None:
    """A covering index with the same search keys must not cause duplicate DDL."""
    assert (
        "key_position.ordinality <= index_info.indnkeyatts" in governance._INDEXES_QUERY
    )


def test_read_only_transaction_begins_before_catalog_queries_and_bounds_timeout() -> (
    None
):
    statements: list[str] = []

    class ConnectionStub:
        def execute(self, statement):
            statements.append(str(statement))

    governance._read_only_transaction(
        cast(Connection, ConnectionStub()), statement_timeout_ms=5_000
    )

    assert statements == [
        "BEGIN TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '5000ms'",
        "SET LOCAL lock_timeout = '2s'",
    ]
    assert all(
        "CREATE" not in statement and "ALTER" not in statement
        for statement in statements
    )


def test_redact_plan_removes_selected_user_id_recursively() -> None:
    plan = {
        "Plan": {
            "Filter": "(user_id = 'user-secret')",
            "Nested": ["user-secret", 42],
        }
    }

    redacted = governance._redact_plan(plan, secrets=("user-secret",))

    assert redacted == {
        "Plan": {
            "Filter": "(user_id = '<redacted-user-id>')",
            "Nested": ["<redacted-user-id>", 42],
        }
    }


def test_anchor_window_accepts_postgres_datetime_values() -> None:
    """psycopg returns timestamp columns as datetime, not ISO strings."""
    start = datetime(2026, 7, 22, 9, 30, tzinfo=UTC)

    window = governance._anchor_window(start, start + timedelta(minutes=5))

    assert window == (
        "2026-07-21T09:35:01+00:00",
        "2026-07-22T09:35:01+00:00",
    )


def test_apply_uses_autocommit_and_only_missing_index_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_spec = governance.TRACE_INDEX_SPECS[0]
    present_spec = governance.TRACE_INDEX_SPECS[1]
    checks = governance.evaluate_trace_index_checks(
        (_entry(name=present_spec.name, keys=present_spec.key_definitions),),
        schema="agno",
    )
    assert checks[0].name == missing_spec.name and checks[0].state == "missing"
    monkeypatch.setattr(
        governance, "verify_trace_indexes", lambda *_args, **_kwargs: _report(*checks)
    )
    captured: dict[str, object] = {"statements": []}

    class ConnectionContext:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback) -> None:
            return None

        def execute(self, statement) -> None:
            cast(list[str], captured["statements"]).append(str(statement))

    class EngineStub:
        def execution_options(self, **kwargs):
            captured["options"] = kwargs
            return self

        def connect(self):
            return ConnectionContext()

    applied = governance.apply_trace_indexes(cast(Engine, EngineStub()), schema="agno")

    assert applied == (missing_spec.name,)
    assert captured["options"] == {"isolation_level": "AUTOCOMMIT"}
    assert captured["statements"] == [
        governance.create_index_sql(missing_spec, schema="agno")
    ]


def test_apply_refuses_conflicting_preflight_without_opening_autocommit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = governance.TRACE_INDEX_SPECS[0]
    checks = governance.evaluate_trace_index_checks(
        (_entry(name=spec.name, keys=("status",)),), schema="agno"
    )
    monkeypatch.setattr(
        governance, "verify_trace_indexes", lambda *_args, **_kwargs: _report(*checks)
    )

    class EngineStub:
        def execution_options(self, **_kwargs):
            raise AssertionError("DDL connection must not open for a conflict")

    with pytest.raises(governance.TraceIndexGovernanceError, match="conflicting"):
        governance.apply_trace_indexes(cast(Engine, EngineStub()), schema="agno")


def _args(**overrides: object) -> Namespace:
    values: dict[str, object] = {
        "database_url": "postgresql://operator:secret@db.example.test/tais",
        "schema": "agno",
        "explain": False,
        "statement_timeout_ms": 15_000,
        "apply": False,
        "confirm": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_cli_requires_explicit_confirmation_before_apply() -> None:
    with pytest.raises(governance.TraceIndexGovernanceError, match="--confirm"):
        task._validate_apply_args(_args(apply=True))
    with pytest.raises(governance.TraceIndexGovernanceError, match="only meaningful"):
        task._validate_apply_args(_args(confirm="CREATE_AGNO_TRACE_INDEXES"))


def test_cli_default_never_calls_apply_and_redacts_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check = governance.TraceIndexCheck(
        name="index",
        state="missing",
        purpose="test",
        matching_index=None,
        message="missing",
        create_sql="CREATE INDEX CONCURRENTLY IF NOT EXISTS test",
    )
    report = _report(check)
    disposed: list[bool] = []

    class EngineStub:
        def dispose(self) -> None:
            disposed.append(True)

    monkeypatch.setattr(task, "_engine", lambda _url: cast(Engine, EngineStub()))
    monkeypatch.setattr(task, "verify_trace_indexes", lambda *_args, **_kwargs: report)
    monkeypatch.setattr(
        task,
        "apply_trace_indexes",
        lambda *_args, **_kwargs: pytest.fail("must not apply"),
    )

    result = task.main(_args())

    assert result["applied"] is False
    assert result["database"] == "postgresql://db.example.test/tais"
    assert disposed == [True]


def test_cli_apply_rechecks_postflight(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = governance.TraceIndexCheck(
        name="index",
        state="missing",
        purpose="test",
        matching_index=None,
        message="missing",
        create_sql="CREATE INDEX CONCURRENTLY IF NOT EXISTS test",
    )
    present = replace(
        missing, state="present", matching_index="index", message="present"
    )
    reports = iter((_report(missing), _report(present)))

    class EngineStub:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(task, "_engine", lambda _url: cast(Engine, EngineStub()))
    monkeypatch.setattr(
        task, "verify_trace_indexes", lambda *_args, **_kwargs: next(reports)
    )
    monkeypatch.setattr(
        task, "apply_trace_indexes", lambda *_args, **_kwargs: ("index",)
    )

    result = task.main(_args(apply=True, confirm="CREATE_AGNO_TRACE_INDEXES"))

    assert result["applied"] is True
    assert result["applied_indexes"] == ["index"]
