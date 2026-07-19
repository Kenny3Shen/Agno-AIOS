from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes import workflows
from api.services.workflow_compiler import (
    WorkflowDefinitionError,
    validate_and_normalize_definition,
)
from api.tests.route_fakes import route_dependency


def actor(user_id: str = "u1", role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False, email="u@example.com")


def test_list_workflows_allows_user_with_workflows_read():
    dependency = route_dependency(workflows.router, "list_workflows")
    assert dependency(user=actor()) is not None


def test_run_workflow_rejects_guest():
    dependency = route_dependency(workflows.router, "run_workflow")
    with pytest.raises(HTTPException) as exc:
        dependency(user=actor("g1", "guest"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_workflow_maps_definition_errors_to_422():
    body = workflows.WorkflowWriteRequest(name="x", definition={"steps": []})
    request = MagicMock()
    request.client = SimpleNamespace(host="127.0.0.1")
    request.headers = {"user-agent": "test"}
    with patch.object(
        workflows,
        "create_workflow_for_actor",
        AsyncMock(side_effect=WorkflowDefinitionError("definition.steps must be a non-empty array")),
    ):
        with pytest.raises(HTTPException) as exc:
            await workflows.create_workflow(body, request=request, user=actor())
    assert exc.value.status_code == 422
    assert "non-empty" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_workflow_success_audits():
    body = workflows.WorkflowWriteRequest(
        name="IR",
        definition={
            "steps": [
                {
                    "id": "t",
                    "name": "T",
                    "executor": {"kind": "agent", "ref": "security-operations"},
                }
            ]
        },
    )
    request = MagicMock()
    request.client = SimpleNamespace(host="127.0.0.1")
    request.headers = {"user-agent": "test"}
    row = {
        "id": "wf-1",
        "name": "IR",
        "description": "",
        "owner_user_id": "u1",
        "definition": body.definition,
        "enabled": True,
        "version": 1,
        "created_at": 1,
        "updated_at": 1,
    }
    with (
        patch.object(workflows, "create_workflow_for_actor", AsyncMock(return_value=row)),
        patch.object(workflows, "record_audit_event_async", AsyncMock()) as audit,
    ):
        result = await workflows.create_workflow(body, request=request, user=actor())
    assert result["id"] == "wf-1"
    audit.assert_awaited_once()



@pytest.mark.asyncio
async def test_trigger_history_requires_read_and_returns_data():
    request_items = [
        {
            "id": 1,
            "action": "workflow.trigger.cron",
            "status": "success",
            "resource_id": "wf-1",
            "created_at": "2026-01-01T00:00:00",
            "metadata": {"run_id": "r1", "session_id": "s1", "source": "cron"},
        }
    ]
    with (
        patch.object(workflows, "get_workflow_for_actor", AsyncMock(return_value={"id": "wf-1"})),
        patch.object(
            workflows,
            "list_audit_logs_async",
            AsyncMock(side_effect=[(request_items, 1), ([], 0)]),
        ),
    ):
        result = await workflows.list_workflow_trigger_history(
            workflow_id="wf-1", page=1, limit=20, user=actor()
        )
    assert result["meta"]["total_count"] == 1
    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == 20
    assert result["data"][0]["run_id"] == "r1"
    assert result["data"][0]["source"] == "cron"



def test_run_workflow_allows_user_with_workflows_run():
    dependency = route_dependency(workflows.router, "run_workflow")
    assert dependency(user=actor()) is not None


@pytest.mark.asyncio
async def test_list_templates_returns_security_playbooks():
    result = await workflows.list_templates(user=actor())
    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == len(result["data"])
    assert result["meta"]["total_count"] == len(result["data"])
    ids = {item["id"] for item in result["data"]}
    assert "ir-triage" in ids
    assert "alert-fanout" in ids
    for item in result["data"]:
        assert validate_and_normalize_definition(item["definition"])["steps"]


@pytest.mark.asyncio
async def test_list_executors_returns_data_meta_envelope():
    result = await workflows.list_executors(user=actor())

    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == len(result["data"])
    assert result["meta"]["total_count"] == len(result["data"])
    assert {item["ref"] for item in result["data"]} >= {"security-operations", "safe-fallback"}


@pytest.mark.asyncio
async def test_list_workflows_forwards_q():
    captured: dict = {}

    async def fake_list(actor, **kwargs):
        captured.update(kwargs)
        return {"data": [], "meta": {"page": 1, "limit": 20, "total_count": 0, "total_pages": 0, "search_time_ms": 0}}

    with patch.object(workflows, "list_workflows_for_actor", fake_list):
        result = await workflows.list_workflows(user=actor(), q=" IR ")
    assert result["data"] == []
    assert captured["q"] == " IR "
