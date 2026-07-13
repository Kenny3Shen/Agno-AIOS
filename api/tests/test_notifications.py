from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.auth.models import User
from api.routes import notifications


@pytest.mark.asyncio
async def test_read_all_notifications_marks_only_the_current_users_notifications() -> None:
    user = cast(User, SimpleNamespace(id="user-1"))

    with patch.object(
        notifications,
        "mark_all_notifications_read",
        new=AsyncMock(return_value=3),
    ) as mark_all:
        assert await notifications.read_all_notifications(user) == {"updated_count": 3}

    mark_all.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_read_all_notifications_is_idempotent_when_no_notifications_are_unread() -> None:
    user = cast(User, SimpleNamespace(id="user-1"))

    with patch.object(
        notifications,
        "mark_all_notifications_read",
        new=AsyncMock(return_value=0),
    ):
        assert await notifications.read_all_notifications(user) == {"updated_count": 0}


@pytest.mark.asyncio
async def test_delete_notification_removes_current_users_notification() -> None:
    user = cast(User, SimpleNamespace(id="user-1"))

    with patch.object(
        notifications,
        "delete_notification",
        new=AsyncMock(return_value=True),
    ) as delete_one:
        assert await notifications.remove_notification(9, user) == {"success": True}
        delete_one.assert_awaited_once_with(9, "user-1")


@pytest.mark.asyncio
async def test_delete_notification_returns_404_when_missing() -> None:
    user = cast(User, SimpleNamespace(id="user-1"))

    with patch.object(
        notifications,
        "delete_notification",
        new=AsyncMock(return_value=False),
    ):
        with pytest.raises(HTTPException) as exc:
            await notifications.remove_notification(9, user)
        assert exc.value.status_code == 404

