"""PostgreSQL persistence for durable background jobs.

The table is deliberately represented as SQLAlchemy metadata only.  Its lifecycle
belongs to Alembic; application processes must not create or alter it at startup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    asc,
    desc,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncConnection

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

DURABLE_JOBS_TABLE = "durable_jobs"
MAX_ERROR_LENGTH = 8_000


class JobKind(StrEnum):
    """Kinds currently supported by the durable-job contract.

    Keeping the enum small makes the payload contract explicit.  New producers
    should add a kind and an independently deployable handler before enqueueing
    it, instead of placing arbitrary import paths in the database.
    """

    KNOWLEDGE_INGEST = "knowledge_ingest"
    WORKFLOW_RESUME = "workflow_resume"
    SECURITY_HITL_RESUME = "security_hitl_resume"
    WORKFLOW_CRON_DISPATCH = "workflow_cron_dispatch"
    MEMORY_PRUNE = "memory_prune"
    EVAL_SUITE_RUN = "eval_suite_run"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATES = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
)


class DurableJobError(RuntimeError):
    """Base exception for durable-job persistence operations."""


class JobNotFoundError(DurableJobError):
    """Raised when a requested durable job does not exist."""


class JobLeaseLostError(DurableJobError):
    """Raised when a worker tries to mutate a job it no longer owns."""


class InvalidJobTransitionError(DurableJobError):
    """Raised for a state transition the durable-job contract disallows."""


@dataclass(frozen=True, slots=True)
class DurableJob:
    """A normalized durable-job row returned by the persistence layer."""

    id: str
    kind: JobKind
    payload: dict[str, Any]
    idempotency_key: str
    state: JobState
    priority: int
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    last_error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    # This is a fencing token, rather than a retry counter.  It must survive
    # explicit retries so an old lease can never become valid again.
    lease_epoch: int = 0


def _schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_schema())


def durable_jobs_table(metadata: MetaData | None = None) -> Table:
    """Return durable-job table metadata for queries and Alembic migrations."""
    table = Table(
        DURABLE_JOBS_TABLE,
        metadata or _metadata(),
        Column("id", String(36), primary_key=True),
        Column("kind", String(64), nullable=False),
        Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("idempotency_key", Text, nullable=False),
        Column("state", String(16), nullable=False, server_default=JobState.QUEUED.value),
        Column("priority", Integer, nullable=False, server_default="0"),
        Column("attempt_count", Integer, nullable=False, server_default="0"),
        Column("lease_epoch", Integer, nullable=False, server_default="0"),
        Column("max_attempts", Integer, nullable=False, server_default="5"),
        Column(
            "available_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
        Column("lease_owner", Text, nullable=True),
        Column("lease_expires_at", DateTime(timezone=True), nullable=True),
        Column("heartbeat_at", DateTime(timezone=True), nullable=True),
        Column("last_error", Text, nullable=True),
        Column("result", JSONB, nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
        Column("started_at", DateTime(timezone=True), nullable=True),
        Column("finished_at", DateTime(timezone=True), nullable=True),
        CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_durable_jobs_state",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_durable_jobs_attempt_count"),
        CheckConstraint("lease_epoch >= 0", name="ck_durable_jobs_lease_epoch"),
        CheckConstraint("max_attempts > 0", name="ck_durable_jobs_max_attempts"),
        UniqueConstraint("kind", "idempotency_key", name="uq_durable_jobs_kind_key"),
    )
    # This is the hot worker query: queued work ordered by priority, followed by
    # availability.  Keep it aligned with ``claim_due_jobs`` below.
    Index(
        "idx_durable_jobs_claim",
        table.c.state,
        table.c.available_at,
        table.c.priority.desc(),
        table.c.created_at,
    )
    Index("idx_durable_jobs_lease", table.c.state, table.c.lease_expires_at)
    Index("idx_durable_jobs_kind_state", table.c.kind, table.c.state)
    return table


def utc_now() -> datetime:
    """Return an aware UTC timestamp (kept injectable in focused tests)."""
    return datetime.now(UTC)


def retry_delay_seconds(
    attempt_count: int,
    *,
    base_seconds: float = 5.0,
    max_seconds: float = 300.0,
) -> float:
    """Deterministic capped exponential backoff for failure and lease recovery."""
    if base_seconds <= 0 or max_seconds <= 0:
        raise ValueError("retry backoff durations must be positive")
    exponent = max(0, int(attempt_count) - 1)
    return min(float(max_seconds), float(base_seconds) * (2**exponent))


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalise_kind(kind: JobKind | str) -> JobKind:
    try:
        return JobKind(kind)
    except ValueError as exc:
        raise ValueError(f"Unsupported durable job kind: {kind!r}") from exc


def _normalise_state(state: JobState | str) -> JobState:
    try:
        return JobState(state)
    except ValueError as exc:
        raise ValueError(f"Unsupported durable job state: {state!r}") from exc


def _normalise_json_object(value: Mapping[str, Any] | None, *, field: str) -> dict[str, Any]:
    payload = dict(value or {})
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"durable job {field} must be JSON-serializable") from exc
    return payload


def _row_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _record(row: Mapping[Any, Any]) -> DurableJob:
    return DurableJob(
        id=str(row["id"]),
        kind=_normalise_kind(str(row["kind"])),
        payload=_row_json_object(row.get("payload")),
        idempotency_key=str(row["idempotency_key"]),
        state=_normalise_state(str(row["state"])),
        priority=int(row.get("priority") or 0),
        attempt_count=int(row.get("attempt_count") or 0),
        max_attempts=int(row.get("max_attempts") or 1),
        available_at=_ensure_aware(row["available_at"]),
        lease_owner=(str(row["lease_owner"]) if row.get("lease_owner") else None),
        lease_expires_at=(
            _ensure_aware(row["lease_expires_at"])
            if row.get("lease_expires_at") is not None
            else None
        ),
        heartbeat_at=(
            _ensure_aware(row["heartbeat_at"])
            if row.get("heartbeat_at") is not None
            else None
        ),
        last_error=(str(row["last_error"]) if row.get("last_error") else None),
        result=(
            _row_json_object(row["result"])
            if row.get("result") is not None
            else None
        ),
        created_at=_ensure_aware(row["created_at"]),
        updated_at=_ensure_aware(row["updated_at"]),
        started_at=(
            _ensure_aware(row["started_at"])
            if row.get("started_at") is not None
            else None
        ),
        finished_at=(
            _ensure_aware(row["finished_at"])
            if row.get("finished_at") is not None
            else None
        ),
        lease_epoch=int(row.get("lease_epoch") or 0),
    )


def _error_message(error: BaseException | str) -> str:
    message = str(error).strip() or type(error).__name__
    return message[:MAX_ERROR_LENGTH]


def _validate_worker_id(worker_id: str) -> str:
    normalized = worker_id.strip()
    if not normalized:
        raise ValueError("worker_id is required")
    return normalized


def _validate_lease_epoch(lease_epoch: int) -> int:
    """Validate the persistent fencing token supplied by a worker.

    ``0`` remains valid for a job that was already running when the migration
    was applied.  Every claim made by code aware of the token advances it to at
    least one.
    """
    if (
        isinstance(lease_epoch, bool)
        or not isinstance(lease_epoch, int)
        or lease_epoch < 0
    ):
        raise ValueError("lease_epoch must be a non-negative integer")
    return lease_epoch


def _validate_positive(name: str, value: int | float) -> int | float:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


async def enqueue_job(
    *,
    kind: JobKind | str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    max_attempts: int = 5,
    priority: int = 0,
    available_at: datetime | None = None,
) -> DurableJob:
    """Insert a job, or return the existing job for the same idempotency key.

    The unique key is intentionally retained for terminal jobs as well.  A
    producer retrying an HTTP request must observe the original job, not create
    a second side effect.  Operators can use :func:`retry_job` for an explicit
    new execution of a failed/cancelled row.
    """
    async with get_async_control_plane_engine().begin() as conn:
        return await enqueue_job_in_transaction(
            conn,
            kind=kind,
            payload=payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            priority=priority,
            available_at=available_at,
        )


async def enqueue_job_in_transaction(
    conn: AsyncConnection,
    *,
    kind: JobKind | str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    max_attempts: int = 5,
    priority: int = 0,
    available_at: datetime | None = None,
) -> DurableJob:
    """Enqueue idempotently on an existing database transaction.

    The caller owns the transaction's commit/rollback boundary.  This is used
    when enqueuing a job is inseparable from another state transition (for
    example, claiming a cron occurrence): either both writes commit, or
    neither does.  It deliberately does not open an engine transaction itself.
    """
    normalized_kind = _normalise_kind(kind)
    normalized_payload = _normalise_json_object(payload, field="payload")
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    _validate_positive("max_attempts", max_attempts)
    now = utc_now()
    scheduled_for = _ensure_aware(available_at) if available_at is not None else now
    table = durable_jobs_table()
    record = {
        "id": str(uuid4()),
        "kind": normalized_kind.value,
        "payload": normalized_payload,
        "idempotency_key": normalized_key,
        "state": JobState.QUEUED.value,
        "priority": int(priority),
        "attempt_count": 0,
        "lease_epoch": 0,
        "max_attempts": int(max_attempts),
        "available_at": scheduled_for,
        "created_at": now,
        "updated_at": now,
    }
    stmt = (
        insert(table)
        .values(record)
        .on_conflict_do_nothing(index_elements=[table.c.kind, table.c.idempotency_key])
        .returning(table)
    )
    inserted = (await conn.execute(stmt)).mappings().first()
    if inserted is not None:
        return _record(inserted)
    existing = (
        await conn.execute(
            select(table).where(
                and_(
                    table.c.kind == normalized_kind.value,
                    table.c.idempotency_key == normalized_key,
                )
            )
        )
    ).mappings().one()
    return _record(existing)


async def get_job(job_id: str) -> DurableJob | None:
    table = durable_jobs_table()
    async with get_async_control_plane_engine().connect() as conn:
        row = (
            await conn.execute(select(table).where(table.c.id == job_id))
        ).mappings().first()
    return _record(row) if row is not None else None


async def list_jobs(
    *,
    kind: JobKind | str | None = None,
    state: JobState | str | None = None,
    limit: int = 100,
) -> list[DurableJob]:
    """List jobs for operational inspection; claiming remains lock based."""
    safe_limit = max(1, min(int(limit), 500))
    table = durable_jobs_table()
    filters = []
    if kind is not None:
        filters.append(table.c.kind == _normalise_kind(kind).value)
    if state is not None:
        filters.append(table.c.state == _normalise_state(state).value)
    stmt = select(table).order_by(desc(table.c.created_at)).limit(safe_limit)
    if filters:
        stmt = stmt.where(*filters)
    async with get_async_control_plane_engine().connect() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [_record(row) for row in rows]


async def _locked_job(conn: AsyncConnection, job_id: str) -> DurableJob:
    table = durable_jobs_table()
    row = (
        await conn.execute(
            select(table).where(table.c.id == job_id).with_for_update()
        )
    ).mappings().first()
    if row is None:
        raise JobNotFoundError(f"Durable job {job_id} was not found")
    return _record(row)


def _ensure_owned_running(
    job: DurableJob,
    *,
    worker_id: str,
    lease_epoch: int,
    now: datetime,
) -> None:
    if job.state is not JobState.RUNNING or job.lease_owner != worker_id:
        raise JobLeaseLostError(f"Worker {worker_id} no longer owns durable job {job.id}")
    if job.lease_epoch != lease_epoch:
        raise JobLeaseLostError(
            f"Lease epoch changed for durable job {job.id} "
            f"(expected={lease_epoch}, current={job.lease_epoch})"
        )
    if job.lease_expires_at is None or job.lease_expires_at <= now:
        raise JobLeaseLostError(f"Lease expired for durable job {job.id}")


async def _update_locked_job(
    conn: AsyncConnection,
    *,
    job_id: str,
    values: Mapping[str, Any],
    table: Table | None = None,
) -> DurableJob:
    target_table = table if table is not None else durable_jobs_table()
    row = (
        await conn.execute(
            update(target_table)
            .where(target_table.c.id == job_id)
            .values(**dict(values))
            .returning(target_table)
        )
    ).mappings().one()
    return _record(row)


async def _recover_expired_jobs_in_transaction(
    conn: AsyncConnection,
    *,
    now: datetime,
    limit: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> list[DurableJob]:
    """Requeue expired leases while holding their rows with ``SKIP LOCKED``."""
    if limit <= 0:
        return []
    table = durable_jobs_table()
    expired_stmt = _expired_lease_statement(table, now=now, limit=limit)
    rows = (await conn.execute(expired_stmt)).mappings().all()
    recovered: list[DurableJob] = []
    for row in rows:
        job = _record(row)
        if job.attempt_count >= job.max_attempts:
            values = {
                "state": JobState.FAILED.value,
                "lease_owner": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "last_error": "Job lease expired after its final allowed attempt.",
                "updated_at": now,
                "finished_at": now,
            }
        else:
            delay = retry_delay_seconds(
                job.attempt_count,
                base_seconds=retry_base_seconds,
                max_seconds=retry_max_seconds,
            )
            values = {
                "state": JobState.QUEUED.value,
                "available_at": now + timedelta(seconds=delay),
                "lease_owner": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "last_error": "Job lease expired before completion; retry scheduled.",
                "updated_at": now,
            }
        recovered.append(await _update_locked_job(conn, job_id=job.id, values=values))
    return recovered


def _expired_lease_statement(table: Table, *, now: datetime, limit: int) -> Any:
    """Build the lease-recovery lock query (kept inspectable for regression tests)."""
    return (
        select(table)
        .where(
            and_(
                table.c.state == JobState.RUNNING.value,
                or_(
                    table.c.lease_expires_at.is_(None),
                    table.c.lease_expires_at <= now,
                ),
            )
        )
        .order_by(asc(table.c.lease_expires_at).nullsfirst(), asc(table.c.created_at))
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


def _claim_due_statement(table: Table, *, now: datetime, limit: int) -> Any:
    """Build the queue claim lock query (kept inspectable for regression tests)."""
    return (
        select(table)
        .where(
            and_(
                table.c.state == JobState.QUEUED.value,
                table.c.available_at <= now,
                table.c.attempt_count < table.c.max_attempts,
            )
        )
        .order_by(
            desc(table.c.priority),
            asc(table.c.available_at),
            asc(table.c.created_at),
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


async def recover_expired_jobs(
    *,
    limit: int = 100,
    retry_base_seconds: float = 5.0,
    retry_max_seconds: float = 300.0,
) -> list[DurableJob]:
    """Recover jobs left running by a crashed worker after their lease expires."""
    safe_limit = max(1, min(int(limit), 1_000))
    _validate_positive("retry_base_seconds", retry_base_seconds)
    _validate_positive("retry_max_seconds", retry_max_seconds)
    now = utc_now()
    async with get_async_control_plane_engine().begin() as conn:
        return await _recover_expired_jobs_in_transaction(
            conn,
            now=now,
            limit=safe_limit,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )


async def claim_due_jobs(
    worker_id: str,
    *,
    limit: int = 1,
    lease_seconds: float = 60.0,
    retry_base_seconds: float = 5.0,
    retry_max_seconds: float = 300.0,
) -> list[DurableJob]:
    """Atomically claim due jobs using PostgreSQL ``FOR UPDATE SKIP LOCKED``.

    Expired leases are recovered in the same transaction before claiming new
    rows.  This permits horizontally scaled workers without double-claiming.
    A handler must still be idempotent: a process can fail after its external
    side effect but before its terminal state is stored.
    """
    owner = _validate_worker_id(worker_id)
    safe_limit = max(1, min(int(limit), 100))
    _validate_positive("lease_seconds", lease_seconds)
    _validate_positive("retry_base_seconds", retry_base_seconds)
    _validate_positive("retry_max_seconds", retry_max_seconds)
    now = utc_now()
    lease_expires_at = now + timedelta(seconds=float(lease_seconds))
    table = durable_jobs_table()
    async with get_async_control_plane_engine().begin() as conn:
        await _recover_expired_jobs_in_transaction(
            conn,
            now=now,
            limit=max(safe_limit * 2, 20),
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )
        claim_stmt = _claim_due_statement(table, now=now, limit=safe_limit)
        rows = (await conn.execute(claim_stmt)).mappings().all()
        claimed: list[DurableJob] = []
        for row in rows:
            job = _record(row)
            claimed.append(
                await _update_locked_job(
                    conn,
                    job_id=job.id,
                    table=table,
                    values={
                        "state": JobState.RUNNING.value,
                        "attempt_count": job.attempt_count + 1,
                        # Keep this an SQL expression instead of deriving it
                        # from ``attempt_count``: retries may reset attempts,
                        # but a fencing token must only move forward.
                        "lease_epoch": table.c.lease_epoch + 1,
                        "lease_owner": owner,
                        "lease_expires_at": lease_expires_at,
                        "heartbeat_at": now,
                        "updated_at": now,
                        "started_at": job.started_at or now,
                    },
                )
            )
    return claimed


async def heartbeat_job(
    job_id: str,
    *,
    worker_id: str,
    lease_epoch: int,
    lease_seconds: float = 60.0,
) -> DurableJob:
    """Extend a claimed job's lease or reject a stale worker."""
    owner = _validate_worker_id(worker_id)
    epoch = _validate_lease_epoch(lease_epoch)
    _validate_positive("lease_seconds", lease_seconds)
    now = utc_now()
    async with get_async_control_plane_engine().begin() as conn:
        job = await _locked_job(conn, job_id)
        _ensure_owned_running(job, worker_id=owner, lease_epoch=epoch, now=now)
        return await _update_locked_job(
            conn,
            job_id=job_id,
            values={
                "lease_expires_at": now + timedelta(seconds=float(lease_seconds)),
                "heartbeat_at": now,
                "updated_at": now,
            },
        )


