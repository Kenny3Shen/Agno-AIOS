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
    create_call = create.await_args
    assert create_call is not None
    assert create_call.args[0] == ["admin-1", "admin-2"]
    assert create_call.kwargs["title"] == "HITL approval required: simulate_containment"
    assert "operator@example.com" in create_call.kwargs["body"]
    assert create_call.kwargs["data"]["approval_id"] == "approval-1"
    assert create_call.kwargs["data"]["status"] == "pending"
    assert create_call.kwargs["data"]["path"] == "/approvals?approval_id=approval-1"


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
    create_call = create.await_args
    assert create_call is not None
    assert create_call.args[0] == ["user-1"]
    assert "rejected" in create_call.kwargs["title"].lower() or "拒绝" in create_call.kwargs["title"]
    assert "证据不足，暂不封禁" in create_call.kwargs["body"]
    assert create_call.kwargs["data"]["rejection_reason"] == "证据不足，暂不封禁"
    assert create_call.kwargs["data"]["path"] == "/chat?session=session-1"


@pytest.mark.asyncio
async def test_notify_submitter_of_hitl_approval_links_to_completed_chat():
    with patch.object(notification_service, "create_notifications", new=AsyncMock()) as create:
        await notification_service.notify_submitter_of_hitl_resolution(
            approval_id="approval-1",
            tool_name="hitl_simulate_containment",
            submitter_id="user-1",
            status="approved",
            run_id="run-1",
            session_id="session-1",
        )

    create_call = create.await_args
    assert create_call is not None
    assert create_call.args[0] == ["user-1"]
    assert create_call.kwargs["data"]["run_status"] == "COMPLETED"
    assert create_call.kwargs["data"]["path"] == "/chat?session=session-1"


@pytest.mark.asyncio
async def test_notify_hitl_resume_failure_targets_submitter_and_admins():
    with (
        patch.object(notification_service, "_admin_user_ids", new=AsyncMock(return_value=["admin-1"])),
        patch.object(notification_service, "create_notifications", new=AsyncMock()) as create,
    ):
        await notification_service.notify_hitl_resume_failure(
            approval_id="approval-1",
            tool_name="hitl_simulate_containment",
            submitter_id="user-1",
            run_id="run-1",
            session_id="session-1",
            error="provider unavailable",
        )

    assert create.await_count == 2
    submitter_call, admin_call = create.await_args_list
    assert submitter_call.args[0] == ["user-1"]
    assert submitter_call.kwargs["data"]["path"] == "/chat?session=session-1"
    assert admin_call.args[0] == ["admin-1"]
    assert admin_call.kwargs["data"]["path"] == "/approvals?approval_id=approval-1"
    assert admin_call.kwargs["data"]["run_status"] == "ERROR"


@pytest.mark.asyncio
async def test_notify_workflow_trigger_failure_targets_owner_and_admins():
    with (
        patch.object(notification_service, "_admin_user_ids", new=AsyncMock(return_value=["admin-1", "owner-1"])),
        patch.object(notification_service, "create_notifications", new=AsyncMock()) as create,
    ):
        await notification_service.notify_workflow_trigger_failure(
            workflow_id="wf-1",
            workflow_name="IR",
            owner_user_id="owner-1",
            source="cron",
            run_id="run-1",
            session_id="session-1",
            error="boom",
        )
    assert create.await_count == 2
    owner_call, admin_call = create.await_args_list
    assert owner_call.args[0] == ["owner-1"]
    assert admin_call.args[0] == ["admin-1"]
    assert "IR" in owner_call.kwargs["title"]
    assert owner_call.kwargs["data"]["path"].startswith("/trace?")
    assert owner_call.kwargs["data"]["source"] == "cron"

