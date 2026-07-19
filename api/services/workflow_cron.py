"""Cron trigger ticker for published workflows."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from croniter import croniter
from loguru import logger

from api.persistence import workflows as workflow_store
from api.persistence.durable_jobs import JobKind
from api.services.audit_service import record_audit_event_async
from api.services.notification_service import notify_workflow_trigger_failure
from api.services.workflow_run_runtime import stream_workflow_run
from api.services.workflow_service import (
    _normalize_triggers,
    get_published_definition,
)


def next_cron_timestamp(
    expression: str,
    *,
    last_run_at: float = 0,
    now: float | None = None,
) -> float | None:
    """Return next fire unix seconds after max(now, last_run_at), or None if invalid/disabled expr."""
    expr = (expression or "").strip()
    if not expr:
        return None
    try:
        wall = float(now if now is not None else time.time())
        base_ts = max(float(last_run_at or 0), wall)
        base = datetime.fromtimestamp(base_ts, tz=timezone.utc)
        itr = croniter(expr, base)
        nxt = itr.get_next(datetime)
        return float(nxt.timestamp())
    except (ValueError, KeyError, TypeError):
        logger.warning("Invalid cron expression: {!r}", expr)
        return None


def _cron_due_timestamp(expression: str, last_run_at: float) -> float | None:
    """Return the first scheduled fire after ``last_run_at``.

    The timestamp is also the durable dispatch idempotency boundary.  It must
    be derived from the schedule, rather than from the wall clock of one API
    process, so competing scheduler instances construct the same job key.
    """
    expr = (expression or "").strip()
    if not expr:
        return None
    try:
        # Walk from last_run forward; due if next schedule is in the past.
        base = datetime.fromtimestamp(last_run_at or 0, tz=timezone.utc)
        itr = croniter(expr, base)
        nxt = itr.get_next(datetime)
        return float(nxt.timestamp())
    except (OverflowError, OSError, ValueError, KeyError, TypeError):
        logger.warning("Invalid cron expression: {!r}", expr)
        return None


def _cron_dispatch_key(workflow_id: str, scheduled_at: float) -> str:
    """Return one stable idempotency key for a workflow schedule occurrence."""
    return f"workflow-cron:{workflow_id}:{scheduled_at:.6f}"


def _system_actor(owner_user_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=owner_user_id or "system",
        email="system@workflow-cron",
        role="system",
        is_superuser=False,
    )


async def tick_workflow_crons(*, limit: int = 200) -> int:
    """Queue due cron workflows once. Returns the number durably dispatched."""
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
        scheduled_at = _cron_due_timestamp(expression, last_run_at)
        if scheduled_at is None or scheduled_at > now + 0.5:
            continue
        definition = get_published_definition(row)
        if definition is None:
            logger.debug("Skip cron {}: no published definition", workflow_id)
            continue
        # Keep the workflow CAS and durable insert in one transaction.  A
        # queue-write failure must leave this occurrence due for the next tick.
        claimed = await workflow_store.claim_cron_run_and_enqueue_job(
            workflow_id,
            expected_last_run_at=last_run_at,
            claim_ts=now,
            kind=JobKind.WORKFLOW_CRON_DISPATCH,
            payload={
                "workflow_id": workflow_id,
                "definition": definition,
                "owner_user_id": str(row.get("owner_user_id") or "system"),
                "run_id": str(uuid4()),
                "session_id": str(uuid4()),
                "expression": expression,
                "scheduled_at": scheduled_at,
            },
            idempotency_key=_cron_dispatch_key(workflow_id, scheduled_at),
        )
        if not claimed:
            logger.debug("Skip cron {}: lost lease claim", workflow_id)
            continue
        started += 1
    return started


async def _run_cron_workflow(
    *,
    workflow_id: str,
    definition: dict[str, Any],
    owner_user_id: str,
    run_id: str,
    session_id: str,
    expression: str = "",
) -> str:
    actor = _system_actor(owner_user_id)
    terminal = "error"
    try:
        await record_audit_event_async(
            actor=actor,
            action="workflow.trigger.cron",
            resource_type="workflow",
            resource_id=workflow_id,
            status="started",
            metadata={
                "run_id": run_id,
                "session_id": session_id,
                "expression": expression,
                "source": "cron",
            },
        )
        async for event in stream_workflow_run(
            workflow_id=workflow_id,
            definition=definition,
            input_text="cron trigger",
            user_id=owner_user_id,
            session_id=session_id,
            model_id=None,
            run_id=run_id,
        ):
            if event.event in {
                "workflow.completed",
                "workflow.failed",
                "workflow.cancelled",
                "workflow.paused",
            }:
                if event.event == "workflow.completed":
                    terminal = "success"
                elif event.event == "workflow.paused":
                    terminal = "paused"
                elif event.event == "workflow.cancelled":
                    terminal = "cancelled"
                else:
                    terminal = "error"
                break
        logger.info(
            "Cron workflow {} finished run={} session={} status={}",
            workflow_id,
            run_id,
            session_id,
            terminal,
        )
    except Exception:
        terminal = "error"
        logger.exception("Cron workflow {} failed run={}", workflow_id, run_id)
    finally:
        await record_audit_event_async(
            actor=actor,
            action="workflow.trigger.cron",
            resource_type="workflow",
            resource_id=workflow_id,
            status=terminal,
            metadata={
                "run_id": run_id,
                "session_id": session_id,
                "expression": expression,
                "source": "cron",
            },
        )
        if terminal == "error":
            await notify_workflow_trigger_failure(
                workflow_id=workflow_id,
                workflow_name=str((definition or {}).get("name") or workflow_id),
                owner_user_id=owner_user_id,
                source="cron",
                run_id=run_id,
                session_id=session_id,
                error="Cron workflow run failed",
            )
    return terminal


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
