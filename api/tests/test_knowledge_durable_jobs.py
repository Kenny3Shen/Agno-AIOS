from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from api.persistence.durable_jobs import DurableJob, JobKind, JobState
from api.services.durable_job_service import JobExecutionContext, NonRetryableJobError
from api.services.knowledge_durable_jobs import (
    build_knowledge_ingest_payload,
    handle_knowledge_ingest_job,
    knowledge_ingest_idempotency_key,
)


def _job(payload: dict[str, object]) -> DurableJob:
    now = datetime.now(UTC)
    return DurableJob(
        id="job-1",
        kind=JobKind.KNOWLEDGE_INGEST,
        payload=payload,
        idempotency_key="knowledge:test",
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


def _actor() -> SimpleNamespace:
    return SimpleNamespace(
        id="user-1",
        email="user@example.test",
        role="user",
        is_superuser=False,
    )


def _context() -> JobExecutionContext:
    # The handler currently relies on worker-owned heartbeats, not the context.
    return cast(JobExecutionContext, object())


def _payload(operation: str, data: dict[str, object]) -> dict[str, object]:
    return build_knowledge_ingest_payload(
        operation=operation,
        actor=_actor(),
        owner_user_id="user-1",
        data=data,
        audit_action="knowledge.create",
        audit_resource_id="resource-1",
        audit_metadata={"async_ingest": True},
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


def test_idempotency_key_only_collapses_explicit_retries() -> None:
    first = knowledge_ingest_idempotency_key(
        operation="text",
        owner_user_id="user-1",
        request_key="request-123",
    )
    second = knowledge_ingest_idempotency_key(
        operation="text",
        owner_user_id="user-1",
        request_key="request-123",
    )

    assert first == second
    assert "request-123" not in first
    assert knowledge_ingest_idempotency_key(
        operation="text", owner_user_id="user-1"
    ) != knowledge_ingest_idempotency_key(operation="text", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_text_handler_runs_lifecycle_and_records_request_audit() -> None:
    payload = _payload(
        "text",
        {
            "title": "Runbook",
            "content": "restart the service",
            "source": "manual",
            "visibility": "private",
            "metadata": {"tag": "ops"},
            "ingest_options": {"chunk_size": 1200},
        },
    )
    lifecycle = SimpleNamespace(
        add_text_document_async=AsyncMock(return_value={"id": "doc-1"})
    )
    audit = AsyncMock()

    with (
        patch(
            "api.services.knowledge_durable_jobs.get_knowledge_base_lifecycle",
            return_value=lifecycle,
        ),
        patch(
            "api.services.knowledge_durable_jobs.record_audit_event_async",
            audit,
        ),
    ):
        result = await handle_knowledge_ingest_job(_job(payload), _context())

    assert result == {
        "operation": "text",
        "document_id": "doc-1",
        "owner_user_id": "user-1",
    }
    lifecycle.add_text_document_async.assert_awaited_once_with(
        title="Runbook",
        content="restart the service",
        source="manual",
        visibility="private",
        metadata={"tag": "ops"},
        owner_user_id="user-1",
        ingest_options={"chunk_size": 1200},
    )
    audit_call = audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs == {
        "action": "knowledge.create",
        "resource_type": "knowledge_document",
        "resource_id": "doc-1",
        "metadata": {"async_ingest": True},
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
    }
    assert audit_call.args[0].id == "user-1"
    assert audit_call.args[0].role == "user"


@pytest.mark.asyncio
async def test_handler_canonicalizes_legacy_superuser_job_actor() -> None:
    payload = _payload(
        "text",
        {
            "title": "Runbook",
            "content": "restart the service",
            "source": "manual",
            "visibility": "private",
            "metadata": {},
            "ingest_options": {},
        },
    )
    payload["actor"] = {
        "id": "user-1",
        "email": "user@example.test",
        "role": "author",
        "is_superuser": True,
    }
    lifecycle = SimpleNamespace(
        add_text_document_async=AsyncMock(return_value={"id": "doc-1"})
    )
    audit = AsyncMock()

    with (
        patch(
            "api.services.knowledge_durable_jobs.get_knowledge_base_lifecycle",
            return_value=lifecycle,
        ),
        patch(
            "api.services.knowledge_durable_jobs.record_audit_event_async",
            audit,
        ),
    ):
        await handle_knowledge_ingest_job(_job(payload), _context())

    audit_call = audit.await_args
    assert audit_call is not None
    assert audit_call.args[0].role == "admin"
    assert audit_call.args[0].is_superuser is True


@pytest.mark.asyncio
async def test_upload_handler_cleans_managed_file_after_retryable_failure() -> None:
    metadata = {
        "_tais_managed_upload": {
            "version": 1,
            "upload_id": "a" * 32,
            "file_name": "runbook.md",
        }
    }
    payload = _payload(
        "upload",
        {
            "path": "/shared/uploads/a/runbook.md",
            "title": "Runbook",
            "source": "upload:runbook.md",
            "visibility": "private",
            "metadata": metadata,
            "ingest_options": {},
        },
    )
    lifecycle = SimpleNamespace(
        add_file_document_async=AsyncMock(side_effect=RuntimeError("embedding unavailable"))
    )
    cleanup = AsyncMock(return_value=True)

    with (
        patch(
            "api.services.knowledge_durable_jobs.get_knowledge_base_lifecycle",
            return_value=lifecycle,
        ),
        patch(
            "api.services.knowledge_durable_jobs.remove_managed_upload_async",
            cleanup,
        ),
    ):
        with pytest.raises(RuntimeError, match="embedding unavailable"):
            await handle_knowledge_ingest_job(_job(payload), _context())

    cleanup.assert_awaited_once_with(metadata)


@pytest.mark.asyncio
async def test_replace_file_missing_document_is_terminal_and_cleans_upload() -> None:
    metadata = {
        "_tais_managed_upload": {
            "version": 1,
            "upload_id": "b" * 32,
            "file_name": "runbook.md",
        }
    }
    payload = _payload(
        "replace_file",
        {
            "doc_id": "missing",
            "path": "/shared/uploads/b/runbook.md",
            "title": "",
            "source": "",
            "visibility": "",
            "metadata": metadata,
            "ingest_options": {},
        },
    )
    lifecycle = SimpleNamespace(replace_document_file_async=AsyncMock(return_value=None))
    cleanup = AsyncMock(return_value=True)

    with (
        patch(
            "api.services.knowledge_durable_jobs.get_knowledge_base_lifecycle",
            return_value=lifecycle,
        ),
        patch(
            "api.services.knowledge_durable_jobs.remove_managed_upload_async",
            cleanup,
        ),
    ):
        with pytest.raises(NonRetryableJobError, match="知识文档不存在"):
            await handle_knowledge_ingest_job(_job(payload), _context())

    cleanup.assert_awaited_once_with(metadata)
