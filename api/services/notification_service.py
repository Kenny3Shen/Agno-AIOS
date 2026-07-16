from __future__ import annotations

from uuid import UUID

from loguru import logger
from sqlalchemy import text

from api.auth.database import async_session_maker
from api.persistence.notifications import create_notifications


async def _admin_user_ids() -> list[str]:
    async with async_session_maker() as session:
        result = await session.execute(
            text('SELECT id FROM "user" WHERE role = \'admin\' OR is_superuser = true')
        )
        return [str(value) for value in result.scalars()]


async def _user_email(user_id: str) -> str:
    value = (user_id or "").strip()
    if not value:
        return ""
    if "@" in value:
        return value
    try:
        user_uuid = UUID(value)
    except ValueError:
        return ""
    async with async_session_maker() as session:
        result = await session.execute(
            text('SELECT email FROM "user" WHERE id = :id'),
            {"id": user_uuid},
        )
        email = result.scalar_one_or_none()
    return str(email or "")


async def notify_admins_of_submission(*, approval_id: str, resource_type: str, submitter_email: str) -> None:
    """Create alerts without letting a notification outage reject an upload."""
    try:
        await create_notifications(
            await _admin_user_ids(),
            title=f"{resource_type.upper()} upload awaiting approval",
            body=f"Submitted by {submitter_email or 'a user'}",
            data={
                "approval_id": approval_id,
                "resource_type": resource_type,
                "status": "pending",
                "path": f"/approvals?approval_id={approval_id}",
            },
        )
    except Exception:
        logger.exception("Failed to create upload approval notifications")


async def notify_admins_of_hitl_approval(
    *,
    approval_id: str,
    tool_name: str,
    submitter_user_id: str,
    run_id: str = "",
    session_id: str = "",
) -> None:
    """Alert admins when a chat run pauses on a required HITL tool."""
    try:
        submitter_email = await _user_email(submitter_user_id)
        label = (tool_name or "tool").strip() or "tool"
        await create_notifications(
            await _admin_user_ids(),
            title=f"HITL approval required: {label}",
            body=f"Submitted by {submitter_email or submitter_user_id or 'a user'}",
            data={
                "approval_id": approval_id,
                "resource_type": "hitl",
                "tool_name": label,
                "status": "pending",
                "run_id": run_id,
                "session_id": session_id,
                "path": f"/approvals?approval_id={approval_id}",
            },
        )
    except Exception:
        logger.exception("Failed to create HITL approval notifications")


async def notify_submitter_of_rejection(
    *, approval_id: str, resource_type: str, submitter_id: str, rejection_reason: str
) -> None:
    """Notify a submitter about a rejected upload without blocking the resolution."""
    try:
        await create_notifications(
            [submitter_id],
            title=f"{resource_type.upper()} upload rejected",
            body=f"Reason: {rejection_reason}",
            data={
                "approval_id": approval_id,
                "resource_type": resource_type,
                "status": "rejected",
                "rejection_reason": rejection_reason,
                "path": f"/approvals?approval_id={approval_id}",
            },
        )
    except Exception:
        logger.exception("Failed to create upload rejection notification")


async def notify_submitter_of_hitl_resolution(
    *,
    approval_id: str,
    tool_name: str,
    submitter_id: str,
    status: str,
    rejection_reason: str = "",
    run_id: str = "",
    session_id: str = "",
) -> None:
    """Notify the chat submitter after a HITL approval is resolved."""
    submitter = (submitter_id or "").strip()
    if not submitter:
        return
    try:
        label = (tool_name or "tool").strip() or "tool"
        if status == "rejected":
            reason = (rejection_reason or "").strip() or "No reason provided"
            title = f"HITL request rejected: {label}"
            body = f"Reason: {reason}"
        else:
            title = f"HITL request approved: {label}"
            body = f"Your {label} request was approved and the conversation continuation completed."
        await create_notifications(
            [submitter],
            title=title,
            body=body,
            data={
                "approval_id": approval_id,
                "resource_type": "hitl",
                "tool_name": label,
                "status": status,
                "rejection_reason": (rejection_reason or "").strip(),
                "run_id": run_id,
                "session_id": session_id,
                "run_status": "COMPLETED",
                "path": f"/chat?session={session_id}" if session_id else "/chat",
            },
        )
    except Exception:
        logger.exception("Failed to create HITL resolution notification for submitter")


