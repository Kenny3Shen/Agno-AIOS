"""Run a guarded PostgreSQL rehearsal for the RBAC migrations.

This command is deliberately for a disposable or restored pre-production
clone.  It reports the exact rows that the RBAC migrations will touch, applies
the current Alembic head only with explicit confirmation, and verifies the
post-migration account and durable-work invariants.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.engine import Connection

from api.config import get_settings
from api.persistence.migrations import control_plane_head_revision

_CLONE_CONFIRMATION = "I_UNDERSTAND_THIS_IS_A_CLONE"
_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})


class RbacMigrationRehearsalError(ValueError):
    """Raised for unsafe or incomplete rehearsal inputs."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight and rehearse the RBAC Alembic migrations on a PostgreSQL clone.",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL for the disposable clone (defaults to POSTGRES_URL).",
    )
    parser.add_argument(
        "--app-schema",
        default=get_settings().agno_app_schema,
        help="Control-plane application schema to inspect.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply Alembic head after the read-only preflight.",
    )
    parser.add_argument(
        "--backup-reference",
        help="Required with --apply; operator reference to the verified clone backup.",
    )
    parser.add_argument(
        "--confirm-clone",
        help=f"Required with --apply; enter {_CLONE_CONFIRMATION!r}.",
    )
    return parser


def _sqlalchemy_url(url: str) -> str:
    clean = url.strip()
    if clean.startswith("postgresql+psycopg_async://"):
        return clean.replace("postgresql+psycopg_async://", "postgresql+psycopg://", 1)
    if clean.startswith("postgresql://"):
        return clean.replace("postgresql://", "postgresql+psycopg://", 1)
    return clean


def _redact_database_url(url: str) -> str:
    try:
        parsed = make_url(url.strip())
    except Exception:
        return "<configured database>"
    return str(
        URL.create(
            drivername=parsed.drivername,
            host=parsed.host or "<unknown-host>",
            port=parsed.port,
            database=parsed.database,
        )
    )


def _quoted_identifier(value: str) -> str:
    return dialect().identifier_preparer.quote(value)


def _actor_needs_canonicalization(
    column: str,
    *,
    actor_path: str,
    role_path: str,
    superuser_path: str,
) -> str:
    role = f"{column} #>> '{role_path}'"
    superuser = f"{column} #> '{superuser_path}'"
    actor = f"{column} #> '{actor_path}'"
    normalized_role = f"lower(trim({role}))"
    return f"""
        jsonb_typeof({actor}) = 'object'
        AND (
            {role} IS NULL
            OR {normalized_role} NOT IN ('admin', 'user')
            OR {role} <> {normalized_role}
            OR ({superuser} = 'true'::jsonb AND {role} <> 'admin')
            OR {superuser} IS NULL
            OR {superuser} NOT IN ('true'::jsonb, 'false'::jsonb)
        )
    """


def _scalar(connection: Connection, statement: str) -> int:
    return int(connection.scalar(text(statement)) or 0)


def collect_preflight(connection: Connection, *, app_schema: str) -> dict[str, object]:
    """Collect only counts; no rehearsal query reads sensitive job payloads."""
    schema = _quoted_identifier(app_schema)
    suite_actor = _actor_needs_canonicalization(
        "execution_snapshot",
        actor_path="{run_manifest,actor}",
        role_path="{run_manifest,actor,role}",
        superuser_path="{run_manifest,actor,is_superuser}",
    )
    case_actor = _actor_needs_canonicalization(
        "execution_provenance",
        actor_path="{actor}",
        role_path="{actor,role}",
        superuser_path="{actor,is_superuser}",
    )
    revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    return {
        "database_revision": str(revision) if revision is not None else None,
        "accounts_requiring_role_canonicalization": _scalar(
            connection,
            """
            SELECT count(*) FROM "user"
            WHERE role IS DISTINCT FROM CASE
                WHEN is_superuser IS TRUE OR lower(trim(role)) = 'admin' THEN 'admin'
                ELSE 'user'
            END
            """,
        ),
        "accounts_requiring_superuser_alignment": _scalar(
            connection,
            """
            SELECT count(*) FROM "user"
            WHERE is_superuser IS DISTINCT FROM (lower(trim(role)) = 'admin')
            """,
        ),
        "suite_run_snapshots_requiring_canonicalization": _scalar(
            connection,
            f"SELECT count(*) FROM {schema}.agent_eval_suite_runs WHERE {suite_actor}",
        ),
        "case_run_provenance_requiring_canonicalization": _scalar(
            connection,
            f"SELECT count(*) FROM {schema}.agent_eval_case_runs WHERE {case_actor}",
        ),
        "knowledge_job_payloads_requiring_canonicalization": _scalar(
            connection,
            f"""
            SELECT count(*) FROM {schema}.durable_jobs
            WHERE kind = 'knowledge_ingest' AND {case_actor.replace('execution_provenance', 'payload')}
            """,
        ),
        "active_eval_runs": _scalar(
            connection,
            f"""
            SELECT count(*) FROM {schema}.agent_eval_suite_runs
            WHERE status IN ('queued', 'running', 'cancelling')
            """,
        ),
        "queued_or_leased_knowledge_jobs": _scalar(
            connection,
            f"""
            SELECT count(*) FROM {schema}.durable_jobs
            WHERE kind = 'knowledge_ingest' AND state IN ('queued', 'running')
            """,
        ),
    }


