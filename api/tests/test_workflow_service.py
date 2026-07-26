from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import workflow_service
from api.services.workflow_compiler import WorkflowDefinitionError
from api.services.workflow_service import _row_payload


def test_row_payload_projects_canonical_definition() -> None:
    payload = _row_payload(
        {
            "id": "wf-1",
            "name": "Canonical workflow",
            "description": "",
            "owner_user_id": "user-1",
            "definition": {
                "name": "Canonical workflow",
                "steps": [
                    {
                        "id": "triage",
                        "type": "step",
                        "executor": {
                            "kind": "agent",
                            "ref": "security-operations",
                        },
                    }
                ],
            },
            "triggers": {},
            "enabled": True,
            "version": 1,
            "created_at": 1,
            "updated_at": 1,
        }
    )

    step = payload["definition"]["steps"][0]
    assert step["type"] == "step"
    assert step["executor"] == {"kind": "agent", "ref": "security-operations"}
    assert step["instructions"] == ""
    assert step["requires_confirmation"] is False


def test_row_payload_rejects_legacy_definition_aliases() -> None:
    with pytest.raises(WorkflowDefinitionError, match="workflow definition is invalid"):
        _row_payload(
            {
                "definition": {
                    "steps": [
                        {
                            "id": "triage",
                            "targetId": "security-operations",
                        }
                    ]
                }
            }
        )


def test_row_payload_rejects_non_object_definition() -> None:
    with pytest.raises(WorkflowDefinitionError, match="workflow definition must be an object"):
        _row_payload({"definition": None})


def _legacy_skill_definition() -> dict[str, object]:
    return {
        "name": "Historic workflow",
        "steps": [
            {
                "id": "triage",
                "type": "step",
                "executor": {"kind": "agent", "ref": "security-operations"},
                "skills": ["playbook-skill", "cve-intel-skill"],
            }
        ],
    }


def test_get_published_definition_rejects_retired_skill() -> None:
    definition = workflow_service.get_published_definition(
        {"id": "wf-1", "published_definition": _legacy_skill_definition()}
    )

    assert definition is None


@pytest.mark.asyncio
async def test_list_versions_rejects_historic_retired_skill() -> None:
    actor = SimpleNamespace(id="user-1", role="user", is_superuser=False)
    version = {
        "id": "version-1",
        "workflow_id": "wf-1",
        "version": 2,
        "name": "Historic workflow",
        "description": "",
        "definition": _legacy_skill_definition(),
        "triggers": {},
        "created_at": 1,
        "created_by": "user-1",
    }
    with (
        patch.object(
            workflow_service,
            "get_workflow_for_actor",
            new=AsyncMock(return_value={"id": "wf-1"}),
        ),
        patch.object(
            workflow_service.workflow_store,
            "list_workflow_versions",
            new=AsyncMock(return_value=([version], 1)),
        ),
    ):
        with pytest.raises(
            WorkflowDefinitionError,
            match="workflow version definition is invalid",
        ):
            await workflow_service.list_versions_for_actor(actor, "wf-1")

@pytest.mark.asyncio
async def test_restore_version_rejects_historic_retired_skill() -> None:
    actor = SimpleNamespace(id="user-1", role="user", is_superuser=False)
    version = {
        "name": "Historic workflow",
        "description": "",
        "definition": _legacy_skill_definition(),
        "triggers": {},
    }
    update = AsyncMock(return_value={"id": "wf-1"})
    with (
        patch.object(
            workflow_service,
            "get_workflow_for_actor",
            new=AsyncMock(return_value={"id": "wf-1", "name": "Current workflow"}),
        ),
        patch.object(
            workflow_service.workflow_store,
            "get_workflow_version",
            new=AsyncMock(return_value=version),
        ),
        patch.object(workflow_service, "update_workflow_for_actor", new=update),
    ):
        with pytest.raises(
            WorkflowDefinitionError,
            match="workflow version definition is invalid",
        ):
            await workflow_service.restore_version_for_actor(actor, "wf-1", 2)

    update.assert_not_awaited()
