from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
import pytest

from api.routes import os_control
from api.services import scheduler_service


def schedule_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "sched-1",
        "name": "nightly-scan",
        "description": "Nightly scan",
        "method": "POST",
        "endpoint": "/workflows/nightly-scan/runs",
        "payload": {"message": "scan"},
        "cron_expr": "0 2 * * *",
        "timezone": "UTC",
        "timeout_seconds": 3600,
        "max_retries": 1,
        "retry_delay_seconds": 60,
        "enabled": True,
        "next_run_at": 1800000000,
        "created_at": 1700000000,
        "updated_at": None,
    }
    data.update(overrides)
    return data


class FakeAsyncScheduleDb:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None
        self.updated: tuple[str, dict[str, Any]] | None = None
        self.existing_by_name: dict[str, Any] | None = None
        self.schedules: dict[str, dict[str, Any]] = {}
        self.runs: list[dict[str, Any]] = []

    async def get_schedule_by_name(self, name: str):
        return self.existing_by_name

    async def create_schedule(self, schedule_data: dict[str, Any]):
        self.created = schedule_data
        row = schedule_dict(**schedule_data)
        self.schedules[row["id"]] = row
        return row

    async def update_schedule(self, schedule_id: str, **kwargs: Any):
        self.updated = (schedule_id, kwargs)
        row = {**self.schedules.get(schedule_id, schedule_dict(id=schedule_id)), **kwargs}
        self.schedules[schedule_id] = row
        return row

    async def get_schedules(self, enabled=None, limit: int = 100, page: int = 1):
        rows = list(self.schedules.values())
        if enabled is not None:
            rows = [row for row in rows if row["enabled"] is enabled]
        return rows[:limit], len(rows)

    async def get_schedule(self, schedule_id: str):
        return self.schedules.get(schedule_id)

    async def delete_schedule(self, schedule_id: str):
        return self.schedules.pop(schedule_id, None) is not None

    async def get_schedule_runs(self, schedule_id: str, limit: int = 20, page: int = 1):
        rows = [row for row in self.runs if row.get("schedule_id") == schedule_id]
        return rows[:limit], len(rows)


def actor() -> Any:
    return SimpleNamespace(id="admin", role="admin", email="admin@example.com", is_superuser=False)