def collect_postflight(connection: Connection, *, app_schema: str) -> dict[str, object]:
    report = collect_preflight(connection, app_schema=app_schema)
    report["accounts_violating_final_access_invariant"] = _scalar(
        connection,
        """
        SELECT count(*) FROM "user"
        WHERE role NOT IN ('admin', 'user')
            OR is_superuser IS DISTINCT FROM (role = 'admin')
            OR auth_version < 1
        """,
    )
    report["expected_head_revision"] = control_plane_head_revision()
    report["schema_is_at_head"] = report["database_revision"] == report["expected_head_revision"]
    return report


def _validate_apply_args(args: argparse.Namespace) -> None:
    if not args.apply:
        return
    if os.getenv("ENVIRONMENT", "").strip().lower() in _PRODUCTION_ENVIRONMENTS:
        raise RbacMigrationRehearsalError(
            "Refusing --apply in a production environment; use a restored clone."
        )
    if not args.backup_reference:
        raise RbacMigrationRehearsalError("--apply requires --backup-reference.")
    if args.confirm_clone != _CLONE_CONFIRMATION:
        raise RbacMigrationRehearsalError(
            f"--apply requires --confirm-clone {_CLONE_CONFIRMATION!r}."
        )


def _apply_head(database_url: str) -> None:
    environment = os.environ.copy()
    environment["POSTGRES_URL"] = database_url
    environment["TAIS_POSTGRES_SQLALCHEMY_URL"] = _sqlalchemy_url(database_url)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def main(args: argparse.Namespace) -> dict[str, object]:
    database_url = (
        args.database_url or os.getenv("POSTGRES_URL") or get_settings().postgres_sqlalchemy_url
    ).strip()
    if not database_url:
        raise RbacMigrationRehearsalError("Provide --database-url or POSTGRES_URL.")
    _validate_apply_args(args)
    engine = create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            before = collect_preflight(connection, app_schema=args.app_schema)
        result: dict[str, object] = {
            "database": _redact_database_url(database_url),
            "app_schema": args.app_schema,
            "before": before,
            "applied": bool(args.apply),
        }
        if args.apply:
            _apply_head(database_url)
            with engine.connect() as connection:
                after = collect_postflight(connection, app_schema=args.app_schema)
            result["backup_reference"] = args.backup_reference
            result["after"] = after
            if not after["schema_is_at_head"]:
                raise RbacMigrationRehearsalError("Alembic did not reach the expected head revision.")
            if after["accounts_violating_final_access_invariant"] != 0:
                raise RbacMigrationRehearsalError("Postflight account invariant check failed.")
            for key in (
                "accounts_requiring_role_canonicalization",
                "suite_run_snapshots_requiring_canonicalization",
                "case_run_provenance_requiring_canonicalization",
                "knowledge_job_payloads_requiring_canonicalization",
            ):
                if after[key] != 0:
                    raise RbacMigrationRehearsalError(f"Postflight check failed: {key} remains nonzero.")
        return result
    finally:
        engine.dispose()


def run() -> None:
    args = _parser().parse_args()
    try:
        result = main(args)
    except (RbacMigrationRehearsalError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"RBAC migration rehearsal failed: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    run()
