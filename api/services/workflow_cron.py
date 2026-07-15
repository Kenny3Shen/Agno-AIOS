"""Cron trigger ticker for published workflows (PR7)."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from croniter import croniter
from loguru import logger

from api.persistence import workflows as workflow_store
from api.services.workflow_run_runtime import stream_workflow_run
from api.services.workflow_service import (
    _normalize_triggers,
    get_published_definition,
    mark_cron_last_run,
)


def _cron_due(expression: str, last_run_at: float, now: float) -> bool:
    expr = (expression or "").strip()
    if not expr:
        return False
    try:
        # Walk from last_run forward; due if next schedule is in the past.
        base = datetime.fromtimestamp(last_run_at or 0, tz=timezone.utc)
        itr = croniter(expr, base)
        nxt = itr.get_next(datetime)
        return nxt.timestamp() <= now + 0.5
    except (ValueError, KeyError, TypeError):
        logger.warning("Invalid cron expression: {!r}", expr)
        return False


async def tick_workflow_crons(*, limit: int = 200) -> int:
    """Fire due cron workflows once. Returns number started."""
    rows = await workflow_store.list_workflows_for_cron(limit=limit)
    now = time.time()
    started = 0
    for row in rows:
        workflow_id = str(row.get("id") or "")
        if not workflow_id:
            continue
        if not row.get("enabled", True):
            continue
        triggers = _normalize_triggers(row.get("triggers"))
        cron = triggers.get("cron") or {}
        if not cron.get("enabled"):
            continue
        expression = str(cron.get("expression") or "").strip()
        last_run_at = float(cron.get("last_run_at") or 0)
        if not _cron_due(expression, last_run_at, now):
            continue
        definition = get_published_definition(row)
        if definition is None:
            logger.debug("Skip cron {}: no published definition", workflow_id)
            continue
        owner = str(row.get("owner_user_id") or "system")
        run_id = str(uuid4())
        session_id = str(uuid4())
        # Mark first to avoid double-fire on slow runs / overlapping ticks.
        await mark_cron_last_run(workflow_id, now)
        started += 1
        asyncio.create_task(
            _run_cron_workflow(
                workflow_id=workflow_id,
                definition=definition,
                owner_user_id=owner,
                run_id=run_id,
                session_id=session_id,
            ),
            name=f"workflow-cron-{workflow_id}",
        )
    return started


async def _run_cron_workflow(
    *,
    workflow_id: str,
    definition: dict[str, Any],
    owner_user_id: str,
    run_id: str,
    session_id: str,
) -> None:
    try:
        async for event in stream_workflow_run(
            workflow_id=workflow_id,
            definition=definition,
            input_text="cron trigger",
            user_id=owner_user_id,
            session_id=session_id,
            model_id=None,
            run_id=run_id,
        ):
            # Drain stream; HITL pause is terminal for this fire.
            if event.event in {
                "workflow.completed",
                "workflow.failed",
                "workflow.cancelled",
                "workflow.paused",
            }:
                break
        logger.info(
            "Cron workflow {} finished run={} session={}",
            workflow_id,
            run_id,
            session_id,
        )
    except Exception:
        logger.exception("Cron workflow {} failed run={}", workflow_id, run_id)


_cron_task: asyncio.Task[None] | None = None


async def start_workflow_cron_scheduler(interval_sec: float = 30.0) -> None:
    global _cron_task
    if _cron_task is not None and not _cron_task.done():
        return

    async def _loop() -> None:
        logger.info("Workflow cron scheduler started (interval={}s)", interval_sec)
        while True:
            try:
                n = await tick_workflow_crons()
                if n:
                    logger.info("Workflow cron ticker started {} run(s)", n)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Workflow cron tick failed")
            await asyncio.sleep(interval_sec)

    _cron_task = asyncio.create_task(_loop(), name="workflow-cron-scheduler")


async def stop_workflow_cron_scheduler() -> None:
    global _cron_task
    task = _cron_task
    _cron_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Workflow cron scheduler stopped")
