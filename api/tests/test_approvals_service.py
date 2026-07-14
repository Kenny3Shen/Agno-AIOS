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
    get_approval_record,
    get_approval_status_counts,
    get_pending_approval_count,
    list_approvals_native,
    resolve_approval_record,
)


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
    def __init__(self):
        self.list_kwargs: dict[str, object] = {}
        self.updated: dict[str, object] = {}
        self.pending_count_user_id: str | None = None
        self.pending_count_value: int = 3
        self.status_totals: dict[str, int] = {"pending": 3, "approved": 5, "rejected": 1}
        self.return_update = True

    async def get_pending_approval_count(self, user_id=None):
        self.pending_count_user_id = user_id
        return self.pending_count_value

    async def get_approvals(self, **kwargs):
        self.list_kwargs = kwargs
        status = kwargs.get("status")
        # Count helper uses limit=1; keep full list fixture for normal list queries.
        if status in self.status_totals and kwargs.get("limit") == 1:
            total = self.status_totals[str(status)]
            return (
                [
                    {
                        "id": f"approval-{status}",
                        "run_id": "run-1",
                        "session_id": "session-1",
                        "status": status,
                        "source_type": "agent",
                        "tool_name": "delete_user_data",
                        "user_id": kwargs.get("user_id") or "u1",
                        "created_at": 1714560000,
                    }
                ],
                total,
            )
        return (
            [
                {
                    "id": "approval-1",
                    "run_id": "run-1",
                    "session_id": "session-1",
                    "status": "pending",
                    "source_type": "agent",
                    "approval_type": "required",
                    "pause_type": "tool",
                    "tool_name": "delete_user_data",
                    "tool_args": {"user_id": "u1"},
                    "agent_id": "security-operations",
                    "user_id": kwargs.get("user_id") or "u1",
                    "source_name": "Security Agent",
                    "requirements": [{"type": "confirmation"}],
                    "context": {"reason": "destructive"},
                    "created_at": 1714560000,
                    "updated_at": 1714560300,
                    "run_status": "PAUSED",
                },
                {
                    "id": "approval-2",
                    "run_id": "run-2",
                    "session_id": "session-2",
                    "status": "approved",
                    "source_type": "agent",
                    "tool_name": "send_bulk_email",
                    "resolved_by": "admin@example.com",
                    "resolved_at": 1714560400,
                    "created_at": 1714560100,
                    "updated_at": 1714560400,
                },
            ],
            2,
        )

    async def get_approval(self, approval_id: str):
        if approval_id == "missing":
            return None
        return {
            "id": approval_id,
            "run_id": "run-1",
            "session_id": "session-1",
            "status": "pending",
            "source_type": "agent",
            "tool_name": "delete_user_data",
            "created_at": 1714560000,
        }

    def update_approval(self, approval_id: str, expected_status=None, **kwargs):
        # Sync signature matches Agno aresolve_approval non-AsyncBaseDb path;
        # production uses AsyncPostgresDb so aresolve awaits async update_approval.
        self.updated = {
            "approval_id": approval_id,
            "expected_status": expected_status,
            **kwargs,
        }
        if not self.return_update:
            return None
        return {
            "id": approval_id,
            "run_id": "run-1",
            "session_id": "session-1",
            "status": kwargs["status"],
            "source_type": "agent",
            "tool_name": "delete_user_data",
            "resolved_by": kwargs["resolved_by"],
            "resolved_at": kwargs["resolved_at"],
            "resolution_data": kwargs.get("resolution_data"),
        }


@pytest.mark.asyncio
async def test_list_approvals_native_uses_agno_filters_and_data_meta():
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
    assert payload["data"][0]["tool_name"] == "delete_user_data"
    assert payload["data"][0]["id"] == "approval-1"
    assert payload["meta"] == {
        "page": 2,
        "limit": 10,
        "total_pages": 1,
        "total_count": 2,
        "search_time_ms": 0.0,
    }


@pytest.mark.asyncio
async def test_get_approval_record_returns_none_for_missing_id():
    db = FakeApprovalDb()
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        assert await get_approval_record("missing") is None