@pytest.mark.asyncio
async def test_create_schedule_generates_agno_endpoint_and_payload():
    db = FakeAsyncScheduleDb()
    with (
        patch.object(scheduler_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(scheduler_service, "compute_next_run", return_value=1800000000),
    ):
        result = await scheduler_service.create_schedule(
            name="nightly-scan",
            target_type="workflow",
            target_id="nightly-scan",
            cron_expr="0 2 * * *",
            payload={"message": "scan"},
            description="Nightly scan",
            timezone="Asia/Shanghai",
            timeout_seconds=1800,
            max_retries=2,
            retry_delay_seconds=30,
            enabled=True,
        )
    assert db.created is not None
    assert db.created["cron_expr"] == "0 2 * * *"
    assert db.created["endpoint"] == "/workflows/nightly-scan/runs"
    assert db.created["description"] == "Nightly scan"
    assert db.created["payload"] == {"message": "scan"}
    assert db.created["timezone"] == "Asia/Shanghai"
    assert db.created["timeout_seconds"] == 1800
    assert db.created["max_retries"] == 2
    assert db.created["retry_delay_seconds"] == 30
    assert result["target_type"] == "workflow"
    assert result["target_id"] == "nightly-scan"


@pytest.mark.asyncio
async def test_create_disabled_schedule_disables_after_create():
    db = FakeAsyncScheduleDb()
    with patch.object(scheduler_service, "get_async_agno_postgres_db", return_value=db):
        result = await scheduler_service.create_schedule(
            name="agent-check",
            target_type="agent",
            target_id="security-operations",
            cron_expr="*/15 * * * *",
            payload={},
            enabled=False,
        )
    assert db.updated is not None
    assert db.updated[1] == {"enabled": False}
    assert not result["enabled"]
    assert result["target_type"] == "agent"


def test_rejects_non_agno_schedule_targets():
    with pytest.raises(ValueError):
        scheduler_service.build_schedule_endpoint("skill", "local-skill")


@pytest.mark.asyncio
async def test_scheduler_payload_lists_agno_schedules():
    db = FakeAsyncScheduleDb()
    db.schedules = {
        "sched-1": schedule_dict(id="sched-1", enabled=True),
        "sched-2": schedule_dict(
            id="sched-2",
            name="soc-agent",
            endpoint="/agents/security-operations/runs",
            enabled=False,
            next_run_at=None,
        ),
    }
    with patch.object(scheduler_service, "get_async_agno_postgres_db", return_value=db):
        payload = await scheduler_service.get_scheduler_payload()
    assert payload["module"] == "scheduler"
    assert payload["metrics"][0]["value"] == 2
    assert payload["metrics"][1]["value"] == 1
    assert payload["metrics"][2]["value"] == 1
    assert payload["records"][0]["meta"]["cron_expr"] == "0 2 * * *"
    assert payload["records"][1]["meta"]["target_type"] == "agent"


@pytest.mark.asyncio
async def test_update_schedule_recomputes_endpoint_when_target_changes():
    db = FakeAsyncScheduleDb()
    db.schedules = {"sched-1": schedule_dict()}
    with (
        patch.object(scheduler_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(scheduler_service, "compute_next_run", return_value=1800000100),
        patch.object(scheduler_service, "validate_cron_expr", return_value=True),
        patch.object(scheduler_service, "validate_timezone", return_value=True),
    ):
        result = await scheduler_service.update_schedule(
            "sched-1",
            target_type="team",
            target_id="soc-team",
            cron_expr="*/10 * * * *",
        )
    assert result is not None
    assert db.updated is not None
    _, kwargs = db.updated
    assert kwargs["endpoint"] == "/teams/soc-team/runs"
    assert kwargs["cron_expr"] == "*/10 * * * *"
    assert kwargs["next_run_at"] == 1800000100
    assert result["target_type"] == "team"


@pytest.mark.asyncio
async def test_create_schedule_delegates_to_service_and_records_audit():
    created = {
        "id": "sched-1",
        "name": "nightly-scan",
        "enabled": True,
        "endpoint": "/workflows/nightly-scan/runs",
    }
    body = os_control.ScheduleCreateRequest(
        name="nightly-scan",
        target_type="workflow",
        target_id="nightly-scan",
        cron_expr="0 2 * * *",
        payload={"message": "scan"},
    )
    with (
        patch.object(os_control, "create_schedule", new=AsyncMock(return_value=created)) as create_mock,
        patch.object(os_control, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await os_control.create_scheduler_job(
            request=cast(Any, None), body=body, user=actor()
        )
    create_mock.assert_awaited_once()
    assert result.id == "sched-1"
    audit_mock.assert_awaited_once()
    assert audit_mock.call_args.args[1].action == "scheduler.create"
    assert audit_mock.call_args.args[1].resource_id == "sched-1"


@pytest.mark.asyncio
async def test_enable_schedule_delegates_to_service():
    enabled = {"id": "sched-1", "name": "nightly-scan", "enabled": True}
    with (
        patch.object(os_control, "set_schedule_enabled", new=AsyncMock(return_value=enabled)) as enable_mock,
        patch.object(os_control, "record_policy_event", new=AsyncMock()),
    ):
        result = await os_control.enable_scheduler_job(
            "sched-1", request=cast(Any, None), user=actor()
        )
    enable_mock.assert_awaited_once_with("sched-1", True)
    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_trigger_requires_running_scheduler_executor():
    with (
        patch.object(
            os_control,
            "get_schedule",
            new=AsyncMock(return_value={"id": "sched-1", "enabled": True}),
        ),
        pytest.raises(HTTPException) as context,
    ):
        await os_control.trigger_scheduler_job(
            "sched-1",
            request=cast(
                Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
            ),
            user=actor(),
        )
    assert context.value.status_code == 503


@pytest.mark.asyncio
async def test_trigger_uses_running_scheduler_executor_and_records_audit():
    run = {
        "id": "run-1",
        "schedule_id": "sched-1",
        "attempt": 1,
        "triggered_at": 1800000000,
        "completed_at": 1800000001,
        "status": "success",
        "status_code": 200,
        "run_id": "agent-run-1",
        "session_id": "session-1",
    }
    executor = Mock()
    executor.execute = AsyncMock(return_value=run)
    request = cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(scheduler_executor=executor))
        ),
    )
    with (
        patch.object(
            os_control,
            "get_schedule",
            new=AsyncMock(return_value={"id": "sched-1", "enabled": True}),
        ),
        patch.object(
            os_control, "get_async_agno_postgres_db", return_value=object()
        ) as db_mock,
        patch.object(os_control, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await os_control.trigger_scheduler_job(
            "sched-1", request=request, user=actor()
        )
    executor.execute.assert_awaited_once_with(
        {"id": "sched-1", "enabled": True}, db_mock.return_value, release_schedule=False
    )
    assert result["id"] == "run-1"
    audit_mock.assert_awaited_once()
    assert audit_mock.call_args.args[1].action == "scheduler.trigger"
    assert audit_mock.call_args.args[1].metadata == {"run_id": "run-1"}
