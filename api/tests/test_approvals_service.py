"""Critical business tests for HITL approvals list/resolve/retry/count."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routes import approvals
from api.services.approvals_service import (
    ApprovalListParams,
    ApprovalResolveConflictError,
    get_pending_approval_count,
    list_approvals_native,
)
from api.tests.route_fakes import route_dependency


def actor(user_id: str = "admin-1", role: str = "admin"):
    return SimpleNamespace(
        id=user_id,
        email=f"{user_id}@example.com",
        role=role,
        is_superuser=False,
    )


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/approvals/approval-1/resolve",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


class FakeApprovalDb:
    """Minimal Agno db surface used by list + pending-count paths."""

    def __init__(self) -> None:
        self.list_kwargs: dict[str, object] = {}
        self.pending_count_user_id: str | None = None
        self.pending_count_value: int = 3

    async def get_pending_approval_count(self, user_id=None):
        self.pending_count_user_id = user_id
        return self.pending_count_value

    async def get_approvals(self, **kwargs):
        self.list_kwargs = kwargs
        return (
            [
                {
                    "id": "approval-1",
                    "run_id": "run-1",
                    "session_id": "session-1",
                    "status": "pending",
                    "source_type": "agent",
                    "tool_name": "delete_user_data",
                    "user_id": kwargs.get("user_id") or "u1",
                    "created_at": 1714560000,
                }
            ],
            1,
        )


@pytest.mark.asyncio
async def test_list_approvals_native_uses_service_filters():
    db = FakeApprovalDb()
    params = ApprovalListParams(
        status="pending",
        source_type="agent",
        run_id="run-1",
        limit=10,
        page=2,
    )

    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        payload = await list_approvals_native(params=params, actor=actor())

    assert db.list_kwargs == {
        "status": "pending",
        "source_type": "agent",
        "approval_type": None,
        "pause_type": None,
        "agent_id": None,
        "team_id": None,
        "workflow_id": None,
        "user_id": None,
        "schedule_id": None,
        "run_id": "run-1",
        "limit": 10,
        "page": 2,
    }
    assert payload["data"][0]["id"] == "approval-1"
    assert payload["meta"]["page"] == 2
    assert payload["meta"]["limit"] == 10
    assert payload["meta"]["total_count"] == 1


@pytest.mark.asyncio
async def test_resolve_route_maps_missing_and_conflict_to_http_errors():
    current_actor = actor("admin-1")

    with patch.object(
        approvals, "get_approval_record", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(HTTPException) as missing:
            await approvals.resolve_approval(
                "missing",
                approvals.ApprovalResolveRequest(status="approved"),
                request=request(),
                user=current_actor,
            )
    assert missing.value.status_code == 404

    with patch.object(
        approvals,
        "get_approval_record",
        new=AsyncMock(return_value={"id": "approval-1", "user_id": "user-1"}),
    ), patch.object(
        approvals, "resolve_approval_record", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(HTTPException) as missing:
            await approvals.resolve_approval(
                "missing",
                approvals.ApprovalResolveRequest(status="approved"),
                request=request(),
                user=current_actor,
            )
    assert missing.value.status_code == 404

    with patch.object(
        approvals,
        "get_approval_record",
        new=AsyncMock(return_value={"id": "approval-1", "user_id": "user-1"}),
    ), patch.object(
        approvals,
        "resolve_approval_record",
        new=AsyncMock(side_effect=ApprovalResolveConflictError("not pending")),
    ):
        with pytest.raises(HTTPException) as conflict:
            await approvals.resolve_approval(
                "approval-1",
                approvals.ApprovalResolveRequest(
                    status="rejected", rejection_reason="Not allowed"
                ),
                request=request(),
                user=current_actor,
            )
    assert conflict.value.status_code == 409


def test_rejected_approval_request_requires_reason():
    with pytest.raises(ValueError, match="rejection reason"):
        approvals.ApprovalResolveRequest(status="rejected", rejection_reason=" ")


@pytest.mark.asyncio
async def test_resolve_hitl_schedules_security_resume():
    current_actor = actor("admin-1")
    resolved = {
        "id": "approval-1",
        "status": "rejected",
        "run_id": "run-1",
        "session_id": "session-1",
        "source_type": "agent",
        "agent_id": "security-operations",
        "user_id": "user-1",
    }
    with (
        patch.object(
            approvals,
            "get_approval_record",
            new=AsyncMock(return_value=resolved),
        ),
        patch.object(
            approvals,
            "resolve_approval_record",
            new=AsyncMock(return_value=resolved),
        ) as resolve,
        patch.object(
            approvals, "resume_security_run", new=AsyncMock(return_value="RUNNING")
        ) as resume,
        patch.object(
            approvals,
            "get_approval_record",
            new=AsyncMock(return_value={**resolved, "run_status": "RUNNING"}),
        ),
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        result = await approvals.resolve_approval(
            "approval-1",
            approvals.ApprovalResolveRequest(
                status="rejected", rejection_reason="证据不足"
            ),
            request=request(),
            user=current_actor,
        )

    resolve.assert_awaited_once()
    assert resolve.await_args is not None
    assert resolve.await_args.kwargs["resolution_data"] == {"note": "证据不足"}
    resume.assert_awaited_once_with("approval-1")
    assert result["run_status"] == "RUNNING"


@pytest.mark.asyncio
async def test_retry_only_accepts_failed_security_chat_runs():
    current_actor = actor("admin-1")
    failed = {
        "id": "approval-1",
        "status": "approved",
        "run_status": "ERROR",
        "run_id": "run-1",
        "session_id": "session-1",
        "source_type": "agent",
        "agent_id": "security-operations",
        "user_id": "user-1",
    }
    with (
        patch.object(
            approvals,
            "get_approval_record",
            new=AsyncMock(side_effect=[failed, {**failed, "run_status": "RUNNING"}]),
        ),
        patch.object(
            approvals, "resume_security_run", new=AsyncMock(return_value="RUNNING")
        ) as resume,
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        result = await approvals.retry_approval_resume(
            "approval-1",
            request=request(),
            user=current_actor,
        )

    resume.assert_awaited_once_with("approval-1", retry_error=True)
    assert result["run_status"] == "RUNNING"

    not_failed = {**failed, "run_status": "RUNNING"}
    with patch.object(
        approvals, "get_approval_record", new=AsyncMock(return_value=not_failed)
    ):
        with pytest.raises(HTTPException) as exc:
            await approvals.retry_approval_resume(
                "approval-1",
                request=request(),
                user=current_actor,
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_normal_user_cannot_resolve_or_retry_another_users_approval():
    current_actor = actor("user-1", role="user")
    other_users_approval = {
        "id": "approval-2",
        "status": "pending",
        "user_id": "user-2",
    }

    with patch.object(
        approvals,
        "get_approval_record",
        new=AsyncMock(return_value=other_users_approval),
    ), patch.object(approvals, "resolve_approval_record", new=AsyncMock()) as resolve:
        with pytest.raises(HTTPException) as resolve_exc:
            await approvals.resolve_approval(
                "approval-2",
                approvals.ApprovalResolveRequest(status="approved"),
                request=request(),
                user=current_actor,
            )
    assert resolve_exc.value.status_code == 404
    resolve.assert_not_awaited()

    with patch.object(
        approvals,
        "get_approval_record",
        new=AsyncMock(return_value=other_users_approval),
    ), patch.object(approvals, "resume_security_run", new=AsyncMock()) as resume:
        with pytest.raises(HTTPException) as retry_exc:
            await approvals.retry_approval_resume(
                "approval-2", request=request(), user=current_actor
            )
    assert retry_exc.value.status_code == 404
    resume.assert_not_awaited()


def test_submission_resolution_is_admin_only():
    dependency = route_dependency(
        approvals.router, "resolve_submission_approval_request"
    )

    with pytest.raises(HTTPException) as exc:
        dependency(user=actor("user-1", role="user"))

    assert exc.value.status_code == 403
    assert dependency(user=actor()) is not None


@pytest.mark.asyncio
async def test_normal_user_can_resolve_own_hitl_approval():
    current_actor = actor("user-1", role="user")
    own_approval = {
        "id": "approval-1",
        "status": "pending",
        "user_id": "user-1",
    }
    resolved_approval = {**own_approval, "status": "approved"}

    with (
        patch.object(
            approvals,
            "get_approval_record",
            new=AsyncMock(side_effect=[own_approval, resolved_approval]),
        ),
        patch.object(
            approvals,
            "resolve_approval_record",
            new=AsyncMock(return_value=resolved_approval),
        ) as resolve,
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        result = await approvals.resolve_approval(
            "approval-1",
            approvals.ApprovalResolveRequest(status="approved"),
            request=request(),
            user=current_actor,
        )

    assert result == resolved_approval
    resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pending_approval_count_scopes_non_admin():
    db = FakeApprovalDb()
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        count = await get_pending_approval_count(actor=actor("user-9", role="user"))

    assert count == 3
    assert db.pending_count_user_id == "user-9"
