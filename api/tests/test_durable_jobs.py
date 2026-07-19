from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from api.persistence import durable_jobs
from api.persistence.durable_jobs import DurableJob, JobKind, JobLeaseLostError, JobState
from api.services.durable_job_handlers import build_durable_job_registry
from api.services.durable_job_service import (
    DurableJobRegistry,
    DurableJobWorker,
    DurableJobWorkerOptions,
    JobExecutionContext,
    NonRetryableJobError,
)
from api.tasks import job_worker
from api.tasks.job_worker import load_handler_registry


def _job(
    *,
    job_id: str = "job-1",
    kind: JobKind = JobKind.WORKFLOW_RESUME,
    attempt_count: int = 1,
) -> DurableJob:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    return DurableJob(
        id=job_id,
        kind=kind,
        payload={"approval_id": "approval-1"},
        idempotency_key=f"key:{job_id}",
        state=JobState.RUNNING,
        priority=0,
        attempt_count=attempt_count,
        max_attempts=3,
        available_at=now,
        lease_owner="worker-1",
        lease_expires_at=now + timedelta(minutes=1),
        heartbeat_at=now,
        last_error=None,
        result=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=None,
    )


class FakeStore:
    def __init__(self, claimed: list[DurableJob]) -> None:
        self.claimed = claimed
        self.claim_calls: list[dict[str, Any]] = []
        self.completed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []
        self.released: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.complete_error: Exception | None = None

    async def claim_due_jobs(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: float,
        retry_base_seconds: float,
        retry_max_seconds: float,
    ) -> list[DurableJob]:
        self.claim_calls.append(
            {
                "worker_id": worker_id,
                "limit": limit,
                "lease_seconds": lease_seconds,
                "retry_base_seconds": retry_base_seconds,
                "retry_max_seconds": retry_max_seconds,
            }
        )
        return list(self.claimed)

    async def heartbeat_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> DurableJob:
        self.heartbeats.append(
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "lease_seconds": lease_seconds,
            }
        )
        return _job(job_id=job_id)

    async def complete_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        result: Mapping[str, Any] | None,
    ) -> DurableJob:
        if self.complete_error is not None:
            raise self.complete_error
        self.completed.append(
            {"job_id": job_id, "worker_id": worker_id, "result": result}
        )
        return replace(_job(job_id=job_id), state=JobState.SUCCEEDED)

    async def fail_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        error: BaseException | str,
        retryable: bool,
        retry_base_seconds: float,
        retry_max_seconds: float,
    ) -> DurableJob:
        self.failed.append(
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "error": str(error),
                "retryable": retryable,
                "retry_base_seconds": retry_base_seconds,
                "retry_max_seconds": retry_max_seconds,
            }
        )
        return replace(
            _job(job_id=job_id),
            state=JobState.QUEUED if retryable else JobState.FAILED,
        )

    async def release_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        reason: BaseException | str,
        retry_base_seconds: float,
        retry_max_seconds: float,
    ) -> DurableJob:
        self.released.append(
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "reason": str(reason),
            }
        )
        return replace(_job(job_id=job_id), state=JobState.QUEUED)


def _worker(
    registry: DurableJobRegistry,
    store: FakeStore,
    *,
    concurrency: int = 2,
) -> DurableJobWorker:
    return DurableJobWorker(
        registry=registry,
        worker_id="worker-1",
        options=DurableJobWorkerOptions(concurrency=concurrency),
        store=store,
    )


def test_durable_job_table_has_typed_state_idempotency_and_worker_indexes() -> None:
    table = durable_jobs.durable_jobs_table()

    assert set(table.c.keys()) >= {
        "id",
        "kind",
        "payload",
        "idempotency_key",
        "state",
        "attempt_count",
        "max_attempts",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "result",
    }
    unique = [item for item in table.constraints if isinstance(item, UniqueConstraint)]
    assert any(
        item.name == "uq_durable_jobs_kind_key"
        and [column.name for column in item.columns] == ["kind", "idempotency_key"]
        for item in unique
    )
    assert {index.name for index in table.indexes} >= {
        "idx_durable_jobs_claim",
        "idx_durable_jobs_lease",
    }


