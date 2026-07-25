"""Durable contract for asynchronously executing an Eval Suite run.

The worker payload deliberately contains only a SuiteRun identifier.  Every
evaluator-relevant input is frozen in the private SuiteRun execution snapshot
when the API atomically creates its CaseRun work items and durable job.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from api.persistence.durable_jobs import DurableJob, JobKind
from api.services.durable_job_service import (
    DurableJobRegistry,
    JobExecutionContext,
    NonRetryableJobError,
)

_PAYLOAD_FIELDS = frozenset({"suite_run_id"})


@dataclass(frozen=True, slots=True)
class EvalSuiteRunJobPayload:
    """Validated JSON-only pointer to one already-created SuiteRun."""

    suite_run_id: str

    def to_payload(self) -> dict[str, str]:
        return {"suite_run_id": self.suite_run_id}


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("eval_suite_run payload must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError("eval_suite_run payload keys must be strings")
    return cast(Mapping[str, object], value)


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"eval_suite_run payload {field} must be a non-empty string")
    return normalized


def parse_eval_suite_run_payload(raw: Mapping[str, object]) -> EvalSuiteRunJobPayload:
    """Strictly validate the one-field durable worker payload."""
    payload = _mapping(raw)
    unknown = sorted(set(payload) - _PAYLOAD_FIELDS)
    if unknown:
        raise ValueError(
            "eval_suite_run payload has unsupported field(s): " + ", ".join(unknown)
        )
    if "suite_run_id" not in payload:
        raise ValueError("eval_suite_run payload is missing required field: suite_run_id")
    return EvalSuiteRunJobPayload(
        suite_run_id=_required_text(payload["suite_run_id"], field="suite_run_id")
    )


def build_eval_suite_run_payload(*, suite_run_id: str) -> dict[str, str]:
    """Build the canonical ID-only durable payload for one SuiteRun."""
    return parse_eval_suite_run_payload({"suite_run_id": suite_run_id}).to_payload()


async def run_queued_suite_run(
    payload: Mapping[str, object],
    context: JobExecutionContext,
) -> Mapping[str, Any]:
    """Adapt the persisted pointer to the runner's fenced worker entry point."""
    # Keep this import lazy: idle durable-job workers should not import Agno
    # evaluation dependencies merely to build their trusted handler registry.
    from api.services.agent_eval_runner import (
        run_queued_suite_run as execute_queued_suite_run,
    )

    parsed = parse_eval_suite_run_payload(payload)
    return await execute_queued_suite_run(
        suite_run_id=parsed.suite_run_id,
        job_id=context.job.id,
        lease_epoch=context.lease_epoch,
        lease_lost=context.lease_lost,
    )


async def handle_eval_suite_run_job(
    job: DurableJob,
    context: JobExecutionContext,
) -> dict[str, Any]:
    """Validate and execute one pre-created Eval Suite run in a worker."""
    try:
        parse_eval_suite_run_payload(job.payload)
        result = await run_queued_suite_run(job.payload, context)
    except ValueError as exc:
        raise NonRetryableJobError(str(exc)) from exc
    return dict(result)


def register_eval_suite_run_job_handler(registry: DurableJobRegistry) -> None:
    """Register the trusted Eval Suite worker handler."""
    registry.register(JobKind.EVAL_SUITE_RUN, handle_eval_suite_run_job)


__all__ = [
    "EvalSuiteRunJobPayload",
    "build_eval_suite_run_payload",
    "handle_eval_suite_run_job",
    "parse_eval_suite_run_payload",
    "register_eval_suite_run_job_handler",
    "run_queued_suite_run",
]
