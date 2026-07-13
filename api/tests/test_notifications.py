from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

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
