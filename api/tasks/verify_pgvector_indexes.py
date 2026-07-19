"""Print a read-only PgVector schema/index verification report."""

from __future__ import annotations

import argparse
import asyncio
import json

from api.services.pgvector_index_verification import (
    PgVectorVerificationError,
    verify_pgvector_indexes_async,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the configured PgVector table and indexes without issuing DDL. "
            "Use --explain-sql only for an explicit representative read-only query."
        )
    )
    parser.add_argument(
        "--explain-sql",
        help=(
            "Single SELECT/WITH statement to wrap in EXPLAIN (FORMAT JSON), without ANALYZE. "
            "No plan is captured unless this flag is supplied."
        ),
    )
    return parser


async def main(*, explain_sql: str | None = None) -> dict[str, object]:
    report = await verify_pgvector_indexes_async(explain_sql=explain_sql)
    return report.as_dict()


def run() -> None:
    args = _parser().parse_args()
    try:
        report = asyncio.run(main(explain_sql=args.explain_sql))
    except PgVectorVerificationError as exc:
        raise SystemExit(f"PgVector verification input error: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    run()
