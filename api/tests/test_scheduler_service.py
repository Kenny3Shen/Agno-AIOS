from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from api.routes import os_control
from api.services import scheduler_service
import pytest


def schedule(**overrides):
    data = {
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
    return SimpleNamespace(**data)


def test_create_schedule_generates_agno_endpoint_and_payload():
    manager = Mock()
    manager.create.return_value = schedule()
    with patch.object(scheduler_service, "get_schedule_manager", return_value=manager):
        result = scheduler_service.create_schedule(
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
    manager.create.assert_called_once_with(
        name="nightly-scan",
        cron="0 2 * * *",
        endpoint="/workflows/nightly-scan/runs",
        method="POST",
        description="Nightly scan",
        payload={"message": "scan"},
        timezone="Asia/Shanghai",
        timeout_seconds=1800,
        max_retries=2,
        retry_delay_seconds=30,
    )
    assert result["target_type"] == "workflow"
    assert result["target_id"] == "nightly-scan"
    assert result["endpoint"] == "/workflows/nightly-scan/runs"


def test_create_disabled_schedule_disables_after_agno_create():
    manager = Mock()
    manager.create.return_value = schedule(
        endpoint="/agents/security-operations/runs", enabled=True
    )
    manager.disable.return_value = schedule(
        endpoint="/agents/security-operations/runs", enabled=False
    )
    with patch.object(scheduler_service, "get_schedule_manager", return_value=manager):
        result = scheduler_service.create_schedule(
            name="agent-check",
            target_type="agent",
            target_id="security-operations",
            cron_expr="*/15 * * * *",
            payload={},
            enabled=False,
        )
    manager.disable.assert_called_once_with("sched-1")
    assert not result["enabled"]
    assert result["target_type"] == "agent"


def test_rejects_non_agno_schedule_targets():
    with pytest.raises(ValueError):
        scheduler_service.build_schedule_endpoint("skill", "local-skill")


def test_scheduler_payload_lists_agno_schedules():
    manager = Mock()
    manager.list.return_value = [
        schedule(id="sched-1", enabled=True),
        schedule(
            id="sched-2",
            name="soc-agent",
            endpoint="/agents/security-operations/runs",
            enabled=False,
            next_run_at=None,
        ),
    ]
    with patch.object(scheduler_service, "get_schedule_manager", return_value=manager):
        payload = scheduler_service.get_scheduler_payload()
    assert payload["module"] == "scheduler"
    assert payload["metrics"][0]["value"] == 2
    assert payload["metrics"][1]["value"] == 1
    assert payload["metrics"][2]["value"] == 1
    assert payload["records"][0]["meta"]["cron_expr"] == "0 2 * * *"
    assert payload["records"][1]["meta"]["target_type"] == "agent"


def test_update_schedule_recomputes_endpoint_when_target_changes():
    manager = Mock()
    manager.get.return_value = schedule()
    manager.update.return_value = schedule(endpoint="/teams/soc-team/runs")
    with (
        patch.object(scheduler_service, "get_schedule_manager", return_value=manager),
        patch.object(scheduler_service, "compute_next_run", return_value=1800000100),
        patch.object(scheduler_service, "validate_cron_expr", return_value=True),
        patch.object(scheduler_service, "validate_timezone", return_value=True),
    ):
        result = scheduler_service.update_schedule(
            "sched-1",
            target_type="team",
            target_id="soc-team",
            cron_expr="*/10 * * * *",
        )
    assert result is not None
    manager.update.assert_called_once()
    _, kwargs = manager.update.call_args
    assert kwargs["endpoint"] == "/teams/soc-team/runs"
    assert kwargs["cron_expr"] == "*/10 * * * *"
    assert kwargs["next_run_at"] == 1800000100
    assert result["target_type"] == "team"


@pytest.mark.asyncio
async def test_create_schedule_delegates_to_service_and_records_audit():
    current_actor = cast(
        Any,
        SimpleNamespace(
            id="admin", role="admin", email="admin@example.com", is_superuser=False
        ),
    )
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
        patch.object(
            os_control, "create_schedule", return_value=created
        ) as create_mock,
        patch.object(os_control, "record_policy_event") as audit_mock,
    ):
        result = await os_control.create_scheduler_job(
            request=cast(Any, None), body=body, user=current_actor
        )
    create_mock.assert_called_once()
    assert result.id == "sched-1"
    audit_mock.assert_called_once()
    assert audit_mock.call_args.args[1].action == "scheduler.create"
    assert audit_mock.call_args.args[1].resource_id == "sched-1"


@pytest.mark.asyncio
async def test_enable_schedule_delegates_to_service():
    current_actor = cast(
        Any,
        SimpleNamespace(
            id="admin", role="admin", email="admin@example.com", is_superuser=False
        ),
    )
    enabled = {"id": "sched-1", "name": "nightly-scan", "enabled": True}
    with (
        patch.object(
            os_control, "set_schedule_enabled", return_value=enabled
        ) as enable_mock,
        patch.object(os_control, "record_policy_event"),
    ):
        result = await os_control.enable_scheduler_job(
            "sched-1", request=cast(Any, None), user=current_actor
        )
    enable_mock.assert_called_once_with("sched-1", True)
    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_trigger_requires_running_scheduler_executor():
    current_actor = cast(
        Any,
        SimpleNamespace(
            id="admin", role="admin", email="admin@example.com", is_superuser=False
        ),
    )
    with (
        patch.object(
            os_control, "get_schedule", return_value={"id": "sched-1", "enabled": True}
        ),
        pytest.raises(HTTPException) as context,
    ):
        await os_control.trigger_scheduler_job(
            "sched-1",
            request=cast(
                Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
            ),
            user=current_actor,
        )
    assert context.value.status_code == 503


@pytest.mark.asyncio
async def test_trigger_uses_running_scheduler_executor_and_records_audit():
    current_actor = cast(
        Any,
        SimpleNamespace(
            id="admin", role="admin", email="admin@example.com", is_superuser=False
        ),
    )
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
    executor.execute = AsyncMock()
    executor.execute.return_value = run
    request = cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(scheduler_executor=executor))
        ),
    )
    with (
        patch.object(
            os_control, "get_schedule", return_value={"id": "sched-1", "enabled": True}
        ),
        patch.object(
            os_control, "get_agno_postgres_db", return_value=object()
        ) as db_mock,
        patch.object(os_control, "record_policy_event") as audit_mock,
    ):
        result = await os_control.trigger_scheduler_job(
            "sched-1", request=request, user=current_actor
        )
    executor.execute.assert_awaited_once_with(
        {"id": "sched-1", "enabled": True}, db_mock.return_value, release_schedule=False
    )
    assert result["id"] == "run-1"
    audit_mock.assert_called_once()
    assert audit_mock.call_args.args[1].action == "scheduler.trigger"
    assert audit_mock.call_args.args[1].metadata == {"run_id": "run-1"}
