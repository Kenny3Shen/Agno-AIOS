"""Cron trigger poller for published workflows.

Inspired by Agno ``SchedulePoller`` / ``agno.scheduler.cron``:

- poll-first loop with configurable interval
- cooperative stop with timeout
- stable schedule-derived idempotency keys
- claim advances ``last_run_at`` to the **scheduled** fire time so missed
  occurrences can catch up across ticks (not stuck on wall-clock claim time)
- cron expression validation via ``croniter.is_valid``
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from croniter import croniter
from loguru import logger

from api.config import get_settings
from api.persistence import workflows as workflow_store
from api.persistence.durable_jobs import JobKind
from api.services.audit_service import record_audit_event_async
from api.services.notification_service import notify_workflow_trigger_failure
from api.services.workflow_run_runtime import stream_workflow_run
from api.services.workflow_service import (
    _normalize_triggers,
    get_published_definition,
)

# Align with Agno SchedulePoller defaults when callers omit overrides.
_DEFAULT_POLL_INTERVAL_SEC = 15.0
_DEFAULT_STOP_TIMEOUT_SEC = 30.0
# Small grace so clock skew / tick latency does not skip a just-due fire.
_DUE_GRACE_SEC = 0.5


def validate_cron_expression(expression: str) -> bool:
    """Return True if *expression* is a valid 5-field cron string (Agno-style)."""
    expr = (expression or "").strip()
    if not expr:
        return False
    try:
        return bool(croniter.is_valid(expr))
    except Exception:  # noqa: BLE001 — treat unparseable as invalid
        return False


def next_cron_timestamp(
    expression: str,
    *,
    last_run_at: float = 0,
    now: float | None = None,
) -> float | None:
    """Return next fire unix seconds after max(now, last_run_at), or None if invalid.

    Used for UI projection (``next_cron_at``). Includes a light monotonicity
    guard so the displayed next fire is not in the past.
    """
    expr = (expression or "").strip()
    if not expr or not validate_cron_expression(expr):
        if expr:
            logger.warning("Invalid cron expression: {!r}", expr)
        return None
    try:
        wall = float(now if now is not None else time.time())
        base_ts = max(float(last_run_at or 0), wall)
        base = datetime.fromtimestamp(base_ts, tz=timezone.utc)
        itr = croniter(expr, base)
        nxt = itr.get_next(datetime)
        computed = float(nxt.timestamp())
        # Agno compute_next_run: never advertise a past fire.
        minimum = wall + 1.0
        return max(computed, minimum)
    except (OverflowError, OSError, ValueError, KeyError, TypeError):
        logger.warning("Invalid cron expression: {!r}", expr)
        return None


def _cron_due_timestamp(expression: str, last_run_at: float) -> float | None:
    """Return the first scheduled fire after ``last_run_at``.

    The timestamp is the durable dispatch idempotency boundary.  It must be
    derived from the schedule (not wall clock) so competing scheduler instances
    construct the same job key.
    """
    expr = (expression or "").strip()
    if not expr or not validate_cron_expression(expr):
        if expr:
            logger.warning("Invalid cron expression: {!r}", expr)
        return None
    try:
        base = datetime.fromtimestamp(float(last_run_at or 0), tz=timezone.utc)
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


async def tick_workflow_crons(
    *,
    limit: int | None = None,
    catchup_max: int | None = None,
    now: float | None = None,
) -> int:
    """Queue due cron workflows. Returns the number of durable dispatches enqueued.

    When a workflow has multiple overdue fires (API was down, poll interval
    longer than schedule), up to ``catchup_max`` occurrences are claimed per
    workflow in this tick.  ``last_run_at`` advances to each **scheduled** time
    so the next occurrence remains discoverable.
    """
    settings = get_settings()
    scan_limit = (
        int(limit)
        if limit is not None
        else int(settings.workflow_cron_tick_limit)
    )
    max_catchup = (
        int(catchup_max)
        if catchup_max is not None
        else int(settings.workflow_cron_catchup_max)
    )
    wall = float(now if now is not None else time.time())
    rows = await workflow_store.list_workflows_for_cron(limit=scan_limit)
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
        if not validate_cron_expression(expression):
            logger.warning(
                "Skip cron {}: invalid expression {!r}",
                workflow_id,
                expression,
            )
            continue
        definition = get_published_definition(row)
        if definition is None:
            logger.debug("Skip cron {}: no published definition", workflow_id)
            continue

        last_run_at = float(cron.get("last_run_at") or 0)
        owner_user_id = str(row.get("owner_user_id") or "system")
        enqueued_for_wf = 0

        # Catch-up loop: claim consecutive overdue fires (AgentOS-style due scan).
        while enqueued_for_wf < max_catchup:
            scheduled_at = _cron_due_timestamp(expression, last_run_at)
            if scheduled_at is None or scheduled_at > wall + _DUE_GRACE_SEC:
                break
            # Keep the workflow CAS and durable insert in one transaction.
            # Queue-write failure must leave this occurrence due for next tick.
            # Advance last_run_at to *scheduled_at* (not wall clock) so the next
            # schedule slot remains the natural successor for catch-up.
            claimed = await workflow_store.claim_cron_run_and_enqueue_job(
                workflow_id,
                expected_last_run_at=last_run_at,
                claim_ts=scheduled_at,
                kind=JobKind.WORKFLOW_CRON_DISPATCH,
                payload={
                    "workflow_id": workflow_id,
                    "definition": definition,
                    "owner_user_id": owner_user_id,
                    "run_id": str(uuid4()),
                    "session_id": str(uuid4()),
                    "expression": expression,
                    "scheduled_at": scheduled_at,
                },
                idempotency_key=_cron_dispatch_key(workflow_id, scheduled_at),
            )
            if not claimed:
                logger.debug("Skip cron {}: lost lease claim", workflow_id)
                break
            started += 1
            enqueued_for_wf += 1
            last_run_at = scheduled_at

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


class WorkflowCronPoller:
    """In-process due-scan loop for workflow cron triggers.

    Mirrors Agno ``SchedulePoller`` lifecycle (start/stop, poll-first, worker id)
    while dispatching through our durable job queue rather than HTTP endpoints.
    """

    def __init__(
        self,
        *,
        poll_interval: float | None = None,
        stop_timeout: float = _DEFAULT_STOP_TIMEOUT_SEC,
        worker_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self.poll_interval = float(
            poll_interval
            if poll_interval is not None
            else settings.workflow_cron_poll_interval_sec
        )
        self.stop_timeout = float(stop_timeout)
        self.worker_id = worker_id or f"workflow-cron-{uuid4().hex[:8]}"
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._running and self._task is not None and not self._task.done():
            return
        if not get_settings().workflow_cron_enabled:
            logger.info(
                "Workflow cron poller disabled (TAIS_WORKFLOW_CRON_ENABLED=false)"
            )
            return
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name="workflow-cron-scheduler",
        )
        logger.info(
            "Workflow cron poller started (worker={}, interval={}s)",
            self.worker_id,
            self.poll_interval,
        )

    async def stop(self) -> None:
        """Stop the poll loop (AgentOS SchedulePoller-style graceful cancel)."""
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=self.stop_timeout)
        except (asyncio.CancelledError, TimeoutError, asyncio.TimeoutError):
            pass
        logger.info("Workflow cron poller stopped (worker={})", self.worker_id)

    async def _poll_loop(self) -> None:
        """Main loop: poll first, then sleep (Agno SchedulePoller)."""
        while self._running:
            try:
                n = await tick_workflow_crons()
                if n:
                    logger.info(
                        "Workflow cron poller ({}) enqueued {} dispatch(es)",
                        self.worker_id,
                        n,
                    )
                if not self._running:
                    break
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Workflow cron poll failed (worker={})", self.worker_id
                )
                await asyncio.sleep(self.poll_interval)


_poller: WorkflowCronPoller | None = None


async def start_workflow_cron_scheduler(
    interval_sec: float | None = None,
) -> None:
    """Start the process-global workflow cron poller (idempotent)."""
    global _poller
    if _poller is not None and _poller.running:
        return
    _poller = WorkflowCronPoller(
        poll_interval=(
            interval_sec
            if interval_sec is not None
            else get_settings().workflow_cron_poll_interval_sec
        )
        or _DEFAULT_POLL_INTERVAL_SEC
    )
    await _poller.start()


async def stop_workflow_cron_scheduler() -> None:
    global _poller
    poller = _poller
    _poller = None
    if poller is None:
        return
    await poller.stop()
