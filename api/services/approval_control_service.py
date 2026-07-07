from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from api.auth.claims import scope_user_id
from api.services.postgres_store import get_async_agno_postgres_db

ApprovalRecord = dict[str, Any]
ApprovalPayload = dict[str, Any]


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


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC).isoformat()
        except (OSError, ValueError):
            return str(value)
    return str(value)


def _compact(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _row_dict(raw_row: Any) -> dict[str, Any]:
    if isinstance(raw_row, dict):
        return dict(raw_row)
    model_dump = getattr(raw_row, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    to_dict = getattr(raw_row, "to_dict", None)
    if callable(to_dict):
        dumped = to_dict()
        if isinstance(dumped, dict):
            return dict(dumped)
    try:
        return dict(vars(raw_row))
    except TypeError:
        return {}


def _metric(label: str, value: Any, hint: str = "", tone: str = "blue") -> dict[str, Any]:
    return {"label": label, "value": value, "hint": hint, "tone": tone}


def normalize_approval(raw_approval: Any) -> ApprovalRecord:
    row = _row_dict(raw_approval)
    return {
        "id": str(row.get("id") or ""),
        "run_id": row.get("run_id"),
        "session_id": row.get("session_id"),
        "status": str(row.get("status") or ""),
        "source_type": row.get("source_type"),
        "approval_type": row.get("approval_type"),
        "pause_type": row.get("pause_type"),
        "tool_name": row.get("tool_name"),
        "tool_args": row.get("tool_args") if isinstance(row.get("tool_args"), dict) else {},
        "expires_at": row.get("expires_at"),
        "agent_id": row.get("agent_id"),
        "team_id": row.get("team_id"),
        "workflow_id": row.get("workflow_id"),
        "user_id": row.get("user_id"),
        "schedule_id": row.get("schedule_id"),
        "schedule_run_id": row.get("schedule_run_id"),
        "source_name": row.get("source_name"),
        "requirements": row.get("requirements") if isinstance(row.get("requirements"), list) else [],
        "context": row.get("context") if isinstance(row.get("context"), dict) else {},
        "resolution_data": row.get("resolution_data") if isinstance(row.get("resolution_data"), dict) else None,
        "resolved_by": row.get("resolved_by"),
        "resolved_at": row.get("resolved_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "run_status": row.get("run_status"),
    }


def approval_record_summary(approval: ApprovalRecord) -> dict[str, Any]:
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
    return {
        "id": str(approval.get("id") or ""),
        "title": _compact(approval.get("tool_name") or approval.get("id") or "Approval"),
        "subtitle": " / ".join(subtitle_parts),
        "status": str(approval.get("status") or "pending"),
        "meta": {
            "source_type": approval.get("source_type"),
            "approval_type": approval.get("approval_type"),
            "pause_type": approval.get("pause_type"),
            "run_status": approval.get("run_status"),
            "agent_id": approval.get("agent_id"),
            "team_id": approval.get("team_id"),
            "workflow_id": approval.get("workflow_id"),
            "schedule_id": approval.get("schedule_id"),
        },
        "updated_at": _iso(updated_at),
    }


def _scoped_user_id(actor: Any | None, requested_user_id: str | None) -> str | None:
    return scope_user_id(actor, requested_user_id)


def _query_kwargs(params: ApprovalListParams, actor: Any | None) -> dict[str, Any]:
    safe_limit = max(1, min(int(params.limit or 50), 100))
    safe_page = max(1, int(params.page or 1))
    values = asdict(params)
    values["limit"] = safe_limit
    values["page"] = safe_page
    values["user_id"] = _scoped_user_id(actor, params.user_id)
    return values


async def list_approvals(
    *,
    params: ApprovalListParams | None = None,
    actor: Any | None = None,
) -> tuple[list[ApprovalRecord], int, dict[str, Any]]:
    effective_params = params or ApprovalListParams()
    kwargs = _query_kwargs(effective_params, actor)
    rows, total = await get_async_agno_postgres_db().get_approvals(**kwargs)
    return [normalize_approval(row) for row in rows], int(total), kwargs


async def list_approvals_payload(
    *,
    params: ApprovalListParams | None = None,
    actor: Any | None = None,
) -> ApprovalPayload:
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
            _metric("Pending", pending, "等待管理员处理", "red" if pending else "green"),
            _metric("Approved", approved, "当前页已批准", "green"),
            _metric("Rejected", rejected, "当前页已拒绝", "red" if rejected else "blue"),
            _metric("Total", total, "当前筛选总数", "blue"),
        ],
        "records": [approval_record_summary(approval) for approval in approvals],
        "generated_at": _iso(datetime.now(UTC)),
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
    return normalize_approval(approval) if approval is not None else None


async def resolve_approval_record(
    approval_id: str,
    *,
    status: str,
    resolved_by: str,
    resolution_data: dict[str, Any] | None,
) -> ApprovalRecord | None:
    if status not in {"approved", "rejected"}:
        raise ValueError(f"Unsupported approval status: {status}")
    db = get_async_agno_postgres_db()
    existing = await db.get_approval(approval_id)
    if existing is None:
        return None
    resolved = await db.update_approval(
        approval_id,
        expected_status="pending",
        status=status,
        resolved_by=resolved_by,
        resolved_at=int(time.time()),
        resolution_data=resolution_data,
    )
    if resolved is None:
        raise ApprovalResolveConflictError("Approval is not pending")
    return normalize_approval(resolved)
