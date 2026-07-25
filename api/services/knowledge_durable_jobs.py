"""Durable payloads and worker handler for Knowledge ingestion.

Knowledge ingestion is intentionally represented as data rather than a closure:
the HTTP process can return as soon as the upload is persisted, while a separate
worker may safely claim, retry, or recover the expensive Docling/vectorisation
operation after an API restart.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from api.auth.claims import Role, actor_role, normalize_actor_role
from api.persistence.durable_jobs import DurableJob, JobKind
from api.services.audit_service import record_audit_event_async
from api.services.durable_job_service import (
    DurableJobRegistry,
    JobExecutionContext,
    NonRetryableJobError,
    enqueue_durable_job,
)
from api.services.knowledge_service import get_knowledge_base_lifecycle
from api.services.knowledge_upload_service import remove_managed_upload_async

KNOWLEDGE_INGEST_TIMEOUT_SECONDS = 15 * 60
_OPERATIONS = frozenset(
    {
        "text",
        "upload",
        "rebuild",
        "replace_text",
        "replace_file",
    }
)


@dataclass(frozen=True, slots=True)
class KnowledgeJobActor:
    """Minimal, serialisable actor reconstructed by the worker for audit/RBAC."""

    id: str
    email: str = ""
    role: Role = "user"
    is_superuser: bool = False


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NonRetryableJobError(f"knowledge_ingest payload {field} must be an object")
    return {str(key): item for key, item in value.items()}


def _optional_mapping(value: object, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    return _mapping(value, field=field)


def _text(value: object, *, field: str, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise NonRetryableJobError(f"knowledge_ingest payload {field} must be a string")
    result = value.strip()
    if required and not result:
        raise NonRetryableJobError(f"knowledge_ingest payload {field} is required")
    return result


def _optional_bool(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    raise NonRetryableJobError(f"knowledge_ingest payload {field} must be a boolean")


def _actor(payload: Mapping[str, Any]) -> KnowledgeJobActor:
    raw = _mapping(payload.get("actor"), field="actor")
    is_superuser = _optional_bool(raw.get("is_superuser"), field="actor.is_superuser")
    return KnowledgeJobActor(
        id=_text(raw.get("id"), field="actor.id", required=True),
        email=_text(raw.get("email"), field="actor.email"),
        role=normalize_actor_role(
            _text(raw.get("role"), field="actor.role"),
            is_superuser=is_superuser,
        ),
        is_superuser=is_superuser,
    )


def build_knowledge_ingest_payload(
    *,
    operation: str,
    actor: Any,
    owner_user_id: str | None,
    data: Mapping[str, object],
    audit_action: str,
    audit_resource_id: str,
    audit_metadata: Mapping[str, object] | None = None,
    ip_address: str = "",
    user_agent: str = "",
) -> dict[str, Any]:
    """Build the JSON-only contract shared by API producers and the worker."""
    normalized_operation = operation.strip()
    if normalized_operation not in _OPERATIONS:
        raise ValueError(f"Unsupported knowledge ingest operation: {operation!r}")
    actor_id = str(getattr(actor, "id", "") or "").strip()
    if not actor_id:
        raise ValueError("knowledge ingest actor id is required")
    return {
        "operation": normalized_operation,
        "actor": {
            "id": actor_id,
            "email": str(getattr(actor, "email", "") or "").strip(),
            "role": actor_role(actor),
            "is_superuser": bool(getattr(actor, "is_superuser", False)),
        },
        "owner_user_id": (owner_user_id or "").strip() or None,
        "data": {str(key): value for key, value in data.items()},
        "audit": {
            "action": audit_action,
            "resource_id": audit_resource_id,
            "metadata": {
                str(key): value for key, value in (audit_metadata or {}).items()
            },
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    }


def knowledge_ingest_idempotency_key(
    *,
    operation: str,
    owner_user_id: str,
    request_key: str | None = None,
) -> str:
    """Create a bounded, opaque key for optional HTTP retry idempotency.

    A fresh key intentionally permits a user to submit the same document again;
    only an explicit ``Idempotency-Key`` requests duplicate HTTP retry collapse.
    """
    normalized_operation = operation.strip()
    owner = owner_user_id.strip()
    supplied = (request_key or "").strip()
    if supplied:
        digest = hashlib.sha256(
            f"{owner}\x00{normalized_operation}\x00{supplied}".encode()
        ).hexdigest()
        return f"knowledge:{normalized_operation}:{owner}:{digest}"
    return f"knowledge:{normalized_operation}:{owner}:{uuid4()}"


async def enqueue_knowledge_ingest_job(
    *,
    payload: Mapping[str, Any],
    idempotency_key: str,
    priority: int = 10,
) -> DurableJob:
    """Queue a validated Knowledge operation for the standalone worker."""
    # Validate producer payload before writing an unrecoverable database row.
    _parse_payload(payload)
    return await enqueue_durable_job(
        kind=JobKind.KNOWLEDGE_INGEST,
        payload=payload,
        idempotency_key=idempotency_key,
        max_attempts=3,
        priority=priority,
    )


def _parse_payload(raw: Mapping[str, Any]) -> tuple[
    str,
    KnowledgeJobActor,
    str | None,
    dict[str, Any],
    dict[str, Any],
]:
    payload = _mapping(raw, field="root")
    operation = _text(payload.get("operation"), field="operation", required=True)
    if operation not in _OPERATIONS:
        raise NonRetryableJobError(f"Unsupported knowledge ingest operation: {operation!r}")
    owner_user_id = _text(payload.get("owner_user_id"), field="owner_user_id") or None
    data = _mapping(payload.get("data"), field="data")
    audit = _mapping(payload.get("audit"), field="audit")
    _text(audit.get("action"), field="audit.action", required=True)
    _text(audit.get("resource_id"), field="audit.resource_id", required=True)
    _optional_mapping(audit.get("metadata"), field="audit.metadata")
    _text(audit.get("ip_address"), field="audit.ip_address")
    _text(audit.get("user_agent"), field="audit.user_agent")
    return operation, _actor(payload), owner_user_id, data, audit


async def _execute_operation(
    *,
    operation: str,
    actor: KnowledgeJobActor,
    owner_user_id: str | None,
    data: Mapping[str, Any],
) -> Mapping[str, Any]:
    lifecycle = get_knowledge_base_lifecycle()
    metadata = _optional_mapping(data.get("metadata"), field="data.metadata")
    ingest_options = _optional_mapping(
        data.get("ingest_options"), field="data.ingest_options"
    )

    if operation == "text":
        return await lifecycle.add_text_document_async(
            title=_text(data.get("title"), field="data.title", required=True),
            content=_text(data.get("content"), field="data.content", required=True),
            source=_text(data.get("source"), field="data.source") or "manual",
            visibility=_text(data.get("visibility"), field="data.visibility") or "private",
            metadata=metadata,
            owner_user_id=owner_user_id,
            ingest_options=ingest_options or None,
        )

    if operation == "upload":
        return await lifecycle.add_file_document_async(
            path=_text(data.get("path"), field="data.path", required=True),
            title=_text(data.get("title"), field="data.title") or None,
            source=_text(data.get("source"), field="data.source") or None,
            metadata=metadata,
            owner_user_id=owner_user_id,
            visibility=_text(data.get("visibility"), field="data.visibility") or "private",
            ingest_options=ingest_options or None,
        )

    doc_id = _text(data.get("doc_id"), field="data.doc_id", required=True)
    common = {
        "owner_user_id": owner_user_id,
        "user": actor,
        "title": _text(data.get("title"), field="data.title") or None,
        "source": _text(data.get("source"), field="data.source") or None,
        "visibility": _text(data.get("visibility"), field="data.visibility") or None,
        "metadata": metadata,
        "ingest_options": ingest_options or None,
    }
    if operation == "rebuild":
        result = await lifecycle.rebuild_document_async(doc_id, **common)
    elif operation == "replace_text":
        result = await lifecycle.replace_document_source_async(
            doc_id,
            content=_text(data.get("content"), field="data.content", required=True),
            file_name=_text(data.get("file_name"), field="data.file_name", required=True),
            **common,
        )
    elif operation == "replace_file":
        result = await lifecycle.replace_document_file_async(
            doc_id,
            path=_text(data.get("path"), field="data.path", required=True),
            **common,
        )
    else:  # Defensive: _parse_payload already restricts the operation.
        raise NonRetryableJobError(f"Unsupported knowledge ingest operation: {operation!r}")
    if result is None:
        raise LookupError("知识文档不存在或无权修改")
    return result


async def handle_knowledge_ingest_job(
    job: DurableJob,
    _context: JobExecutionContext,
) -> dict[str, Any]:
    """Execute one serialised Knowledge operation and emit the audit record."""
    operation, actor, owner_user_id, data, audit = _parse_payload(job.payload)
    upload_metadata = _optional_mapping(data.get("metadata"), field="data.metadata")
    try:
        async with asyncio.timeout(KNOWLEDGE_INGEST_TIMEOUT_SECONDS):
            document = await _execute_operation(
                operation=operation,
                actor=actor,
                owner_user_id=owner_user_id,
                data=data,
            )
    except TimeoutError as exc:
        raise RuntimeError("Knowledge ingest timed out") from exc
    except (LookupError, ValueError, FileNotFoundError) as exc:
        # Bad request data, missing source snapshots, and inaccessible persisted
        # uploads cannot be repaired by automatically retrying the same payload.
        if operation in {"upload", "replace_file"}:
            await remove_managed_upload_async(upload_metadata)
        raise NonRetryableJobError(str(exc) or type(exc).__name__) from exc
    except Exception:
        # Failed initial upload/replace must not leave an orphaned managed file.
        if operation in {"upload", "replace_file"}:
            await remove_managed_upload_async(upload_metadata)
        raise

    document_id = _text(document.get("id"), field="result.id", required=True)
    await record_audit_event_async(
        actor,
        action=_text(audit.get("action"), field="audit.action", required=True),
        resource_type="knowledge_document",
        resource_id=document_id
        or _text(audit.get("resource_id"), field="audit.resource_id", required=True),
        metadata=_optional_mapping(audit.get("metadata"), field="audit.metadata"),
        ip_address=_text(audit.get("ip_address"), field="audit.ip_address"),
        user_agent=_text(audit.get("user_agent"), field="audit.user_agent"),
    )
    return {
        "operation": operation,
        "document_id": document_id,
        "owner_user_id": owner_user_id or "",
    }


def register_knowledge_job_handler(registry: DurableJobRegistry) -> None:
    """Register the trusted Knowledge handler into a worker registry."""
    registry.register(JobKind.KNOWLEDGE_INGEST, handle_knowledge_ingest_job)
