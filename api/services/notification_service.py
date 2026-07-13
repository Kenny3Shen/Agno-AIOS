from __future__ import annotations

from sqlalchemy import text
from loguru import logger

from api.auth.database import async_session_maker
from api.persistence.notifications import create_notifications


async def notify_admins_of_submission(*, approval_id: str, resource_type: str, submitter_email: str) -> None:
    """Create alerts without letting a notification outage reject an upload."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                text('SELECT id FROM "user" WHERE role = \'admin\' OR is_superuser = true')
            )
            ids = [str(value) for value in result.scalars()]
        await create_notifications(
            ids,
            title=f"{resource_type.upper()} upload awaiting approval",
            body=f"Submitted by {submitter_email or 'a user'}",
            data={"approval_id": approval_id, "resource_type": resource_type},
        )
    except Exception:
        logger.exception("Failed to create upload approval notifications")


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
            },
        )
    except Exception:
        logger.exception("Failed to create upload rejection notification")
