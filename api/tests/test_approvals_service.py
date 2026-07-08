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
    list_approvals_payload,
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
        self.return_update = True

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

    async def get_pending_approval_count(self, user_id=None):
        self.pending_count_user_id = user_id
        return 1

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

    async def update_approval(self, approval_id: str, expected_status=None, **kwargs):
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
async def test_list_approvals_payload_uses_agno_filters_and_metrics():
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
        payload = await list_approvals_payload(params=params, actor=actor())

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
    assert db.pending_count_user_id is None
    assert payload["module"] == "approvals"
    assert payload["approval_filters"]["status"] == "pending"
    assert payload["approval_meta"]["total"] == 2
    assert payload["approvals"][0]["tool_name"] == "delete_user_data"
    assert payload["records"][0]["id"] == "approval-1"
    assert payload["metrics"][0]["label"] == "Pending"
    assert payload["metrics"][0]["value"] == 1


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

    assert payload["module"] == "approvals"
    assert payload["approvals"][0]["id"] == "approval-1"
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
                approvals.ApprovalResolveRequest(status="rejected"),
                request=request(),
                user=current_actor,
            )
    assert conflict.value.status_code == 409