async def notify_hitl_resume_failure(
    *,
    approval_id: str,
    tool_name: str,
    submitter_id: str,
    run_id: str,
    session_id: str,
    error: str,
) -> None:
    """Notify both sides when an approved/rejected run cannot be continued."""
    label = (tool_name or "tool").strip() or "tool"
    failure = (error or "Unknown continuation error").strip()[:500]
    common = {
        "approval_id": approval_id,
        "resource_type": "hitl",
        "tool_name": label,
        "status": "failed",
        "run_status": "ERROR",
        "run_id": run_id,
        "session_id": session_id,
        "error": failure,
    }
    try:
        submitter = (submitter_id or "").strip()
        if submitter:
            await create_notifications(
                [submitter],
                title=f"HITL continuation failed: {label}",
                body="The approval was recorded, but the conversation could not be continued.",
                data={
                    **common,
                    "path": f"/chat?session={session_id}" if session_id else "/chat",
                },
            )
        await create_notifications(
            await _admin_user_ids(),
            title=f"HITL continuation failed: {label}",
            body=failure,
            data={
                **common,
                "path": f"/approvals?approval_id={approval_id}",
            },
        )
    except Exception:
        logger.exception("Failed to create HITL continuation failure notifications")


async def notify_workflow_trigger_failure(
    *,
    workflow_id: str,
    workflow_name: str = "",
    owner_user_id: str,
    source: str,
    run_id: str = "",
    session_id: str = "",
    error: str = "",
) -> None:
    """Notify workflow owner (and admins) when webhook/cron run ends in error."""
    owner = (owner_user_id or "").strip()
    if not owner:
        return
    try:
        label = (workflow_name or workflow_id or "workflow").strip() or "workflow"
        src = (source or "trigger").strip() or "trigger"
        failure = (error or "Workflow trigger failed").strip()[:500]
        path_trace = (
            f"/trace?session_id={session_id}&run_id={run_id}&selected_session={session_id}&trace={run_id}"
            if session_id
            else f"/workflow?workflow_id={workflow_id}"
        )
        data = {
            "workflow_id": workflow_id,
            "resource_type": "workflow",
            "source": src,
            "status": "error",
            "run_id": run_id,
            "session_id": session_id,
            "error": failure,
            "path": path_trace,
        }
        body = f"{src} trigger failed for {label}. {failure}".strip()
        await create_notifications(
            [owner],
            title=f"Workflow trigger failed: {label}",
            body=body,
            data=data,
        )
        admin_ids = [uid for uid in await _admin_user_ids() if uid != owner]
        if admin_ids:
            await create_notifications(
                admin_ids,
                title=f"Workflow trigger failed: {label}",
                body=body,
                data=data,
            )
    except Exception:
        logger.exception("Failed to create workflow trigger failure notifications")


async def notify_workflow_hitl_pending(
    *,
    approval_id: str,
    workflow_id: str,
    step_name: str = "",
    submitter_user_id: str = "",
    run_id: str = "",
    session_id: str = "",
    pause_type: str = "confirmation",
) -> None:
    """Alert admins when a workflow step pauses for HITL (Approvals on-call)."""
    approval = (approval_id or "").strip()
    if not approval:
        return
    try:
        label = (step_name or "workflow step").strip() or "workflow step"
        submitter_email = await _user_email(submitter_user_id) if submitter_user_id else ""
        body_parts = [f"Step: {label}"]
        if submitter_email or submitter_user_id:
            body_parts.append(
                f"Submitted by {submitter_email or submitter_user_id}"
            )
        if pause_type:
            body_parts.append(f"pause={pause_type}")
        await create_notifications(
            await _admin_user_ids(),
            title=f"Workflow HITL required: {label}",
            body="; ".join(body_parts),
            data={
                "approval_id": approval,
                "resource_type": "workflow_hitl",
                "workflow_id": workflow_id,
                "tool_name": f"workflow.step:{label}",
                "status": "pending",
                "run_id": run_id,
                "session_id": session_id,
                "pause_type": pause_type,
                "path": f"/approvals?approval_id={approval}",
            },
        )
    except Exception:
        logger.exception("Failed to create workflow HITL pending notifications")


async def notify_background_task_failure(
    *,
    task_name: str = "",
    error: str = "",
    user_id: str = "",
) -> None:
    """Alert admins (and optional user) when a fire-and-forget task fails.

    Used by the asyncio exception handler for Agno background work such as
    ``amake_memories``. Never raises to the event-loop handler.
    """
    message = (error or "Background task failed").strip() or "Background task failed"
    label = (task_name or "background task").strip() or "background task"
    body = message if len(message) <= 500 else f"{message[:497]}..."
    lower = label.lower()
    if "memory" in lower or "memories" in lower:
        path = "/memory"
        title = f"Memory task failed: {label}"
    else:
        path = "/audit"
        title = f"Background task failed: {label}"
    data = {
        "resource_type": "background_task",
        "status": "error",
        "task_name": label,
        "error": body,
        "path": path,
    }
    recipients: list[str] = []
    try:
        recipients.extend(await _admin_user_ids())
        owner = (user_id or "").strip()
        if owner:
            recipients.append(owner)
        if not recipients:
            return
        await create_notifications(
            recipients,
            title=title,
            body=body,
            data=data,
        )
    except Exception:
        logger.exception("Failed to create background task failure notifications")

