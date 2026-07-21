"""Built-in durable-job handlers that are safe to run in a worker process.

Only handlers with a fully serializable payload contract live here.  The other
declared kinds intentionally remain unregistered until their current in-process
producers are migrated; registering an adapter that merely starts another
``create_task`` would defeat durability.
"""

from __future__ import annotations

import math
from typing import Any

from api.persistence.durable_jobs import DurableJob, JobKind
from api.services.durable_job_service import (
    DurableJobRegistry,
    JobExecutionContext,
    NonRetryableJobError,
)
from api.services.knowledge_durable_jobs import register_knowledge_job_handler
from api.services.memory_durable_jobs import register_memory_job_handler


def _approval_id(job: DurableJob) -> str:
    approval_id = str(job.payload.get("approval_id") or "").strip()
    if not approval_id:
        raise NonRetryableJobError("durable resume payload requires approval_id")
    return approval_id


def _required_payload_text(job: DurableJob, field: str) -> str:
    value = job.payload.get(field)
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise NonRetryableJobError(
            f"workflow_cron_dispatch payload requires {field}"
        )
    return normalized


def _workflow_cron_payload(job: DurableJob) -> dict[str, Any]:
    """Validate and normalize the fully serializable cron dispatch contract."""
    definition = job.payload.get("definition")
    if not isinstance(definition, dict):
        raise NonRetryableJobError(
            "workflow_cron_dispatch payload requires definition object"
        )
    scheduled_at = job.payload.get("scheduled_at")
    if (
        not isinstance(scheduled_at, int | float)
        or isinstance(scheduled_at, bool)
        or not math.isfinite(float(scheduled_at))
    ):
        raise NonRetryableJobError(
            "workflow_cron_dispatch payload requires finite scheduled_at"
        )
    return {
        "workflow_id": _required_payload_text(job, "workflow_id"),
        "definition": dict(definition),
        "owner_user_id": _required_payload_text(job, "owner_user_id"),
        "run_id": _required_payload_text(job, "run_id"),
        "session_id": _required_payload_text(job, "session_id"),
        "expression": _required_payload_text(job, "expression"),
        "scheduled_at": float(scheduled_at),
    }


async def _resume_workflow(
    job: DurableJob,
    _context: JobExecutionContext,
) -> dict[str, Any]:
    # Import lazily: a standalone worker should not import Agno/LLM machinery
    # until it has actually claimed a workflow resume job.
    from api.services.workflow_run_runtime import resume_workflow_run

    approval_id = _approval_id(job)
    status = await resume_workflow_run(approval_id)
    return {"approval_id": approval_id, "run_status": status}


async def _resume_security_hitl(
    job: DurableJob,
    _context: JobExecutionContext,
) -> dict[str, Any]:
    """Continue one security HITL run inside the worker, never via the API scheduler."""
    # ``execute_security_hitl_resume`` intentionally calls the continuation
    # itself.  Importing ``resume_security_run`` here would only enqueue a new
    # job and leave this leased job falsely marked as complete.
    from agno.run import RunStatus

    from api.services.security_run_runtime import execute_security_hitl_resume

    approval_id = _approval_id(job)
    status = await execute_security_hitl_resume(approval_id)
    if status != RunStatus.completed.value:
        # The continuation already persisted ERROR and emitted the existing
        # submitter/admin notification.  Keep this durable row terminal until
        # an administrator explicitly uses the retry endpoint.
        raise NonRetryableJobError(
            f"Security HITL continuation did not complete (status={status!r})"
        )
    return {"approval_id": approval_id, "run_status": status}


async def _dispatch_workflow_cron(
    job: DurableJob,
    _context: JobExecutionContext,
) -> dict[str, Any]:
    """Run one already-claimed cron workflow inside the worker process."""
    # Keep the API scheduler light and make the execution process independent
    # of the process that won the cron CAS claim.
    from api.services.workflow_cron import _run_cron_workflow

    payload = _workflow_cron_payload(job)
    terminal_status = await _run_cron_workflow(
        workflow_id=payload["workflow_id"],
        definition=payload["definition"],
        owner_user_id=payload["owner_user_id"],
        run_id=payload["run_id"],
        session_id=payload["session_id"],
        expression=payload["expression"],
    )
    return {
        "workflow_id": payload["workflow_id"],
        "run_id": payload["run_id"],
        "session_id": payload["session_id"],
        "scheduled_at": payload["scheduled_at"],
        "terminal_status": terminal_status,
    }


def build_durable_job_registry() -> DurableJobRegistry:
    """Return the built-in handlers available in every worker deployment."""
    registry = DurableJobRegistry()
    registry.register(JobKind.WORKFLOW_RESUME, _resume_workflow)
    registry.register(JobKind.SECURITY_HITL_RESUME, _resume_security_hitl)
    registry.register(JobKind.WORKFLOW_CRON_DISPATCH, _dispatch_workflow_cron)
    register_knowledge_job_handler(registry)
    register_memory_job_handler(registry)
    return registry
