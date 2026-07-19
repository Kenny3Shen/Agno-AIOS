"""Dispatch and worker orchestration for :mod:`api.persistence.durable_jobs`.

The service intentionally keeps handlers in application code rather than in
database rows.  A durable job payload is data, not an import path or shell
command; this makes a worker safe to run as a separate process.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from socket import gethostname
from typing import Any, Protocol
from uuid import uuid4

from loguru import logger

from api.persistence import durable_jobs as job_store
from api.persistence.durable_jobs import (
    DurableJob,
    JobKind,
    JobLeaseLostError,
)

JobHandlerResult = Mapping[str, Any] | None
JobHandler = Callable[[DurableJob, "JobExecutionContext"], Awaitable[JobHandlerResult]]


class DurableJobHandlerError(RuntimeError):
    """Base exception a handler can use to describe an expected failure."""


class NonRetryableJobError(DurableJobHandlerError):
    """A handler error that should become terminal after this attempt."""


class UnknownJobKindError(NonRetryableJobError):
    """A queued job has no handler in this worker process."""


class DurableJobStore(Protocol):
    """Narrow persistence boundary used by the worker and its focused tests."""

    async def claim_due_jobs(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: float,
        retry_base_seconds: float,
        retry_max_seconds: float,
    ) -> list[DurableJob]: ...

    async def heartbeat_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> DurableJob: ...

    async def complete_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        result: Mapping[str, Any] | None,
    ) -> DurableJob: ...

    async def fail_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        error: BaseException | str,
        retryable: bool,
        retry_base_seconds: float,
        retry_max_seconds: float,
    ) -> DurableJob: ...

    async def release_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        reason: BaseException | str,
        retry_base_seconds: float,
        retry_max_seconds: float,
    ) -> DurableJob: ...


class DurableJobRegistry:
    """Explicit job-kind-to-handler mapping for one worker deployment."""

    def __init__(self) -> None:
        self._handlers: dict[JobKind, JobHandler] = {}

    def register(self, kind: JobKind | str, handler: JobHandler) -> JobHandler:
        """Register one handler and return it for decorator-friendly use."""
        normalized_kind = JobKind(kind)
        if normalized_kind in self._handlers:
            raise ValueError(f"A durable job handler already exists for {normalized_kind}")
        self._handlers[normalized_kind] = handler
        return handler

    def handler_for(self, kind: JobKind) -> JobHandler:
        try:
            return self._handlers[kind]
        except KeyError as exc:
            raise UnknownJobKindError(
                f"No durable-job handler registered for kind {kind.value!r}"
            ) from exc

    @property
    def kinds(self) -> frozenset[JobKind]:
        return frozenset(self._handlers)


@dataclass(slots=True)
class JobExecutionContext:
    """Worker-owned execution helpers made available to a handler.

    The worker heartbeats automatically.  A handler that performs a long phase
    synchronously can call :meth:`heartbeat` at a known safe boundary; it can
    also observe ``lease_lost`` and stop optional follow-up work.
    """

    job: DurableJob
    worker_id: str
    lease_seconds: float
    lease_lost: asyncio.Event
    _store: DurableJobStore

    async def heartbeat(self) -> DurableJob:
        updated = await self._store.heartbeat_job(
            self.job.id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        return updated


@dataclass(frozen=True, slots=True)
class DurableJobWorkerOptions:
    """Runtime limits for a standalone durable job worker."""

    concurrency: int = 4
    lease_seconds: float = 60.0
    poll_interval_seconds: float = 1.0
    retry_base_seconds: float = 5.0
    retry_max_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least one")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.retry_base_seconds <= 0 or self.retry_max_seconds <= 0:
            raise ValueError("retry backoff durations must be positive")


def default_worker_id() -> str:
    """Return a traceable, per-process worker id suitable for a job lease."""
    return f"durable-jobs:{gethostname()}:{uuid4()}"


async def enqueue_durable_job(
    *,
    kind: JobKind | str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    max_attempts: int = 5,
    priority: int = 0,
) -> DurableJob:
    """Service-level producer API for gradual migration from ``create_task``."""
    return await job_store.enqueue_job(
        kind=kind,
        payload=payload,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        priority=priority,
    )


class DurableJobWorker:
    """Claim, execute, heartbeat, and finish jobs in an independent process."""

    def __init__(
        self,
        *,
        registry: DurableJobRegistry,
        worker_id: str | None = None,
        options: DurableJobWorkerOptions | None = None,
        store: DurableJobStore | None = None,
    ) -> None:
        self.registry = registry
        self.worker_id = (worker_id or default_worker_id()).strip()
        if not self.worker_id:
            raise ValueError("worker_id is required")
        self.options = options or DurableJobWorkerOptions()
        self._store: DurableJobStore = store or job_store

    async def run_once(self) -> int:
        """Process one claimed batch and return the number of claimed jobs."""
        claimed = await self._store.claim_due_jobs(
            self.worker_id,
            limit=self.options.concurrency,
            lease_seconds=self.options.lease_seconds,
            retry_base_seconds=self.options.retry_base_seconds,
            retry_max_seconds=self.options.retry_max_seconds,
        )
        if not claimed:
            return 0
        await asyncio.gather(*(self._execute(job) for job in claimed))
        return len(claimed)

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        """Keep polling until a process signal (or caller) requests shutdown."""
        logger.info(
            "Durable job worker started id={} handlers={} concurrency={}",
            self.worker_id,
            sorted(kind.value for kind in self.registry.kinds),
            self.options.concurrency,
        )
        while not stop_event.is_set():
            claimed = await self.run_once()
            if claimed:
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=self.options.poll_interval_seconds
                )
            except TimeoutError:
                pass
        logger.info("Durable job worker stopped id={}", self.worker_id)

    async def _execute(self, job: DurableJob) -> None:
        lease_lost = asyncio.Event()
        context = JobExecutionContext(
            job=job,
            worker_id=self.worker_id,
            lease_seconds=self.options.lease_seconds,
            lease_lost=lease_lost,
            _store=self._store,
        )
        heartbeat = asyncio.create_task(
            self._heartbeat_loop(job, lease_lost),
            name=f"durable-job-heartbeat:{job.id}",
        )
        try:
            handler = self.registry.handler_for(job.kind)
            result = await handler(job, context)
            if result is not None and not isinstance(result, Mapping):
                raise NonRetryableJobError(
                    "Durable job handlers must return a mapping or None"
                )
            if lease_lost.is_set():
                logger.warning(
                    "Durable job {} finished after its lease was lost; terminal update skipped",
                    job.id,
                )
                return
            await self._store.complete_job(
                job.id,
                worker_id=self.worker_id,
                result=dict(result) if result is not None else None,
            )
            logger.info("Durable job succeeded id={} kind={}", job.id, job.kind.value)
        except asyncio.CancelledError:
            # A graceful worker stop must release the lease rather than leave a
            # healthy job invisible until its full lease timeout elapses.
            await self._release_on_cancellation(job, lease_lost)
            raise
        except JobLeaseLostError:
            lease_lost.set()
            logger.warning(
                "Durable job lease lost id={} kind={}", job.id, job.kind.value
            )
        except Exception as exc:  # noqa: BLE001 - job handlers are extension code.
            if lease_lost.is_set():
                logger.warning(
                    "Durable job {} failed after lease loss; failure update skipped: {}",
                    job.id,
                    exc,
                )
                return
            await self._record_failure(
                job,
                exc,
                retryable=not isinstance(exc, NonRetryableJobError),
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(
        self,
        job: DurableJob,
        lease_lost: asyncio.Event,
    ) -> None:
        # Keep enough slack for one slow database roundtrip while avoiding a
        # busy heartbeat loop for short development leases.
        interval = max(0.1, min(self.options.lease_seconds / 3, 30.0))
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._store.heartbeat_job(
                        job.id,
                        worker_id=self.worker_id,
                        lease_seconds=self.options.lease_seconds,
                    )
                except JobLeaseLostError:
                    lease_lost.set()
                    logger.warning("Durable job heartbeat lost lease id={}", job.id)
                    return
                except Exception:  # noqa: BLE001 - a later heartbeat can recover a transient DB failure.
                    logger.exception("Durable job heartbeat failed id={}", job.id)
        except asyncio.CancelledError:
            raise

    async def _record_failure(
        self,
        job: DurableJob,
        exc: Exception,
        *,
        retryable: bool,
    ) -> None:
        try:
            stored = await self._store.fail_job(
                job.id,
                worker_id=self.worker_id,
                error=exc,
                retryable=retryable,
                retry_base_seconds=self.options.retry_base_seconds,
                retry_max_seconds=self.options.retry_max_seconds,
            )
        except JobLeaseLostError:
            logger.warning("Durable job failed after lease loss id={}", job.id)
            return
        except Exception:  # noqa: BLE001 - avoid killing sibling jobs on one DB failure.
            logger.exception("Could not persist durable job failure id={}", job.id)
            return
        logger.exception(
            "Durable job failed id={} kind={} state={} retryable={}",
            job.id,
            job.kind.value,
            stored.state.value,
            retryable,
        )

    async def _release_on_cancellation(
        self,
        job: DurableJob,
        lease_lost: asyncio.Event,
    ) -> None:
        if lease_lost.is_set():
            return
        try:
            await self._store.release_job(
                job.id,
                worker_id=self.worker_id,
                reason="Worker process cancelled before job completion.",
                retry_base_seconds=self.options.retry_base_seconds,
                retry_max_seconds=self.options.retry_max_seconds,
            )
        except JobLeaseLostError:
            logger.warning("Durable job cancelled after lease loss id={}", job.id)
        except Exception:  # noqa: BLE001 - lease expiry remains the fallback recovery path.
            logger.exception("Could not release cancelled durable job id={}", job.id)
