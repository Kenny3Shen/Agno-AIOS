from __future__ import annotations

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects import postgresql

from api.persistence import migrations
from api.config import get_settings
from api.persistence.schema_metadata import control_plane_metadata
from api.utils.async_once import AsyncOnce


def _eval_run_snapshots_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260725_0023_eval_run_execution_snapshots.py"
    )
    spec = spec_from_file_location("eval_run_snapshots_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _eval_case_terminal_checkpoint_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260725_0024_eval_case_terminal_checkpoints.py"
    )
    spec = spec_from_file_location("eval_case_terminal_checkpoint_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _eval_execution_fencing_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260725_0026_eval_suite_execution_fencing.py"
    )
    spec = spec_from_file_location("eval_execution_fencing_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _eval_case_work_items_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260725_0027_eval_case_work_items.py"
    )
    spec = spec_from_file_location("eval_case_work_items_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _terminalize_legacy_eval_runs_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260725_0028_terminalize_legacy_active_eval_runs.py"
    )
    spec = spec_from_file_location("terminalize_legacy_eval_runs_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _simplify_rbac_roles_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260725_0029_simplify_rbac_roles.py"
    )
    spec = spec_from_file_location("simplify_rbac_roles_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _user_auth_versions_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260726_0030_user_auth_versions.py"
    )
    spec = spec_from_file_location("user_auth_versions_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_baseline_does_not_include_future_control_plane_schema() -> None:
    """Keep the initial revision frozen before the first later table migration.

    Rendering through 20260720_0003 is enough to catch the historical failure:
    a live ``control_plane_metadata()`` import put ``knowledge_rag_settings``
    into 0001, then 0003 tried to create it a second time on every fresh DB.
    """
    repository_root = Path(__file__).resolve().parents[2]
    app_schema = "alembic_frozen_baseline_app"
    environment = os.environ.copy()
    environment.update(
        {
            "TAIS_APP_SCHEMA": app_schema,
            "AGNO_DB_SCHEMA": "alembic_frozen_baseline_db",
            "TAIS_MCP_SCHEMA": "alembic_frozen_baseline_mcp",
            "TAIS_KNOWLEDGE_SCHEMA": "alembic_frozen_baseline_knowledge",
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "20260720_0003",
            "--sql",
        ],
        cwd=repository_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    sql = completed.stdout
    assert sql.count(f"CREATE TABLE {app_schema}.knowledge_rag_settings") == 1

    case_definition = re.search(
        rf'CREATE TABLE IF NOT EXISTS "{app_schema}"\.agent_eval_cases \((.*?)\n\);',
        sql,
        flags=re.DOTALL,
    )
    assert case_definition is not None
    initial_case_columns = case_definition.group(1)
    assert "target_agent_id" in initial_case_columns
    assert "judge_mode" not in initial_case_columns
    assert "additional_guidelines" not in initial_case_columns
    assert "timeout_seconds" not in initial_case_columns
    assert "tags JSONB" not in initial_case_columns


def test_eval_run_snapshot_migration_adds_private_json_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _eval_run_snapshots_revision()
    added: list[tuple[str, Any, str | None]] = []
    removed: list[tuple[str, str, str | None]] = []

    class Operations:
        def add_column(self, table: str, column: Any, *, schema: str | None) -> None:
            added.append((table, column, schema))

        def drop_column(self, table: str, column: str, *, schema: str | None) -> None:
            removed.append((table, column, schema))

    monkeypatch.setattr(revision, "op", Operations())
    monkeypatch.setattr(
        revision,
        "get_settings",
        lambda: SimpleNamespace(agno_app_schema="eval_test"),
    )

    revision.upgrade()

    assert revision.down_revision == "20260724_0022"
    assert [(table, column.name, schema) for table, column, schema in added] == [
        ("agent_eval_suite_runs", "execution_snapshot", "eval_test"),
        ("agent_eval_case_runs", "definition_snapshot", "eval_test"),
        ("agent_eval_case_runs", "execution_provenance", "eval_test"),
    ]
    for _, column, _ in added:
        assert getattr(column, "nullable") is False
        assert "JSONB" in str(getattr(column, "type")).upper()
        default = getattr(column, "server_default")
        assert default is not None
        assert str(default.arg) == "'{}'::jsonb"

    revision.downgrade()

    assert removed == [
        ("agent_eval_case_runs", "execution_provenance", "eval_test"),
        ("agent_eval_case_runs", "definition_snapshot", "eval_test"),
        ("agent_eval_suite_runs", "execution_snapshot", "eval_test"),
    ]


def test_eval_case_terminal_checkpoint_migration_adds_private_json_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _eval_case_terminal_checkpoint_revision()
    added: list[tuple[str, Any, str | None]] = []
    removed: list[tuple[str, str, str | None]] = []

    class Operations:
        def add_column(self, table: str, column: Any, *, schema: str | None) -> None:
            added.append((table, column, schema))

        def drop_column(self, table: str, column: str, *, schema: str | None) -> None:
            removed.append((table, column, schema))

    monkeypatch.setattr(revision, "op", Operations())
    monkeypatch.setattr(
        revision,
        "get_settings",
        lambda: SimpleNamespace(agno_app_schema="eval_test"),
    )

    revision.upgrade()

    assert revision.down_revision == "20260725_0023"
    assert [(table, column.name, schema) for table, column, schema in added] == [
        ("agent_eval_case_runs", "terminal_checkpoint", "eval_test"),
    ]
    column = added[0][1]
    assert getattr(column, "nullable") is False
    assert "JSONB" in str(getattr(column, "type")).upper()
    default = getattr(column, "server_default")
    assert default is not None
    assert str(default.arg) == "'{}'::jsonb"

    revision.downgrade()

    assert removed == [("agent_eval_case_runs", "terminal_checkpoint", "eval_test")]


def test_eval_execution_fencing_migration_adds_private_lease_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _eval_execution_fencing_revision()
    added: list[tuple[str, Any, str | None]] = []
    removed: list[tuple[str, str, str | None]] = []
    indexes: list[tuple[str, str, list[str], dict[str, Any]]] = []
    dropped_indexes: list[tuple[str, str, str | None]] = []

    class Operations:
        def add_column(self, table: str, column: Any, *, schema: str | None) -> None:
            added.append((table, column, schema))

        def drop_column(self, table: str, column: str, *, schema: str | None) -> None:
            removed.append((table, column, schema))

        def create_index(
            self,
            name: str,
            table: str,
            columns: list[str],
            **kwargs: Any,
        ) -> None:
            indexes.append((name, table, columns, kwargs))

        def drop_index(
            self,
            name: str,
            *,
            table_name: str,
            schema: str | None,
        ) -> None:
            assert table_name == "agent_eval_case_runs"
            dropped_indexes.append((name, table_name, schema))

    monkeypatch.setattr(revision, "op", Operations())
    monkeypatch.setattr(
        revision,
        "get_settings",
        lambda: SimpleNamespace(agno_app_schema="eval_test"),
    )

    revision.upgrade()

    assert revision.down_revision == "20260725_0025"
    assert [(table, column.name, schema) for table, column, schema in added] == [
        ("agent_eval_suite_runs", "active_job_id", "eval_test"),
        ("agent_eval_suite_runs", "active_lease_epoch", "eval_test"),
        ("agent_eval_case_runs", "lease_job_id", "eval_test"),
        ("agent_eval_case_runs", "lease_epoch", "eval_test"),
    ]
    assert indexes[0][0:3] == (
        "uq_agent_eval_case_runs_fenced_suite_case",
        "agent_eval_case_runs",
        ["suite_run_id", "case_id"],
    )
    assert indexes[0][3]["unique"] is True

    revision.downgrade()

    assert dropped_indexes == [
        ("uq_agent_eval_case_runs_fenced_suite_case", "agent_eval_case_runs", "eval_test")
    ]
    assert removed == [
        ("agent_eval_case_runs", "lease_epoch", "eval_test"),
        ("agent_eval_case_runs", "lease_job_id", "eval_test"),
        ("agent_eval_suite_runs", "active_lease_epoch", "eval_test"),
        ("agent_eval_suite_runs", "active_job_id", "eval_test"),
    ]


def test_eval_case_work_items_migration_adds_ordered_unique_work_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _eval_case_work_items_revision()
    added: list[tuple[str, Any, str | None]] = []
    removed: list[tuple[str, str, str | None]] = []
    indexes: list[tuple[str, str, list[str], dict[str, Any]]] = []
    dropped_indexes: list[tuple[str, str, str | None]] = []

    class Operations:
        def add_column(self, table: str, column: Any, *, schema: str | None) -> None:
            added.append((table, column, schema))

        def drop_column(self, table: str, column: str, *, schema: str | None) -> None:
            removed.append((table, column, schema))

        def create_index(
            self,
            name: str,
            table: str,
            columns: list[str],
            **kwargs: Any,
        ) -> None:
            indexes.append((name, table, columns, kwargs))

        def drop_index(
            self,
            name: str,
            *,
            table_name: str,
            schema: str | None,
        ) -> None:
            dropped_indexes.append((name, table_name, schema))

    monkeypatch.setattr(revision, "op", Operations())
    monkeypatch.setattr(
        revision,
        "get_settings",
        lambda: SimpleNamespace(agno_app_schema="eval_test"),
    )

    revision.upgrade()

    assert revision.down_revision == "20260725_0026"
    assert [(table, column.name, schema) for table, column, schema in added] == [
        ("agent_eval_case_runs", "work_item_index", "eval_test"),
    ]
    assert [(name, table, columns) for name, table, columns, _ in indexes] == [
        (
            "uq_agent_eval_case_runs_work_item_order",
            "agent_eval_case_runs",
            ["suite_run_id", "work_item_index"],
        ),
        (
            "uq_agent_eval_case_runs_work_item_case",
            "agent_eval_case_runs",
            ["suite_run_id", "case_id"],
        ),
    ]
    assert all(kwargs["unique"] is True for *_, kwargs in indexes)

    revision.downgrade()

    assert dropped_indexes == [
        (
            "uq_agent_eval_case_runs_work_item_case",
            "agent_eval_case_runs",
            "eval_test",
        ),
        (
            "uq_agent_eval_case_runs_work_item_order",
            "agent_eval_case_runs",
            "eval_test",
        ),
    ]
    assert removed == [("agent_eval_case_runs", "work_item_index", "eval_test")]


def test_terminalize_legacy_active_eval_runs_migration_only_updates_empty_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _terminalize_legacy_eval_runs_revision()
    executed: list[Any] = []

    class Operations:
        def execute(self, statement: Any) -> None:
            executed.append(statement)

    monkeypatch.setattr(revision, "op", Operations())
    monkeypatch.setattr(
        revision,
        "get_settings",
        lambda: SimpleNamespace(agno_app_schema="eval_test"),
    )

    revision.upgrade()

    assert revision.down_revision == "20260725_0027"
    assert len(executed) == 1
    compiled = executed[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "UPDATE eval_test.agent_eval_suite_runs" in sql
    assert "status IN" in sql
    assert "execution_snapshot IS NULL" in sql
    assert "execution_snapshot = '{}'::jsonb" in sql
    assert "completed_at=now()" in sql
    assert compiled.params["status"] == "error"
    assert compiled.params["error_summary"] == revision._LEGACY_ACTIVE_RUN_ERROR


def test_simplify_rbac_roles_migration_canonicalizes_active_account_and_job_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _simplify_rbac_roles_revision()
    executed: list[Any] = []

    class Operations:
        def execute(self, statement: Any) -> None:
            executed.append(statement)

    monkeypatch.setattr(revision, "op", Operations())
    monkeypatch.setattr(
        revision,
        "get_settings",
        lambda: SimpleNamespace(agno_app_schema="rbac_test"),
    )

    revision.upgrade()

    assert revision.down_revision == "20260725_0028"
    assert len(executed) == 4
    compiled = [
        str(statement.compile(dialect=postgresql.dialect())) for statement in executed
    ]
    sql = "\n".join(compiled)
    assert 'UPDATE "user"' in sql
    assert "UPDATE rbac_test.agent_eval_suite_runs" in sql
    assert "UPDATE rbac_test.agent_eval_case_runs" in sql
    assert "UPDATE rbac_test.durable_jobs" in sql
    assert all("jsonb_set" in statement for statement in compiled[1:])
    assert "jsonb_typeof" in sql
    assert "run_manifest,actor,role" in sql
    assert "run_manifest,actor,is_superuser" in sql
    assert "actor,role" in sql
    assert "is_superuser" in sql
    assert "'\"admin\"'::jsonb" in sql
    assert "'false'::jsonb" in sql
    assert "admin" in executed[0].compile(dialect=postgresql.dialect()).params.values()
    assert "knowledge_ingest" in str(executed[3].compile(dialect=postgresql.dialect()).params)


def test_user_auth_version_migration_canonicalizes_admin_state_and_adds_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _user_auth_versions_revision()
    added: list[tuple[str, Any]] = []
    executed: list[str] = []
    constraints: list[tuple[str, str, str]] = []
    dropped_constraints: list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []

    class Operations:
        def add_column(self, table: str, column: Any) -> None:
            added.append((table, column))

        def execute(self, statement: str) -> None:
            executed.append(statement)

        def create_check_constraint(self, name: str, table: str, condition: str) -> None:
            constraints.append((name, table, condition))

        def drop_constraint(self, name: str, table: str) -> None:
            dropped_constraints.append((name, table))

        def drop_column(self, table: str, column: str) -> None:
            removed.append((table, column))

    monkeypatch.setattr(revision, "op", Operations())

    revision.upgrade()

    assert revision.down_revision == "20260725_0029"
    assert [(table, column.name) for table, column in added] == [("user", "auth_version")]
    assert getattr(added[0][1], "nullable") is False
    assert "UPDATE \"user\"" in executed[0]
    assert "lower(trim(role)) = 'admin'" in executed[0]
    assert constraints == [
        ("ck_user_role", "user", "role IN ('admin', 'user')"),
        ("ck_user_role_matches_superuser", "user", "is_superuser = (role = 'admin')"),
        ("ck_user_auth_version", "user", "auth_version >= 1"),
    ]

    revision.downgrade()

    assert dropped_constraints == [
        ("ck_user_auth_version", "user"),
        ("ck_user_role_matches_superuser", "user"),
        ("ck_user_role", "user"),
    ]
    assert removed == [("user", "auth_version")]


class _RevisionConnection:
    def __init__(self, result: str | None | BaseException) -> None:
        self.result = result
        self.statements: list[str] = []

    async def scalar(self, statement: object) -> str | None:
        self.statements.append(str(statement))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _RevisionConnectionContext:
    def __init__(self, connection: _RevisionConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _RevisionConnection:
        return self.connection

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None


class _RevisionEngine:
    def __init__(self, result: str | None | BaseException) -> None:
        self.connection = _RevisionConnection(result)

    def connect(self) -> _RevisionConnectionContext:
        return _RevisionConnectionContext(self.connection)


def test_control_plane_metadata_contains_capability_and_owned_token_schema() -> None:
    settings = get_settings()
    metadata = control_plane_metadata()
    cve_source_settings = metadata.tables[
        f"{settings.agno_app_schema}.cve_source_settings"
    ]
    preferences = metadata.tables[
        f"{settings.agno_app_schema}.user_capability_preferences"
    ]
    servers = metadata.tables[f"{settings.agno_mcp_schema}.mcp_servers"]
    tokens = metadata.tables[f"{settings.agno_mcp_schema}.mcp_tokens"]

    assert list(preferences.primary_key.columns.keys()) == [
        "user_id",
        "capability_type",
        "capability_key",
    ]
    assert "default_enabled" not in servers.c
    custom_nodes = metadata.tables[
        f"{settings.agno_app_schema}.workflow_custom_nodes"
    ]
    assert list(custom_nodes.primary_key.columns.keys()) == ["id"]
    assert {"user_id", "name", "definition"}.issubset(custom_nodes.c.keys())
    assert {"token_hash", "owner_user_id", "token_kind"}.issubset(tokens.c.keys())
    assert "token" not in tokens.c
    assert list(cve_source_settings.primary_key.columns.keys()) == ["source"]
    assert {"enabled", "updated_at"}.issubset(cve_source_settings.c.keys())


@pytest.mark.asyncio
async def test_control_plane_current_revision_reads_alembic_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _RevisionEngine("20260720_0002")
    monkeypatch.setattr(migrations, "get_async_control_plane_engine", lambda: engine)

    assert await migrations.control_plane_current_revision() == "20260720_0002"
    assert engine.connection.statements == ["SELECT version_num FROM alembic_version"]


@pytest.mark.asyncio
async def test_control_plane_current_revision_returns_none_when_alembic_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _RevisionEngine(SQLAlchemyError("alembic_version does not exist"))
    monkeypatch.setattr(migrations, "get_async_control_plane_engine", lambda: engine)

    assert await migrations.control_plane_current_revision() is None


@pytest.mark.asyncio
async def test_assert_control_plane_schema_current_requires_exact_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations, "control_plane_head_revision", lambda: "expected")
    current = AsyncMock(return_value="expected")
    monkeypatch.setattr(migrations, "control_plane_current_revision", current)

    await migrations.assert_control_plane_schema_current()
    current.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_assert_control_plane_schema_current_fails_closed_for_missing_or_stale_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations, "control_plane_head_revision", lambda: "expected")

    for current in (None, "previous"):
        monkeypatch.setattr(
            migrations,
            "control_plane_current_revision",
            AsyncMock(return_value=current),
        )
        with pytest.raises(migrations.ControlPlaneSchemaOutdatedError) as error:
            await migrations.assert_control_plane_schema_current()

        assert f"database={current or 'none'}, expected=expected" in str(error.value)
        assert "uv run alembic upgrade head" in str(error.value)


@pytest.mark.asyncio
async def test_schema_current_check_is_serialized_and_cached_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked = AsyncMock()
    monkeypatch.setattr(migrations, "_schema_checked_once", AsyncOnce())
    monkeypatch.setattr(migrations, "assert_control_plane_schema_current", checked)

    await asyncio.gather(
        migrations.ensure_control_plane_schema_current(),
        migrations.ensure_control_plane_schema_current(),
    )

    checked.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_schema_current_check_retries_after_a_failed_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked = AsyncMock(
        side_effect=[
            migrations.ControlPlaneSchemaOutdatedError("migration required"),
            None,
        ]
    )
    monkeypatch.setattr(migrations, "_schema_checked_once", AsyncOnce())
    monkeypatch.setattr(migrations, "assert_control_plane_schema_current", checked)

    with pytest.raises(migrations.ControlPlaneSchemaOutdatedError):
        await migrations.ensure_control_plane_schema_current()
    await migrations.ensure_control_plane_schema_current()

    assert checked.await_count == 2


@pytest.mark.asyncio
async def test_schema_current_readiness_check_returns_false_for_outdated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migrations,
        "assert_control_plane_schema_current",
        AsyncMock(side_effect=migrations.ControlPlaneSchemaOutdatedError("stale")),
    )

    assert await migrations.control_plane_schema_is_current() is False
