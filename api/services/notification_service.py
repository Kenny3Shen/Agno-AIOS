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
            body = f"Your {label} request was approved and the run has been resumed."
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
                "path": f"/approvals?approval_id={approval_id}",
            },
        )
    except Exception:
        logger.exception("Failed to create HITL resolution notification for submitter")

