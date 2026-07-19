from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field, model_validator

from api.auth.claims import actor_id, actor_role
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.users import current_active_user
from api.services.approvals_service import (
    ApprovalListParams,
    ApprovalResolveConflictError,
    get_approval_record,
    get_pending_approval_count,
    list_approvals_native,
    list_combined_approvals_native,
    resolve_approval_record,
)
from api.services.security_policy import PolicyAuditEvent, record_policy_event
from api.services.security_run_runtime import resume_security_run
from api.services.workflow_run_runtime import (
    is_workflow_step_approval,
    schedule_workflow_resume,
)
from api.services.upload_approval_service import (
    can_view_submission_approval,
    list_submission_approvals_page,
    preview_skill_submission,
    resolve_submission_approval,
)

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


class ApprovalResolveRequest(BaseModel):
    status: Literal["approved", "rejected"]
    resolution_data: dict[str, object] | None = None
    rejection_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> ApprovalResolveRequest:
        if self.status == "rejected" and not (self.rejection_reason or "").strip():
            raise ValueError("A rejection reason is required")
        return self


class SubmissionApprovalResolveRequest(BaseModel):
    status: Literal["approved", "rejected"]
    rejection_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> SubmissionApprovalResolveRequest:
        if self.status == "rejected" and not (self.rejection_reason or "").strip():
            raise ValueError("A rejection reason is required")
        return self


def _resolver_id(user: User) -> str:
    return str(getattr(user, "email", "") or actor_id(user) or "system")


def _resolver_email(user: User) -> str:
    return str(getattr(user, "email", "") or "")


def _is_security_chat_approval(approval: Mapping[str, object]) -> bool:
    return (
        str(approval.get("source_type") or "") == "agent"
        and str(approval.get("agent_id") or "") == "security-operations"
        and bool(str(approval.get("run_id") or ""))
        and bool(str(approval.get("session_id") or ""))
        and bool(str(approval.get("user_id") or ""))
    )


@router.get("/submissions")
async def list_submission_approval_requests(
    status: Literal["pending", "approved", "rejected"] | None = None,
    page: int = 1,
    limit: int = 100,
    user: User = Depends(current_active_user),
):
    """List staged Skill/MCP uploads as ``{data, meta}``; non-admins see own only."""
    submitted_by = None if actor_role(user) == "admin" else actor_id(user)
    return await list_submission_approvals_page(
        status,
        submitted_by=submitted_by,
        page=page,
        limit=limit,
    )


@router.post("/submissions/{approval_id}/resolve")
async def resolve_submission_approval_request(
    approval_id: str,
    body: SubmissionApprovalResolveRequest,
    request: Request,
    user: User = Depends(require_scope("approvals:write")),
):
    approval = await resolve_submission_approval(
        approval_id,
        status=body.status,
        resolved_by=actor_id(user) or "system",
        resolved_by_email=_resolver_email(user),
        rejection_reason=body.rejection_reason,
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action=f"upload_approval.{body.status}",
            resource_type=str(approval["resource_type"]),
            resource_id=approval_id,
            metadata={"submitted_by": approval["submitted_by"], "rejection_reason": approval.get("rejection_reason")},
        ),
        request,
    )
    return approval


