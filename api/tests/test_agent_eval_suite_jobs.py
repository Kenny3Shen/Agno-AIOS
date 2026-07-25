from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from api.persistence.durable_jobs import DurableJob, JobKind, JobState
from api.services.agent_eval_suite_jobs import (
    EvalSuiteRunJobPayload,
    build_eval_suite_run_payload,
    handle_eval_suite_run_job,
    parse_eval_suite_run_payload,
    register_eval_suite_run_job_handler,
    run_queued_suite_run,
)
from api.services.durable_job_service import (
    DurableJobRegistry,
    JobExecutionContext,
    NonRetryableJobError,
)


def _payload() -> dict[str, str]:
    return build_eval_suite_run_payload(suite_run_id="suite-run-1")


def _job(payload: Mapping[str, object]) -> DurableJob:
    now = datetime.now(UTC)
    return DurableJob(
        id="job-1",
        kind=JobKind.EVAL_SUITE_RUN,
        payload=dict(payload),
        idempotency_key="eval-suite-run:suite-run-1",
        state=JobState.RUNNING,
        priority=10,
        attempt_count=1,
        max_attempts=3,
        available_at=now,
        lease_owner="worker-1",
        lease_expires_at=now,
        heartbeat_at=now,
        last_error=None,
        result=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=None,
    )


def test_build_payload_is_an_id_only_pointer() -> None:
    parsed = parse_eval_suite_run_payload(_payload())

    assert parsed == EvalSuiteRunJobPayload(suite_run_id="suite-run-1")
    assert parsed.to_payload() == {"suite_run_id": "suite-run-1"}
    assert _payload() == {"suite_run_id": "suite-run-1"}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "missing required field"),
        ({"suite_run_id": ""}, "must be a non-empty string"),
        ({"suite_run_id": 1}, "must be a non-empty string"),
        (
            {"suite_run_id": "suite-run-1", "actor": {"id": "user-1"}},
            "unsupported field",
        ),
    ],
)
def test_payload_parser_rejects_any_non_pointer_contract(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_eval_suite_run_payload(payload)


@pytest.mark.asyncio
async def test_handler_delegates_precreated_run_to_queued_suite_executor() -> None:
    job = _job(_payload())
    context = cast(JobExecutionContext, object())
    executor = AsyncMock(return_value={"id": "suite-run-1", "status": "passed"})

    with patch(
        "api.services.agent_eval_suite_jobs.run_queued_suite_run",
        new=executor,
    ):
        result = await handle_eval_suite_run_job(job, context)

    executor.assert_awaited_once_with(job.payload, context)
    assert result == {"id": "suite-run-1", "status": "passed"}


@pytest.mark.asyncio
async def test_queued_executor_forwards_only_pointer_and_lease() -> None:
    lease_lost = asyncio.Event()
    context = cast(
        JobExecutionContext,
        SimpleNamespace(
            lease_lost=lease_lost,
            lease_epoch=7,
            job=SimpleNamespace(id="job-1"),
        ),
    )
    executor = AsyncMock(return_value={"id": "suite-run-1", "status": "running"})

    with patch(
        "api.services.agent_eval_runner.run_queued_suite_run",
        new=executor,
    ):
        result = await run_queued_suite_run(_payload(), context)

    assert result == {"id": "suite-run-1", "status": "running"}
    call = executor.await_args
    assert call is not None
    kwargs = dict(call.kwargs)
    forwarded_lease_lost = kwargs.pop("lease_lost")
    assert kwargs == {
        "suite_run_id": "suite-run-1",
        "job_id": "job-1",
        "lease_epoch": 7,
    }
    assert forwarded_lease_lost is lease_lost
    assert forwarded_lease_lost.is_set() is False
    lease_lost.set()
    assert forwarded_lease_lost.is_set() is True


@pytest.mark.asyncio
async def test_handler_makes_malformed_payload_terminal_without_execution() -> None:
    payload: dict[str, object] = {"suite_run_id": "suite-run-1", "case_ids": []}
    executor = AsyncMock()

    with (
        patch(
            "api.services.agent_eval_suite_jobs.run_queued_suite_run",
            new=executor,
        ),
        pytest.raises(NonRetryableJobError, match="unsupported field"),
    ):
        await handle_eval_suite_run_job(
            _job(payload), cast(JobExecutionContext, object())
        )

    executor.assert_not_awaited()


def test_registers_eval_suite_job_handler() -> None:
    registry = DurableJobRegistry()

    register_eval_suite_run_job_handler(registry)

    assert JobKind.EVAL_SUITE_RUN in registry.kinds
    assert registry.handler_for(JobKind.EVAL_SUITE_RUN) is handle_eval_suite_run_job