@pytest.mark.asyncio
async def test_resolve_approval_record_uses_expected_pending_and_server_resolver():
    db = FakeApprovalDb()
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        resolved = await resolve_approval_record(
            "approval-1",
            status="approved",
            resolved_by="admin@example.com",
            resolution_data={"note": "checked"},
        )

    assert resolved is not None
    assert db.updated["approval_id"] == "approval-1"
    assert db.updated["expected_status"] == "pending"
    assert db.updated["status"] == "approved"
    assert db.updated["resolved_by"] == "admin@example.com"
    assert db.updated["resolution_data"] == {"note": "checked"}
    assert isinstance(db.updated["resolved_at"], int)
    assert resolved["status"] == "approved"


@pytest.mark.asyncio
async def test_resolve_approval_record_maps_stale_pending_to_conflict():
    db = FakeApprovalDb()
    db.return_update = False
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        with pytest.raises(ApprovalResolveConflictError):
            await resolve_approval_record(
                "approval-1",
                status="rejected",
                resolved_by="admin@example.com",
                resolution_data=None,
            )


@pytest.mark.asyncio
async def test_approvals_route_uses_agno_service():
    db = FakeApprovalDb()
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        payload = await approvals.list_approvals(user=actor("admin-1"))

    assert payload["data"][0]["id"] == "approval-1"
    assert payload["meta"]["total_count"] == 2
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["limit"] == 50
    assert db.list_kwargs["limit"] == 50


