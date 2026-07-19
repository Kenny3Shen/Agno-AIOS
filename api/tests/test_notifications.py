from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.auth.models import User
from api.routes import notifications
from api.utils.async_once import AsyncOnce


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


@pytest.mark.asyncio
async def test_notification_stream_replays_rows_in_cursor_order_without_duplicates() -> None:
    user = cast(User, SimpleNamespace(id="user-1"))
    request = cast(
        Request,
        SimpleNamespace(is_disconnected=AsyncMock(side_effect=[False, False, True])),
    )
    rows = [
        {
            "id": 4,
            "title": "first",
            "body": "one",
            "data": {},
            "read": False,
            "created_at": 1,
        },
        {
            "id": 5,
            "title": "second",
            "body": "two",
            "data": {},
            "read": False,
            "created_at": 2,
        },
    ]
    with (
        patch.object(
            notifications,
            "list_notifications_after",
            new=AsyncMock(side_effect=[rows, []]),
        ) as list_after,
        patch.object(notifications.asyncio, "sleep", new=AsyncMock()),
    ):
        response = await notifications.stream_notifications(
            request,
            after_id=3,
            user=user,
        )
        events = [cast(dict[str, str], event) async for event in response.body_iterator]

    assert [event["id"] for event in events] == ["4", "5"]
    assert [event["event"] for event in events] == [
        "notification.created",
        "notification.created",
    ]
    assert [call.args for call in list_after.await_args_list] == [
        ("user-1", 3),
        ("user-1", 5),
    ]


@pytest.mark.asyncio
async def test_notifications_ensure_runs_once(monkeypatch) -> None:
    from api.persistence import notifications as store

    monkeypatch.setattr(store, "_notifications_ensure_once", AsyncOnce())
    calls = 0

    async def fake_create() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(store, "_create_notifications_table", fake_create)
    await store._ensure()
    await store._ensure()
    assert calls == 1



@pytest.mark.asyncio
async def test_get_notifications_returns_data_meta_envelope() -> None:
    user = cast(User, SimpleNamespace(id="user-1"))
    rows = [
        {
            "id": 1,
            "title": "hello",
            "body": "world",
            "data": {},
            "read": False,
            "created_at": 1,
        }
    ]
    with patch.object(
        notifications,
        "list_notifications",
        new=AsyncMock(return_value=(rows, 3)),
    ) as list_rows:
        result = await notifications.get_notifications(unread_only=False, user=user)
    list_rows.assert_awaited_once_with("user-1", False)
    assert result["data"] == rows
    assert result["meta"]["unread_count"] == 3
    assert result["meta"]["total_count"] == 1
    assert result["meta"]["page"] == 1