def test_claim_and_lease_recovery_queries_use_skip_locked() -> None:
    table = durable_jobs.durable_jobs_table()
    now = datetime(2026, 7, 20, tzinfo=UTC)

    claim_sql = str(
        durable_jobs._claim_due_statement(table, now=now, limit=4).compile(  # noqa: SLF001
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    recover_sql = str(
        durable_jobs._expired_lease_statement(table, now=now, limit=4).compile(  # noqa: SLF001
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "FOR UPDATE SKIP LOCKED" in claim_sql
    assert "FOR UPDATE SKIP LOCKED" in recover_sql
    assert "attempt_count <" in claim_sql
    assert "max_attempts" in claim_sql
    assert "lease_expires_at" in recover_sql


@pytest.mark.parametrize(
    ("attempt_count", "expected"),
    [(0, 5.0), (1, 5.0), (2, 10.0), (7, 300.0)],
)
def test_retry_backoff_is_capped_and_deterministic(
    attempt_count: int, expected: float
) -> None:
    assert durable_jobs.retry_delay_seconds(attempt_count) == expected


@pytest.mark.asyncio
async def test_worker_completes_claimed_job_and_passes_result() -> None:
    registry = DurableJobRegistry()

    async def handler(job: DurableJob, _context: object) -> dict[str, str]:
        return {"handled": job.id}

    registry.register(JobKind.WORKFLOW_RESUME, handler)
    store = FakeStore([_job()])

    claimed = await _worker(registry, store).run_once()

    assert claimed == 1
    assert store.claim_calls == [
        {
            "worker_id": "worker-1",
            "limit": 2,
            "lease_seconds": 60.0,
            "retry_base_seconds": 5.0,
            "retry_max_seconds": 300.0,
        }
    ]
    assert store.completed == [
        {"job_id": "job-1", "worker_id": "worker-1", "result": {"handled": "job-1"}}
    ]
    assert store.failed == []


@pytest.mark.asyncio
async def test_worker_marks_missing_handler_terminal_without_retry() -> None:
    store = FakeStore([_job(kind=JobKind.KNOWLEDGE_INGEST)])

    await _worker(DurableJobRegistry(), store).run_once()

    assert store.completed == []
    assert len(store.failed) == 1
    assert store.failed[0]["retryable"] is False
    assert "No durable-job handler" in store.failed[0]["error"]


@pytest.mark.asyncio
async def test_worker_retries_unexpected_handler_exception() -> None:
    registry = DurableJobRegistry()

    async def failing_handler(_job: DurableJob, _context: object) -> None:
        raise RuntimeError("temporary provider failure")

    registry.register(JobKind.WORKFLOW_RESUME, failing_handler)
    store = FakeStore([_job()])

    await _worker(registry, store).run_once()

    assert len(store.failed) == 1
    assert store.failed[0]["retryable"] is True
    assert store.failed[0]["error"] == "temporary provider failure"


@pytest.mark.asyncio
async def test_worker_does_not_overwrite_a_lost_lease() -> None:
    registry = DurableJobRegistry()

    async def handler(_job: DurableJob, _context: object) -> dict[str, bool]:
        return {"ok": True}

    registry.register(JobKind.WORKFLOW_RESUME, handler)
    store = FakeStore([_job()])
    store.complete_error = JobLeaseLostError("claimed elsewhere")

    await _worker(registry, store).run_once()

    assert store.completed == []
    assert store.failed == []


@pytest.mark.asyncio
async def test_builtin_security_hitl_handler_continues_run_directly() -> None:
    registry = build_durable_job_registry()
    job = _job(kind=JobKind.SECURITY_HITL_RESUME)

    with patch(
        "api.services.security_run_runtime.execute_security_hitl_resume",
        new=AsyncMock(return_value="COMPLETED"),
    ) as resume, patch(
        "api.services.security_run_runtime.resume_security_run",
        new=AsyncMock(),
    ) as schedule:
        result = await registry.handler_for(JobKind.SECURITY_HITL_RESUME)(
            job,
            cast(JobExecutionContext, object()),
        )

    resume.assert_awaited_once_with("approval-1")
    schedule.assert_not_awaited()
    assert result == {"approval_id": "approval-1", "run_status": "COMPLETED"}


@pytest.mark.asyncio
async def test_builtin_security_hitl_handler_makes_failed_continuation_terminal() -> None:
    registry = build_durable_job_registry()
    job = _job(kind=JobKind.SECURITY_HITL_RESUME)

    with (
        patch(
            "api.services.security_run_runtime.execute_security_hitl_resume",
            new=AsyncMock(return_value="ERROR"),
        ) as resume,
        pytest.raises(NonRetryableJobError, match="did not complete"),
    ):
        await registry.handler_for(JobKind.SECURITY_HITL_RESUME)(
            job,
            cast(JobExecutionContext, object()),
        )

    resume.assert_awaited_once_with("approval-1")


@pytest.mark.asyncio
async def test_worker_records_security_hitl_failure_without_automatic_retry() -> None:
    registry = build_durable_job_registry()
    store = FakeStore([_job(kind=JobKind.SECURITY_HITL_RESUME)])

    with patch(
        "api.services.security_run_runtime.execute_security_hitl_resume",
        new=AsyncMock(return_value="ERROR"),
    ):
        await _worker(registry, store).run_once()

    assert len(store.failed) == 1
    assert store.failed[0]["job_id"] == "job-1"
    assert store.failed[0]["retryable"] is False
    assert "Security HITL continuation did not complete" in store.failed[0]["error"]


@pytest.mark.asyncio
async def test_builtin_cron_handler_runs_serialized_dispatch() -> None:
    registry = build_durable_job_registry()
    job = replace(
        _job(kind=JobKind.WORKFLOW_CRON_DISPATCH),
        payload={
            "workflow_id": "workflow-1",
            "definition": {"name": "Scheduled workflow", "steps": []},
            "owner_user_id": "owner-1",
            "run_id": "run-1",
            "session_id": "session-1",
            "expression": "*/5 * * * *",
            "scheduled_at": 1_767_281_100.0,
        },
    )
    with patch(
        "api.services.workflow_cron._run_cron_workflow",
        new=AsyncMock(return_value="success"),
    ) as run_cron:
        result = await registry.handler_for(JobKind.WORKFLOW_CRON_DISPATCH)(
            job,
            cast(JobExecutionContext, object()),
        )

    run_cron.assert_awaited_once_with(
        workflow_id="workflow-1",
        definition={"name": "Scheduled workflow", "steps": []},
        owner_user_id="owner-1",
        run_id="run-1",
        session_id="session-1",
        expression="*/5 * * * *",
    )
    assert result == {
        "workflow_id": "workflow-1",
        "run_id": "run-1",
        "session_id": "session-1",
        "scheduled_at": 1_767_281_100.0,
        "terminal_status": "success",
    }


@pytest.mark.asyncio
async def test_builtin_cron_handler_rejects_invalid_payload_without_execution() -> None:
    registry = build_durable_job_registry()
    job = replace(_job(kind=JobKind.WORKFLOW_CRON_DISPATCH), payload={})

    with pytest.raises(NonRetryableJobError, match="definition object"):
        await registry.handler_for(JobKind.WORKFLOW_CRON_DISPATCH)(
            job,
            cast(JobExecutionContext, object()),
        )


def test_builtin_worker_registry_registers_safe_builtin_handlers() -> None:
    registry = build_durable_job_registry()

    assert {
        JobKind.WORKFLOW_RESUME,
        JobKind.SECURITY_HITL_RESUME,
        JobKind.WORKFLOW_CRON_DISPATCH,
    } <= registry.kinds


def test_worker_cli_loads_trusted_handler_factory() -> None:
    registry = load_handler_registry(
        "api.services.durable_job_handlers:build_durable_job_registry"
    )

    assert {
        JobKind.WORKFLOW_RESUME,
        JobKind.SECURITY_HITL_RESUME,
        JobKind.WORKFLOW_CRON_DISPATCH,
    } <= registry.kinds


@pytest.mark.asyncio
async def test_worker_checks_control_plane_revision_before_claiming_jobs() -> None:
    registry = DurableJobRegistry()

    class StubWorker:
        async def run_once(self) -> int:
            return 0

    args = Namespace(
        worker_id=None,
        concurrency=1,
        lease_seconds=60.0,
        poll_interval_seconds=1.0,
        retry_base_seconds=5.0,
        retry_max_seconds=300.0,
        handler_factory="trusted:factory",
        once=True,
    )
    with (
        patch(
            "api.tasks.job_worker.ensure_control_plane_schema_current",
            new=AsyncMock(),
        ) as schema_check,
        patch("api.tasks.job_worker.load_handler_registry", return_value=registry),
        patch("api.tasks.job_worker.DurableJobWorker", return_value=StubWorker()),
    ):
        assert await job_worker.main(args) == 0

    schema_check.assert_awaited_once_with()
