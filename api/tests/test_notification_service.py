from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.services import notification_service


@pytest.mark.asyncio
async def test_notify_admins_of_hitl_approval_targets_admin_ids():
    with (
        patch.object(notification_service, "_admin_user_ids", new=AsyncMock(return_value=["admin-1", "admin-2"])),
        patch.object(notification_service, "_user_email", new=AsyncMock(return_value="operator@example.com")),
        patch.object(notification_service, "create_notifications", new=AsyncMock()) as create,
    ):
        await notification_service.notify_admins_of_hitl_approval(
            approval_id="approval-1",
            tool_name="simulate_containment",
            submitter_user_id="user-1",
            run_id="run-1",
            session_id="session-1",
        )

    create.assert_awaited_once()
    assert create.await_args.args[0] == ["admin-1", "admin-2"]
    assert create.await_args.kwargs["title"] == "HITL approval required: simulate_containment"
    assert "operator@example.com" in create.await_args.kwargs["body"]
    assert create.await_args.kwargs["data"]["approval_id"] == "approval-1"
    assert create.await_args.kwargs["data"]["status"] == "pending"
    assert create.await_args.kwargs["data"]["path"] == "/approvals?approval_id=approval-1"


@pytest.mark.asyncio
async def test_notify_admins_of_hitl_approval_swallows_failures():
    with (
        patch.object(notification_service, "_admin_user_ids", new=AsyncMock(side_effect=RuntimeError("db down"))),
        patch.object(notification_service, "create_notifications", new=AsyncMock()) as create,
    ):
        await notification_service.notify_admins_of_hitl_approval(
            approval_id="approval-1",
            tool_name="simulate_containment",
            submitter_user_id="user-1",
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_submitter_of_hitl_rejection_includes_reason():
    with patch.object(notification_service, "create_notifications", new=AsyncMock()) as create:
        await notification_service.notify_submitter_of_hitl_resolution(
            approval_id="approval-1",
            tool_name="simulate_containment",
            submitter_id="user-1",
            status="rejected",
            rejection_reason="证据不足，暂不封禁",
            run_id="run-1",
            session_id="session-1",
        )
    create.assert_awaited_once()
    assert create.await_args.args[0] == ["user-1"]
    assert "rejected" in create.await_args.kwargs["title"].lower() or "拒绝" in create.await_args.kwargs["title"]
    assert "证据不足，暂不封禁" in create.await_args.kwargs["body"]
    assert create.await_args.kwargs["data"]["rejection_reason"] == "证据不足，暂不封禁"
