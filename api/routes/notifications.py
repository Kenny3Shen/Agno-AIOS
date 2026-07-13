from fastapi import APIRouter, Depends, HTTPException

from api.auth.claims import actor_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.persistence.notifications import (
    delete_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("")
async def get_notifications(unread_only: bool = False, user: User = Depends(require_scope("sessions:read"))):
    items, unread_count = await list_notifications(actor_id(user), unread_only)
    return {"notifications": items, "unread_count": unread_count}

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
