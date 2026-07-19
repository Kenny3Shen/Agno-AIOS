from __future__ import annotations

import argparse
import asyncio
from typing import Any, cast

from loguru import logger

from api.persistence.audit_logs import (
    failed_chat_run_ids_async,
    repair_failed_chat_trace_statuses_async,
)
from api.services.postgres_store import coerce_json_value, get_async_agno_postgres_db


async def _session_error_run_ids() -> set[str]:
    db = get_async_agno_postgres_db()
    page = 1
    result: set[str] = set()
    while True:
        rows, total = cast(
            tuple[list[dict[str, Any]], int],
            await db.get_sessions(limit=200, page=page, deserialize=False),
        )
        for row in rows:
            runs = coerce_json_value(row.get("runs"))
            if not isinstance(runs, list):
                continue
            for run in runs:
                if not isinstance(run, dict):
                    continue
                if str(run.get("status") or "").upper() not in {"ERROR", "FAILED", "FAILURE"}:
                    continue
                run_id = str(run.get("run_id") or "").strip()
                if run_id:
                    result.add(run_id)
        if page * 200 >= total or not rows:
            break
        page += 1
    return result


async def repair_trace_statuses(*, apply: bool) -> dict[str, Any]:
    db = get_async_agno_postgres_db()
    traces_table = await db._get_table(  # noqa: SLF001 - Agno exposes no public table accessor.
        table_type="traces", create_table_if_not_found=True
    )
    if traces_table is None:
        raise RuntimeError("Agno traces table is unavailable")
    report: dict[str, Any] = await repair_failed_chat_trace_statuses_async(
        traces_table,
        apply=apply,
    )
    session_error_ids = await _session_error_run_ids()
    audited_error_ids: set[str] = set()
    ordered_session_error_ids = sorted(session_error_ids)
    for offset in range(0, len(ordered_session_error_ids), 1000):
        batch = set(ordered_session_error_ids[offset : offset + 1000])
        audited_error_ids.update(await failed_chat_run_ids_async(batch))
    missing_audit_ids = sorted(session_error_ids - audited_error_ids)
    report["session_error_runs"] = len(session_error_ids)
    report["session_errors_without_audit"] = len(missing_audit_ids)
    report["session_errors_without_audit_sample"] = missing_audit_ids[:20]
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile failed chat audit terminals into Agno Trace status."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Without this flag the command is a dry run.",
    )
    return parser


async def main(*, apply: bool) -> None:
    report = await repair_trace_statuses(apply=apply)
    logger.info("Trace status repair mode={}: {}", "apply" if apply else "dry-run", report)


def run() -> None:
    args = _parser().parse_args()
    asyncio.run(main(apply=args.apply))


if __name__ == "__main__":
    run()
