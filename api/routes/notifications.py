import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import actor_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.persistence.notifications import (
    delete_notification,
    list_notifications,
    list_notifications_after,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("")
async def get_notifications(unread_only: bool = False, user: User = Depends(require_scope("sessions:read"))):
    items, unread_count = await list_notifications(actor_id(user), unread_only)
    return {"notifications": items, "unread_count": unread_count}


@router.get("/stream")
async def stream_notifications(
    request: Request,
    after_id: int = 0,
    user: User = Depends(require_scope("sessions:read")),
) -> EventSourceResponse:
    async def event_generator():
        cursor = max(0, int(after_id))
        while not await request.is_disconnected():
            rows = await list_notifications_after(actor_id(user), cursor)
            for row in rows:
                cursor = max(cursor, int(row["id"]))
                yield {
                    "event": "notification.created",
                    "id": str(row["id"]),
                    "data": json.dumps(row, ensure_ascii=False),
                }
            await asyncio.sleep(1)

    return EventSourceResponse(
        event_generator(),
        headers={"Cache-Control": "no-cache"},
        ping=15,
        sep="\n",
    )

@router.post("/read-all")
async def read_all_notifications(user: User = Depends(require_scope("sessions:read"))):
    updated_count = await mark_all_notifications_read(actor_id(user))
    return {"updated_count": updated_count}


@router.post("/{notification_id}/read")
async def read_notification(notification_id: int, user: User = Depends(require_scope("sessions:read"))):
    if not await mark_notification_read(notification_id, actor_id(user)):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.delete("/{notification_id}")
async def remove_notification(notification_id: int, user: User = Depends(require_scope("sessions:read"))):
    if not await delete_notification(notification_id, actor_id(user)):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}
