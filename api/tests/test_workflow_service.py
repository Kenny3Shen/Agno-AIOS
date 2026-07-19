from __future__ import annotations

import pytest

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


def test_row_payload_rejects_legacy_definition() -> None:
    with pytest.raises(
        WorkflowDefinitionError,
        match=r"workflow definition is invalid: steps\[0\]\.type is required",
    ):
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
