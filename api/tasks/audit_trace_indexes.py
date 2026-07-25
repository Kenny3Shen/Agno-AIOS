"""Audit and explicitly govern the Agno trace-table performance indexes.

The default command is read-only.  It never creates, drops, or reindexes a
database object.  Operators can inspect actual representative plans with
``--explain`` and must deliberately provide both ``--apply`` and the exact
confirmation value before the two approved extension indexes are created.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import URL, create_engine, make_url
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from api.config import get_settings
from api.services.trace_index_governance import (
    TraceIndexGovernanceError,
    apply_trace_indexes,
    assert_trace_indexes_applyable,
    verify_trace_indexes,
)

_APPLY_CONFIRMATION = "CREATE_AGNO_TRACE_INDEXES"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Agno trace index/EXPLAIN audit. The command never issues DDL "
            "unless --apply and its exact confirmation are both supplied."
        ),
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL (defaults to the configured application database).",
    )
    parser.add_argument(
        "--schema",
        default=get_settings().agno_db_schema,
        help="Agno schema containing agno_traces (defaults to AGNO_DB_SCHEMA).",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "Capture bounded, read-only EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) evidence "
            "for representative Overview and ERROR trace queries."
        ),
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=15_000,
        help="Per read-only audit statement timeout (1000-60000; default: 15000).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Create only missing approved trace indexes. Uses CREATE INDEX CONCURRENTLY "
            "in autocommit mode; never part of Alembic."
        ),
    )
    parser.add_argument(
        "--confirm",
        help=(
            "Required with --apply. Enter the exact value "
            f"{_APPLY_CONFIRMATION!r} after reviewing the read-only report."
        ),
    )
    return parser


def _sqlalchemy_url(url: str) -> str:
    """Normalize configured URLs to the synchronous psycopg dialect for this CLI."""
    clean = url.strip()
    if clean.startswith("postgresql+psycopg_async://"):
        return clean.replace("postgresql+psycopg_async://", "postgresql+psycopg://", 1)
    if clean.startswith("postgresql://"):
        return clean.replace("postgresql://", "postgresql+psycopg://", 1)
    return clean


def _redact_database_url(url: str) -> str:
    """Keep credentials out of JSON reports and terminal history."""
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


def _validate_apply_args(args: argparse.Namespace) -> None:
    if args.apply and args.confirm != _APPLY_CONFIRMATION:
        raise TraceIndexGovernanceError(
            f"--apply requires --confirm {_APPLY_CONFIRMATION!r}."
        )
    if args.confirm and not args.apply:
        raise TraceIndexGovernanceError("--confirm is only meaningful with --apply.")


def _database_url(args: argparse.Namespace) -> str:
    configured = args.database_url or get_settings().postgres_sqlalchemy_url
    if not isinstance(configured, str) or not configured.strip():
        raise TraceIndexGovernanceError("Provide --database-url or configure PostgreSQL.")
    return configured.strip()


def _engine(database_url: str) -> Engine:
    # A CLI audit should not leave application-pool connections behind.
    return create_engine(_sqlalchemy_url(database_url), poolclass=NullPool, pool_pre_ping=True)


def main(args: argparse.Namespace) -> dict[str, object]:
    """Run the read-only preflight and optionally an explicitly confirmed apply."""
    _validate_apply_args(args)
    database_url = _database_url(args)
    schema = str(args.schema or "").strip()
    if not schema:
        raise TraceIndexGovernanceError("--schema cannot be blank.")
    engine = _engine(database_url)
    try:
        before = verify_trace_indexes(
            engine,
            schema=schema,
            explain=bool(args.explain),
            statement_timeout_ms=int(args.statement_timeout_ms),
        )
        result: dict[str, object] = {
            "database": _redact_database_url(database_url),
            "schema": schema,
            "applied": False,
            "before": before.as_dict(),
        }
        if args.apply:
            applied = apply_trace_indexes(
                engine,
                schema=schema,
                statement_timeout_ms=int(args.statement_timeout_ms),
            )
            after = verify_trace_indexes(
                engine,
                schema=schema,
                explain=False,
                statement_timeout_ms=int(args.statement_timeout_ms),
            )
            assert_trace_indexes_applyable(after)
            remaining = [check.name for check in after.checks if check.state == "missing"]
            if remaining:
                raise TraceIndexGovernanceError(
                    "Trace index postflight still reports missing indexes: " + ", ".join(remaining)
                )
            result.update(
                {
                    "applied": True,
                    "applied_indexes": list(applied),
                    "after": after.as_dict(),
                }
            )
        return result
    finally:
        engine.dispose()


def run() -> None:
    args = _parser().parse_args()
    try:
        report = main(args)
    except TraceIndexGovernanceError as exc:
        raise SystemExit(f"Trace index audit failed: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    run()