@router.get("/submissions/{approval_id}/skill-preview")
async def preview_skill_submission_request(
    approval_id: str,
    user: User = Depends(current_active_user),
):
    if not await can_view_submission_approval(
        approval_id, submitted_by=actor_id(user), is_admin=actor_role(user) == "admin"
    ):
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        return await preview_skill_submission(approval_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_approvals(
    status: str | None = None,
    source_type: str | None = None,
    approval_type: str | None = None,
    pause_type: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    workflow_id: str | None = None,
    user_id: str | None = None,
    schedule_id: str | None = None,
    run_id: str | None = None,
    combined: bool = False,
    page: int = 1,
    limit: int = 50,
    user: User = Depends(require_scope("approvals:read")),
):
    """List approvals with Agno-native ``data`` / ``meta``.

    ``combined=true``: upload submissions first, then HITL (workbench kind=all).
    Otherwise HITL-only (optional ``source_type`` etc.).
    """
    try:
        if combined:
            return await list_combined_approvals_native(
                status=status,
                page=page,
                limit=limit,
                actor=user,
            )
        return await list_approvals_native(
            params=ApprovalListParams(
                status=status,
                source_type=source_type,
                approval_type=approval_type,
                pause_type=pause_type,
                agent_id=agent_id,
                team_id=team_id,
                workflow_id=workflow_id,
                user_id=user_id,
                schedule_id=schedule_id,
                run_id=run_id,
                page=page,
                limit=limit,
            ),
            actor=user,
        )
    except Exception as exc:
        logger.error("获取 Agno 审批列表失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to load approvals") from exc


@router.get("/count")
async def get_approval_count(
    user_id: str | None = None,
    user: User = Depends(require_scope("approvals:read")),
):
    """Pending HITL approval count (Agno-native ``{ count }``).

    Non-admins always count their own rows; admins may filter by ``user_id``.
    Must be registered before ``/{approval_id}`` so ``count`` is not captured
    as an approval id.
    """
    try:
        count = await get_pending_approval_count(actor=user, user_id=user_id)
    except Exception as exc:
        logger.error("获取 Agno 待审批数量失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to load approval count") from exc
    return {"count": count}


@router.get("/{approval_id}")
async def get_approval(
    approval_id: str,
    user: User = Depends(require_scope("approvals:read")),
):
    try:
        approval = await get_approval_record(approval_id)
    except Exception as exc:
        logger.error("获取 Agno 审批详情失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to load approval") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if actor_role(user) != "admin" and approval.get("user_id") != actor_id(user):
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    body: ApprovalResolveRequest,
    request: Request,
    user: User = Depends(require_scope("approvals:write")),
):
    try:
        resolution_data = dict(body.resolution_data or {})
        if body.status == "rejected":
            reason = (body.rejection_reason or "").strip()
            # Agno convention: only ``note`` (no dual rejection_reason key).
            resolution_data["note"] = reason
        approval = await resolve_approval_record(
            approval_id,
            status=body.status,
            resolved_by=_resolver_id(user),
            resolution_data=resolution_data or None,
        )
    except ApprovalResolveConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("处理 Agno 审批失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to resolve approval") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if _is_security_chat_approval(approval):
        try:
            await resume_security_run(approval_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("调度 HITL Run 恢复失败: {}", exc)
            raise HTTPException(status_code=500, detail="Failed to schedule approval run") from exc
    elif is_workflow_step_approval(dict(approval)):
        try:
            await schedule_workflow_resume(approval_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("调度 Workflow 恢复失败: {}", exc)
            raise HTTPException(status_code=500, detail="Failed to schedule workflow resume") from exc
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action=f"approvals.{body.status}",
            resource_type="approval",
            resource_id=approval_id,
            metadata={
                "status": body.status,
                "run_id": approval.get("run_id"),
                "session_id": approval.get("session_id"),
                "source_type": approval.get("source_type"),
            },
        ),
        request,
    )
    return await get_approval_record(approval_id) or approval


@router.post("/{approval_id}/resume")
async def retry_approval_resume(
    approval_id: str,
    request: Request,
    user: User = Depends(require_scope("approvals:write")),
):
    """Retry a failed continuation without granting a new approval."""
    approval = await get_approval_record(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if not _is_security_chat_approval(approval):
        raise HTTPException(status_code=400, detail="Approval is not a resumable security chat run")
    if approval.get("status") not in {"approved", "rejected"}:
        raise HTTPException(status_code=409, detail="Approval must be resolved before resuming")
    if str(approval.get("run_status") or "").upper() != "ERROR":
        raise HTTPException(status_code=409, detail="Only failed approval runs can be retried")
    try:
        await resume_security_run(approval_id, retry_error=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("重试恢复 HITL Run 失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to resume approval run") from exc
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="approvals.resume",
            resource_type="approval",
            resource_id=approval_id,
            metadata={"run_id": approval.get("run_id"), "run_status": "RUNNING"},
        ),
        request,
    )
    refreshed = await get_approval_record(approval_id)
    return refreshed or approval
