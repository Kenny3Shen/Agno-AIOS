from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.engine import Connection as SqlAlchemyConnection

from api.tasks import rehearse_rbac_migration as rehearsal


def _args(**overrides: object) -> Namespace:
    values: dict[str, object] = {
        "apply": False,
        "backup_reference": None,
        "confirm_clone": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_rehearsal_url_helpers_do_not_expose_credentials() -> None:
    url = "postgresql://operator:very-secret@db.example.test:5432/tais?sslmode=require"

    assert rehearsal._sqlalchemy_url(url).startswith("postgresql+psycopg://")
    assert rehearsal._sqlalchemy_url(url.replace("postgresql://", "postgresql+psycopg_async://")).startswith(
        "postgresql+psycopg://"
    )
    assert rehearsal._redact_database_url(url) == "postgresql://db.example.test:5432/tais"


def test_rehearsal_apply_requires_backup_clone_confirmation_and_nonproduction_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(rehearsal.RbacMigrationRehearsalError, match="backup-reference"):
        rehearsal._validate_apply_args(_args(apply=True))

    with pytest.raises(rehearsal.RbacMigrationRehearsalError, match="confirm-clone"):
        rehearsal._validate_apply_args(_args(apply=True, backup_reference="snapshot-1"))

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(rehearsal.RbacMigrationRehearsalError, match="production environment"):
        rehearsal._validate_apply_args(
            _args(
                apply=True,
                backup_reference="snapshot-1",
                confirm_clone="I_UNDERSTAND_THIS_IS_A_CLONE",
            )
        )

    monkeypatch.setenv("ENVIRONMENT", "staging")
    rehearsal._validate_apply_args(
        _args(
            apply=True,
            backup_reference="snapshot-1",
            confirm_clone="I_UNDERSTAND_THIS_IS_A_CLONE",
        )
    )


def test_rehearsal_preflight_reports_account_snapshot_and_active_work_counts() -> None:
    values = iter(["20260725_0028", 1, 2, 3, 4, 5, 6, 7])

    class Connection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def scalar(self, statement):
            self.statements.append(str(statement))
            return next(values)

    connection = Connection()
    report = rehearsal.collect_preflight(
        cast(SqlAlchemyConnection, connection), app_schema="app"
    )

    assert report == {
        "database_revision": "20260725_0028",
        "accounts_requiring_role_canonicalization": 1,
        "accounts_requiring_superuser_alignment": 2,
        "suite_run_snapshots_requiring_canonicalization": 3,
        "case_run_provenance_requiring_canonicalization": 4,
        "knowledge_job_payloads_requiring_canonicalization": 5,
        "active_eval_runs": 6,
        "queued_or_leased_knowledge_jobs": 7,
    }
    sql = "\n".join(connection.statements)
    assert 'FROM "user"' in sql
    assert "app.agent_eval_suite_runs" in sql
    assert "app.durable_jobs" in sql
    assert "knowledge_ingest" in sql


def test_rehearsal_postflight_checks_head_and_account_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rehearsal,
        "collect_preflight",
        lambda _connection, *, app_schema: {"database_revision": "head"},
    )
    monkeypatch.setattr(rehearsal, "control_plane_head_revision", lambda: "head")

    class Connection:
        def scalar(self, _statement):
            return 0

    report = rehearsal.collect_postflight(
        cast(SqlAlchemyConnection, Connection()), app_schema="app"
    )

    assert report["accounts_violating_final_access_invariant"] == 0
    assert report["expected_head_revision"] == "head"
    assert report["schema_is_at_head"] is True


def test_rehearsal_main_uses_application_database_config_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class ConnectionContext:
        def __enter__(self):
            return object()

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

    class Engine:
        def connect(self):
            return ConnectionContext()

        def dispose(self) -> None:
            captured["disposed"] = True

    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(
        rehearsal,
        "get_settings",
        lambda: SimpleNamespace(
            postgres_sqlalchemy_url="postgresql+psycopg_async://operator:secret@db.example.test/tais"
        ),
    )
    monkeypatch.setattr(
        rehearsal,
        "create_engine",
        lambda url, **_kwargs: captured.setdefault("url", url) and Engine(),
    )
    monkeypatch.setattr(
        rehearsal,
        "collect_preflight",
        lambda _connection, *, app_schema: {"schema": app_schema},
    )

    result = rehearsal.main(
        Namespace(
            database_url=None,
            app_schema="app",
            apply=False,
            backup_reference=None,
            confirm_clone=None,
        )
    )

    assert captured["url"] == "postgresql+psycopg://operator:secret@db.example.test/tais"
    assert captured["disposed"] is True
    assert result["database"] == "postgresql+psycopg_async://db.example.test/tais"
    assert result["before"] == {"schema": "app"}
