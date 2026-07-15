from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from api.routes import workflows
from api.services.workflow_compiler import WorkflowDefinitionError


def actor(user_id: str = "u1", role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False, email="u@example.com")


def route_dependency(endpoint_name: str):
    for route in workflows.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_list_workflows_allows_user_with_workflows_read():
    dependency = route_dependency("list_workflows")
    assert dependency(user=actor()) is not None


def test_run_workflow_rejects_guest():
    dependency = route_dependency("run_workflow")
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