async def complete_job(
    job_id: str,
    *,
    worker_id: str,
    lease_epoch: int,
    result: Mapping[str, Any] | None = None,
) -> DurableJob:
    """Mark an owned running job as succeeded."""
    owner = _validate_worker_id(worker_id)
    epoch = _validate_lease_epoch(lease_epoch)
    normalized_result = (
        _normalise_json_object(result, field="result") if result is not None else None
    )
    now = utc_now()
    async with get_async_control_plane_engine().begin() as conn:
        job = await _locked_job(conn, job_id)
        _ensure_owned_running(job, worker_id=owner, lease_epoch=epoch, now=now)
        return await _update_locked_job(
            conn,
            job_id=job_id,
            values={
                "state": JobState.SUCCEEDED.value,
                "result": normalized_result,
                "lease_owner": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "updated_at": now,
                "finished_at": now,
            },
        )


async def fail_job(
    job_id: str,
    *,
    worker_id: str,
    lease_epoch: int,
    error: BaseException | str,
    retryable: bool = True,
    retry_base_seconds: float = 5.0,
    retry_max_seconds: float = 300.0,
) -> DurableJob:
    """Record a handler failure and either retry it or make it terminal."""
    owner = _validate_worker_id(worker_id)
    epoch = _validate_lease_epoch(lease_epoch)
    _validate_positive("retry_base_seconds", retry_base_seconds)
    _validate_positive("retry_max_seconds", retry_max_seconds)
    now = utc_now()
    async with get_async_control_plane_engine().begin() as conn:
        job = await _locked_job(conn, job_id)
        _ensure_owned_running(job, worker_id=owner, lease_epoch=epoch, now=now)
        can_retry = retryable and job.attempt_count < job.max_attempts
        values: dict[str, Any] = {
            "lease_owner": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "last_error": _error_message(error),
            "updated_at": now,
        }
        if can_retry:
            values.update(
                {
                    "state": JobState.QUEUED.value,
                    "available_at": now
                    + timedelta(
                        seconds=retry_delay_seconds(
                            job.attempt_count,
                            base_seconds=retry_base_seconds,
                            max_seconds=retry_max_seconds,
                        )
                    ),
                }
            )
        else:
            values.update({"state": JobState.FAILED.value, "finished_at": now})
        return await _update_locked_job(conn, job_id=job_id, values=values)


