from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict, cast
from uuid import UUID

from agno.run.approval import aresolve_approval
from sqlalchemy import select

from api.auth.claims import ActorLike, scope_user_id
from api.auth.database import async_session_maker
from api.auth.models import User
from api.services.page_payloads import (
    PageMetric,
    PageRecord,
    compact,
    iso,
    metric,
    now_utc,
    record,
    row_dict,
)
from api.services.postgres_store import get_async_agno_postgres_db

class ApprovalRecord(TypedDict):
    id: str
    status: str
    run_id: NotRequired[str | None]
    session_id: NotRequired[str | None]
    source_type: NotRequired[str | None]
    approval_type: NotRequired[str | None]
    pause_type: NotRequired[str | None]
    tool_name: NotRequired[str | None]
    tool_args: NotRequired[dict[str, object]]
    expires_at: NotRequired[object]
    agent_id: NotRequired[str | None]
    team_id: NotRequired[str | None]
    workflow_id: NotRequired[str | None]
    user_id: NotRequired[str | None]
    schedule_id: NotRequired[str | None]
    schedule_run_id: NotRequired[str | None]
    source_name: NotRequired[str | None]
    requirements: NotRequired[list[object]]
    context: NotRequired[dict[str, object]]
    resolution_data: NotRequired[dict[str, object] | None]
    resolved_by: NotRequired[str | dict[str, str] | None]
    resolved_at: NotRequired[object]
    created_at: NotRequired[object]
    updated_at: NotRequired[object]
    run_status: NotRequired[str | None]
    submitted_by: NotRequired[dict[str, str] | None]
    submitted_by_email: NotRequired[str | None]
    resolved_by_email: NotRequired[str | None]


class ApprovalQueryKwargs(TypedDict):
    status: str | None
    source_type: str | None
    approval_type: str | None
    pause_type: str | None
    agent_id: str | None
    team_id: str | None
    workflow_id: str | None
    user_id: str | None
    schedule_id: str | None
    run_id: str | None
    limit: int
    page: int


class ApprovalMeta(TypedDict):
    page: int
    limit: int
    total: int
    pending: int


class ApprovalListResponse(TypedDict):
    module: str
    title: str
    description: str
    status: str
    metrics: list[PageMetric]
    records: list[PageRecord]
    generated_at: str
    approvals: list[ApprovalRecord]
    approval_filters: ApprovalQueryKwargs
    approval_meta: ApprovalMeta


class ApprovalResolveConflictError(Exception):
    """Raised when an approval is no longer pending at resolve time."""