@pytest.mark.asyncio
async def test_resolve_route_derives_resolver_from_actor_and_records_audit():
    current_actor = actor("admin-1")
    resolved = {
        "id": "approval-1",
        "status": "approved",
        "run_id": "run-1",
        "session_id": "session-1",
        "source_type": "agent",
    }

    with (
        patch.object(approvals, "resolve_approval_record", new=AsyncMock(return_value=resolved)) as resolve_mock,
        patch.object(approvals, "get_approval_record", new=AsyncMock(return_value=resolved)),
        patch.object(approvals, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await approvals.resolve_approval(
            "approval-1",
            approvals.ApprovalResolveRequest(
                status="approved",
                resolution_data={"client": "note"},
            ),
            request=request(),
            user=current_actor,
        )

    assert result == resolved
    resolve_mock.assert_awaited_once_with(
        "approval-1",
        status="approved",
        resolved_by="admin-1@example.com",
        resolution_data={"client": "note"},
    )
    audit_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_route_maps_missing_and_conflict_to_http_errors():
    current_actor = actor("admin-1")

    with patch.object(approvals, "resolve_approval_record", new=AsyncMock(return_value=None)):
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
        "resolve_approval_record",
        new=AsyncMock(side_effect=ApprovalResolveConflictError("not pending")),
    ):
        with pytest.raises(HTTPException) as conflict:
            await approvals.resolve_approval(
                "approval-1",
                approvals.ApprovalResolveRequest(status="rejected", rejection_reason="Not allowed"),
                request=request(),
                user=current_actor,
            )
    assert conflict.value.status_code == 409


def test_rejected_approval_request_requires_reason():
    with pytest.raises(ValueError, match="rejection reason"):
        approvals.ApprovalResolveRequest(status="rejected", rejection_reason=" ")


def test_rejected_submission_request_requires_reason():
    with pytest.raises(ValueError, match="rejection reason"):
        approvals.SubmissionApprovalResolveRequest(status="rejected")


@pytest.mark.asyncio
async def test_rejected_approval_route_adds_reason_to_resolution_data():
    current_actor = actor("admin-1")
    resolved = {"id": "approval-1", "status": "rejected"}
    with (
        patch.object(approvals, "resolve_approval_record", new=AsyncMock(return_value=resolved)) as resolve_mock,
        patch.object(approvals, "get_approval_record", new=AsyncMock(return_value=resolved)),
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        await approvals.resolve_approval(
            "approval-1",
            approvals.ApprovalResolveRequest(
                status="rejected", rejection_reason="Policy violation", resolution_data={"source": "review"}
            ),
            request=request(),
            user=current_actor,
        )
    assert resolve_mock.await_args is not None
    assert resolve_mock.await_args.kwargs["resolution_data"] == {
        "source": "review",
        "note": "Policy violation",
    }


@pytest.mark.asyncio
async def test_list_approvals_enrich_submitter_email_from_user_id():
    db = FakeApprovalDb()
    with (
        patch(
            "api.services.approvals_service.get_async_agno_postgres_db",
            return_value=db,
        ),
        patch(
            "api.services.approvals_service.lookup_user_emails",
            new=AsyncMock(return_value={"u1": "operator@example.com"}),
        ),
    ):
        from api.services.approvals_service import list_approvals

        approvals, total, _kwargs = await list_approvals(actor=actor())

    assert total == 2
    assert approvals[0]["submitted_by"] == {"id": "u1", "email": "operator@example.com"}
    assert "submitted_by_email" not in approvals[0]
    assert "resolved_by_email" not in approvals[0]


@pytest.mark.asyncio
async def test_resolve_hitl_rejection_schedules_native_continuation_and_returns_running():
    current_actor = actor("admin-1")
    resolved = {
        "id": "approval-1",
        "status": "rejected",
        "run_id": "run-1",
        "session_id": "session-1",
        "source_type": "agent",
        "agent_id": "security-operations",
        "tool_name": "any_protected_tool",
        "user_id": "user-1",
    }
    with (
        patch.object(approvals, "resolve_approval_record", new=AsyncMock(return_value=resolved)) as resolve,
        patch.object(approvals, "resume_security_run", new=AsyncMock(return_value="RUNNING")) as resume,
        patch.object(
            approvals,
            "get_approval_record",
            new=AsyncMock(return_value={**resolved, "run_status": "RUNNING"}),
        ),
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        result = await approvals.resolve_approval(
            "approval-1",
            approvals.ApprovalResolveRequest(status="rejected", rejection_reason="证据不足，暂不封禁"),
            request=request(),
            user=current_actor,
    )

    resolve.assert_awaited_once()
    resolve_call = resolve.await_args
    assert resolve_call is not None
    assert resolve_call.kwargs["resolution_data"] == {
        "note": "证据不足，暂不封禁",
    }
    resume.assert_awaited_once_with("approval-1")
    assert result["run_status"] == "RUNNING"


@pytest.mark.asyncio
async def test_resolve_without_paused_run_skips_resume():
    current_actor = actor("admin-1")
    resolved = {
        "id": "approval-2",
        "status": "approved",
        "tool_name": "simulate_containment",
        "user_id": "user-1",
    }
    with (
        patch.object(approvals, "resolve_approval_record", new=AsyncMock(return_value=resolved)),
        patch.object(approvals, "resume_security_run", new=AsyncMock()) as resume,
        patch.object(approvals, "get_approval_record", new=AsyncMock(return_value=resolved)),
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        result = await approvals.resolve_approval(
            "approval-2",
            approvals.ApprovalResolveRequest(status="approved"),
            request=request(),
            user=current_actor,
        )
    resume.assert_not_awaited()
    assert result == resolved


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
        patch.object(approvals, "resume_security_run", new=AsyncMock(return_value="RUNNING")) as resume,
        patch.object(approvals, "record_policy_event", new=AsyncMock()),
    ):
        result = await approvals.retry_approval_resume(
            "approval-1",
            request=request(),
            user=current_actor,
        )

    resume.assert_awaited_once_with("approval-1", retry_error=True)
    assert result["run_status"] == "RUNNING"

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


@pytest.mark.asyncio
async def test_get_pending_approval_count_admin_global_and_filter():
    db = FakeApprovalDb()
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        global_count = await get_pending_approval_count(actor=actor("admin-1"))
        filtered = await get_pending_approval_count(
            actor=actor("admin-1"),
            user_id="member-2",
        )

    assert global_count == 3
    assert filtered == 3
    assert db.pending_count_user_id == "member-2"


@pytest.mark.asyncio
async def test_approvals_count_route_returns_agno_shape():
    db = FakeApprovalDb()
    db.pending_count_value = 7
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        payload = await approvals.get_approval_count(user=actor("admin-1"))

    assert payload == {"count": 7}


@pytest.mark.asyncio
async def test_get_approval_status_counts_returns_pending_approved_rejected():
    db = FakeApprovalDb()
    with patch(
        "api.services.approvals_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        counts = await get_approval_status_counts(actor=actor("admin-1"))

    assert counts == {
        "pending": 3,
        "approved": 5,
        "rejected": 1,
        "total": 9,
    }