async def release_job(
    job_id: str,
    *,
    worker_id: str,
    lease_epoch: int,
    reason: BaseException | str = "Worker stopped before job completion.",
    retry_base_seconds: float = 5.0,
    retry_max_seconds: float = 300.0,
) -> DurableJob:
    """Return an owned job to the queue during a graceful worker shutdown."""
    return await fail_job(
        job_id,
        worker_id=worker_id,
        lease_epoch=lease_epoch,
        error=reason,
        retryable=True,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
    )


async def cancel_job(job_id: str, *, reason: str | None = None) -> DurableJob:
    """Cancel queued or running work; terminal rows are returned unchanged."""
    now = utc_now()
    async with get_async_control_plane_engine().begin() as conn:
        job = await _locked_job(conn, job_id)
        if job.state in TERMINAL_JOB_STATES:
            return job
        return await _update_locked_job(
            conn,
            job_id=job_id,
            values={
                "state": JobState.CANCELLED.value,
                "lease_owner": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "last_error": (reason or "Cancelled by request.")[:MAX_ERROR_LENGTH],
                "updated_at": now,
                "finished_at": now,
            },
        )


async def retry_job(job_id: str, *, available_at: datetime | None = None) -> DurableJob:
    """Explicitly retry a failed/cancelled job without creating a duplicate key."""
    now = utc_now()
    scheduled_for = _ensure_aware(available_at) if available_at is not None else now
    async with get_async_control_plane_engine().begin() as conn:
        job = await _locked_job(conn, job_id)
        if job.state not in {JobState.FAILED, JobState.CANCELLED}:
            raise InvalidJobTransitionError(
                f"Only failed or cancelled jobs can be retried (current={job.state.value})"
            )
        return await _update_locked_job(
            conn,
            job_id=job_id,
            values={
                "state": JobState.QUEUED.value,
                "attempt_count": 0,
                "available_at": scheduled_for,
                "lease_owner": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "last_error": None,
                "result": None,
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
            },
        )
