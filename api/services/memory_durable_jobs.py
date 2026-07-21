"""Durable job contract for automatic user-memory prune."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4

from loguru import logger

from api.persistence import durable_jobs as job_store
from api.persistence.durable_jobs import DurableJob, JobKind, JobState
from api.services.chat_settings_service import get_chat_settings
from api.services.durable_job_service import (
    DurableJobRegistry,
    JobExecutionContext,
    NonRetryableJobError,
)
from api.services.memory_prune_service import run_memory_prune

# Default cadence for the follow-up self-enqueue (24h).
_DEFAULT_INTERVAL_HOURS = 24


def _optional_int(value: object, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise NonRetryableJobError(f"memory_prune payload {field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise NonRetryableJobError(
                f"memory_prune payload {field} must be an integer"
            ) from exc
    raise NonRetryableJobError(f"memory_prune payload {field} must be an integer")


def _parse_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise NonRetryableJobError("memory_prune payload must be an object")
    retention = _optional_int(raw.get("retention_days"), field="retention_days")
    top_k = _optional_int(raw.get("top_k"), field="top_k")
    user_ids_raw = raw.get("user_ids")
    user_ids: list[str] | None = None
    if user_ids_raw is not None:
        if not isinstance(user_ids_raw, list):
            raise NonRetryableJobError("memory_prune payload user_ids must be a list")
        user_ids = [str(u).strip() for u in user_ids_raw if str(u).strip()]
    schedule_next = raw.get("schedule_next", True)
    if not isinstance(schedule_next, bool):
        raise NonRetryableJobError("memory_prune payload schedule_next must be a boolean")
    interval_hours = _optional_int(raw.get("interval_hours"), field="interval_hours")
    return {
        "retention_days": retention,
        "top_k": top_k,
        "user_ids": user_ids,
        "schedule_next": schedule_next,
        "interval_hours": interval_hours or _DEFAULT_INTERVAL_HOURS,
    }


async def enqueue_memory_prune_job(
    *,
    payload: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
    available_at: datetime | None = None,
    priority: int = 50,
) -> DurableJob:
    """Queue a memory prune pass (idempotent when *idempotency_key* is stable)."""
    body = dict(payload or {})
    key = (idempotency_key or f"memory-prune:{uuid4().hex}").strip()
    # Validate early so bad producers do not leave poison rows.
    _parse_payload(body)
    return await job_store.enqueue_job(
        kind=JobKind.MEMORY_PRUNE,
        payload=body,
        idempotency_key=key,
        max_attempts=3,
        priority=priority,
        available_at=available_at,
    )


async def ensure_memory_prune_scheduled() -> DurableJob | None:
    """Ensure a follow-up prune job exists when the Settings flag is enabled.

    Uses a stable bootstrap idempotency key. When that key is still non-terminal,
    ``enqueue_job`` returns the existing row (no duplicate). After a successful
    run the handler schedules the next fire with a timestamped key.
    """
    settings = await get_chat_settings()
    if not settings.get("memory_prune_enabled", True):
        logger.info("memory prune scheduler skipped (memory_prune_enabled=false)")
        return None

    # If a queued/running prune already exists, do not stampede the queue.
    for state in (JobState.QUEUED, JobState.RUNNING):
        existing = await job_store.list_jobs(
            kind=JobKind.MEMORY_PRUNE, state=state, limit=1
        )
        if existing:
            logger.debug(
                "memory prune already scheduled id={} state={}",
                existing[0].id,
                existing[0].state,
            )
            return existing[0]

    # Fresh key each boot when no active job — terminal rows keep their
    # idempotency keys, so reusing a fixed key would return the old SUCCEEDED row.
    return await enqueue_memory_prune_job(
        payload={
            "retention_days": int(settings.get("memory_prune_retention_days") or 90),
            "top_k": int(settings.get("memory_prune_top_k") or 50),
            "schedule_next": True,
            "interval_hours": _DEFAULT_INTERVAL_HOURS,
        },
        idempotency_key=f"memory-prune:boot:{uuid4().hex}",
        available_at=datetime.now(UTC),
        priority=50,
    )


async def _handle_memory_prune(
    job: DurableJob,
    _context: JobExecutionContext,
) -> dict[str, Any]:
    settings = await get_chat_settings()
    if not settings.get("memory_prune_enabled", True):
        return {"skipped": True, "reason": "memory_prune_enabled=false"}

    parsed = _parse_payload(job.payload)
    result = await run_memory_prune(
        retention_days=parsed["retention_days"],
        top_k=parsed["top_k"],
        user_ids=parsed["user_ids"],
    )

    if parsed["schedule_next"] and settings.get("memory_prune_enabled", True):
        hours = max(1, int(parsed["interval_hours"] or _DEFAULT_INTERVAL_HOURS))
        next_at = datetime.now(UTC) + timedelta(hours=hours)
        await enqueue_memory_prune_job(
            payload={
                "retention_days": int(
                    settings.get("memory_prune_retention_days") or 90
                ),
                "top_k": int(settings.get("memory_prune_top_k") or 50),
                "schedule_next": True,
                "interval_hours": hours,
            },
            # Unique key per occurrence so completed bootstrap keys can recycle.
            idempotency_key=f"memory-prune:at:{int(next_at.timestamp())}",
            available_at=next_at,
            priority=50,
        )

    return result


def register_memory_job_handler(registry: DurableJobRegistry) -> None:
    """Attach MEMORY_PRUNE to the durable-job registry."""
    registry.register(JobKind.MEMORY_PRUNE, _handle_memory_prune)


async def enqueue_memory_prune_now() -> DurableJob:
    """Force an immediate prune job with a fresh idempotency key."""
    settings = await get_chat_settings()
    return await enqueue_memory_prune_job(
        payload={
            "retention_days": int(settings.get("memory_prune_retention_days") or 90),
            "top_k": int(settings.get("memory_prune_top_k") or 50),
            "schedule_next": False,
        },
        idempotency_key=f"memory-prune:manual:{uuid4().hex}",
        priority=10,
    )


__all__ = [
    "enqueue_memory_prune_job",
    "enqueue_memory_prune_now",
    "ensure_memory_prune_scheduled",
    "register_memory_job_handler",
]
