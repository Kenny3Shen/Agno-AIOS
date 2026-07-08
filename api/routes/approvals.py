from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from api.auth.claims import actor_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.approvals_service import (
    ApprovalListParams,
    ApprovalResolveConflictError,
    get_approval_record,
    list_approvals_payload,
    resolve_approval_record,
)
from api.services.security_policy import PolicyAuditEvent, record_policy_event

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


class ApprovalResolveRequest(BaseModel):
    status: Literal["approved", "rejected"]
    resolution_data: dict[str, object] | None = None


def _resolver_id(user: User) -> str:
    return str(getattr(user, "email", "") or actor_id(user) or "system")


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
    page: int = 1,
    limit: int = 50,
    user: User = Depends(require_scope("approvals:read")),
):
    try:
        return await list_approvals_payload(
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
        logger.error(f"获取 Agno 审批列表失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load approvals") from exc


@router.get("/{approval_id}")
async def get_approval(
    approval_id: str,
    user: User = Depends(require_scope("approvals:read")),
):
    del user
    try:
        approval = await get_approval_record(approval_id)
    except Exception as exc:
        logger.error(f"获取 Agno 审批详情失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load approval") from exc
    if approval is None:
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
        approval = await resolve_approval_record(
            approval_id,
            status=body.status,
            resolved_by=_resolver_id(user),
            resolution_data=body.resolution_data,
        )
    except ApprovalResolveConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"处理 Agno 审批失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to resolve approval") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
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
    return approval