@dataclass(frozen=True)
class ApprovalListParams:
    status: str | None = None
    source_type: str | None = None
    approval_type: str | None = None
    pause_type: str | None = None
    agent_id: str | None = None
    team_id: str | None = None
    workflow_id: str | None = None
    user_id: str | None = None
    schedule_id: str | None = None
    run_id: str | None = None
    limit: int = 50
    page: int = 1


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _object_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _optional_object_mapping(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return None


def _object_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def normalize_approval(raw_approval: object) -> ApprovalRecord:
    row = row_dict(raw_approval)
    return {
        "id": str(row.get("id") or ""),
        "run_id": _optional_str(row.get("run_id")),
        "session_id": _optional_str(row.get("session_id")),
        "status": str(row.get("status") or ""),
        "source_type": _optional_str(row.get("source_type")),
        "approval_type": _optional_str(row.get("approval_type")),
        "pause_type": _optional_str(row.get("pause_type")),
        "tool_name": _optional_str(row.get("tool_name")),
        "tool_args": _object_mapping(row.get("tool_args")),
        "expires_at": row.get("expires_at"),
        "agent_id": _optional_str(row.get("agent_id")),
        "team_id": _optional_str(row.get("team_id")),
        "workflow_id": _optional_str(row.get("workflow_id")),
        "user_id": _optional_str(row.get("user_id")),
        "schedule_id": _optional_str(row.get("schedule_id")),
        "schedule_run_id": _optional_str(row.get("schedule_run_id")),
        "source_name": _optional_str(row.get("source_name")),
        "requirements": _object_list(row.get("requirements")),
        "context": _object_mapping(row.get("context")),
        "resolution_data": _optional_object_mapping(row.get("resolution_data")),
        "resolved_by": _optional_str(row.get("resolved_by")),
        "resolved_at": row.get("resolved_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "run_status": _optional_str(row.get("run_status")),
    }


async def lookup_user_emails(user_ids: list[str]) -> dict[str, str]:
    """Resolve auth user UUIDs to emails for HITL submitter display."""
    ids: list[UUID] = []
    for value in user_ids:
        text = (value or "").strip()
        if not text:
            continue
        try:
            ids.append(UUID(text))
        except ValueError:
            continue
    if not ids:
        return {}
    async with async_session_maker() as session:
        # Mapped columns are runtime SQLAlchemy expressions; cast for static checkers.
        user_id_col = cast(Any, User.id)
        email_col = cast(Any, User.email)
        rows = (await session.execute(select(user_id_col, email_col).where(user_id_col.in_(ids)))).all()
    return {str(user_id): str(email or "") for user_id, email in rows}


def _actor_payload(user_id: str | None, email: str | None) -> dict[str, str] | None:
    actor_id = (user_id or "").strip()
    actor_email = (email or "").strip()
    if not actor_id and not actor_email:
        return None
    return {"id": actor_id, "email": actor_email}


async def enrich_approval_actors(
    approval: ApprovalRecord,
    *,
    email_by_id: Mapping[str, str] | None = None,
) -> ApprovalRecord:
    """Attach submitted_by / resolved_by email fields used by the Approvals UI."""
    user_id = _optional_str(approval.get("user_id"))
    resolved_by = approval.get("resolved_by")
    resolved_id = _optional_str(resolved_by) if not isinstance(resolved_by, Mapping) else _optional_str(
        resolved_by.get("id")
    )
    resolved_email_hint = (
        _optional_str(resolved_by.get("email"))
        if isinstance(resolved_by, Mapping)
        else (_optional_str(resolved_by) if isinstance(resolved_by, str) and "@" in resolved_by else None)
    )

    emails = dict(email_by_id or {})
    missing = [value for value in (user_id, resolved_id) if value and value not in emails and "@" not in value]
    if missing:
        emails.update(await lookup_user_emails(missing))

    submitter_email = emails.get(user_id or "", "") if user_id else ""
    if resolved_email_hint and "@" in resolved_email_hint:
        resolved_email = resolved_email_hint
    else:
        resolved_email = emails.get(resolved_id or "", "") if resolved_id else ""

    return {
        **approval,
        "submitted_by": _actor_payload(user_id, submitter_email),
        "submitted_by_email": submitter_email or None,
        "resolved_by": _actor_payload(resolved_id or resolved_email, resolved_email) if (resolved_id or resolved_email) else None,
        "resolved_by_email": resolved_email or None,
    }


async def enrich_approval(approval: ApprovalRecord) -> ApprovalRecord:
    return await enrich_approval_actors(approval)


def approval_record_summary(approval: ApprovalRecord) -> PageRecord:
    subtitle_parts = [
        str(value)
        for value in (
            approval.get("source_name") or approval.get("source_type"),
            approval.get("user_id"),
            approval.get("run_id"),
        )
        if value
    ]
    updated_at = approval.get("updated_at") or approval.get("resolved_at") or approval.get("created_at")
    return record(
        record_id=str(approval.get("id") or ""),
        title=compact(approval.get("tool_name") or approval.get("id") or "Approval"),
        subtitle=" / ".join(subtitle_parts),
        status=str(approval.get("status") or "pending"),
        meta={
            "source_type": approval.get("source_type"),
            "approval_type": approval.get("approval_type"),
            "pause_type": approval.get("pause_type"),
            "run_status": approval.get("run_status"),
            "agent_id": approval.get("agent_id"),
            "team_id": approval.get("team_id"),
            "workflow_id": approval.get("workflow_id"),
            "schedule_id": approval.get("schedule_id"),
        },
        updated_at=updated_at,
    )


def _scoped_user_id(actor: ActorLike | None, requested_user_id: str | None) -> str | None:
    return scope_user_id(actor, requested_user_id)


def _query_kwargs(params: ApprovalListParams, actor: ActorLike | None) -> ApprovalQueryKwargs:
    safe_limit = max(1, min(int(params.limit or 50), 100))
    safe_page = max(1, int(params.page or 1))
    return {
        "status": params.status,
        "source_type": params.source_type,
        "approval_type": params.approval_type,
        "pause_type": params.pause_type,
        "agent_id": params.agent_id,
        "team_id": params.team_id,
        "workflow_id": params.workflow_id,
        "user_id": _scoped_user_id(actor, params.user_id),
        "schedule_id": params.schedule_id,
        "run_id": params.run_id,
        "limit": safe_limit,
        "page": safe_page,
    }


async def list_approvals(
    *,
    params: ApprovalListParams | None = None,
    actor: ActorLike | None = None,
) -> tuple[list[ApprovalRecord], int, ApprovalQueryKwargs]:
    effective_params = params or ApprovalListParams()
    kwargs = _query_kwargs(effective_params, actor)
    rows, total = await get_async_agno_postgres_db().get_approvals(**kwargs)
    normalized = [normalize_approval(row) for row in rows]
    email_ids = [
        value
        for approval in normalized
        for value in (approval.get("user_id"), approval.get("resolved_by") if isinstance(approval.get("resolved_by"), str) else None)
        if isinstance(value, str) and value and "@" not in value
    ]
    email_by_id = await lookup_user_emails(email_ids)
    approvals = [
        await enrich_approval_actors(approval, email_by_id=email_by_id)
        for approval in normalized
    ]
    return approvals, int(total), kwargs


async def list_approvals_payload(
    *,
    params: ApprovalListParams | None = None,
    actor: ActorLike | None = None,
) -> ApprovalListResponse:
    approvals, total, kwargs = await list_approvals(params=params, actor=actor)
    pending = int(
        await get_async_agno_postgres_db().get_pending_approval_count(
            user_id=kwargs.get("user_id")
        )
    )
    approved = sum(1 for approval in approvals if approval["status"] == "approved")
    rejected = sum(1 for approval in approvals if approval["status"] == "rejected")
    return {
        "module": "approvals",
        "title": "Approvals",
        "description": "Agno HITL 审批请求、工具调用确认和处理历史。",
        "status": "ready",
        "metrics": [
            metric("Pending", pending, "等待管理员处理", "red" if pending else "green"),
            metric("Approved", approved, "当前页已批准", "green"),
            metric("Rejected", rejected, "当前页已拒绝", "red" if rejected else "blue"),
            metric("Total", total, "当前筛选总数", "blue"),
        ],
        "records": [approval_record_summary(approval) for approval in approvals],
        "generated_at": iso(now_utc()),
        "approvals": approvals,
        "approval_filters": kwargs,
        "approval_meta": {
            "page": kwargs["page"],
            "limit": kwargs["limit"],
            "total": total,
            "pending": pending,
        },
    }


async def get_approval_record(approval_id: str) -> ApprovalRecord | None:
    approval = await get_async_agno_postgres_db().get_approval(approval_id)
    return await enrich_approval(normalize_approval(approval)) if approval is not None else None


async def resolve_approval_record(
    approval_id: str,
    *,
    status: str,
    resolved_by: str,
    resolution_data: dict[str, object] | None,
) -> ApprovalRecord | None:
    if status not in {"approved", "rejected"}:
        raise ValueError(f"Unsupported approval status: {status}")
    db = get_async_agno_postgres_db()
    existing = await db.get_approval(approval_id)
    if existing is None:
        return None
    # Agno-native helper used by Slack HITL and other interfaces.
    resolved = await aresolve_approval(
        db,
        approval_id,
        status=status,
        resolved_by=resolved_by,
        resolved_at=int(time.time()),
        resolution_data=resolution_data,
    )
    if resolved is None:
        raise ApprovalResolveConflictError("Approval is not pending")
    return await enrich_approval(normalize_approval(resolved))
