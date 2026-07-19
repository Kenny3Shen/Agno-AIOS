from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import skill_reference_service as refs


def test_skill_names_in_definition_walks_nested_steps():
    definition = {
        "steps": [
            {"id": "a", "type": "step", "skills": ["alpha", "beta"]},
            {
                "id": "p",
                "type": "parallel",
                "steps": [{"id": "b", "skills": ["gamma"]}],
            },
            {
                "id": "c",
                "type": "condition",
                "steps": [{"id": "t", "skills": ["delta"]}],
                "else": [],
            },
            {
                "id": "r",
                "type": "router",
                "choices": [{"id": "ch", "name": "x", "steps": [{"id": "s", "skills": ["epsilon"]}]}],
            },
        ]
    }
    assert refs.skill_names_in_definition(definition) == {
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    }


@pytest.mark.asyncio
async def test_list_skill_workflow_references_filters_matches():
    rows = [
        {
            "id": "wf-1",
            "name": "IR",
            "version": 2,
            "definition": {"steps": [{"skills": ["playbook-skill"]}]},
        },
        {
            "id": "wf-2",
            "name": "Other",
            "version": 1,
            "definition": {"steps": [{"skills": ["other"]}]},
        },
    ]

    async def fake_list(**kwargs):
        assert kwargs["skill_name"] == "playbook-skill"
        return rows

    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)
    with patch.object(
        refs.workflow_store,
        "list_workflows_referencing_skill_text",
        new=AsyncMock(side_effect=fake_list),
    ):
        matches = await refs.list_skill_workflow_references(actor, "playbook-skill")
    assert matches["data"] == [{"workflow_id": "wf-1", "name": "IR", "version": "2"}]
    assert matches["truncated"] is False


@pytest.mark.asyncio
async def test_list_skill_workflow_references_ignores_incidental_text_matches():
    rows = [
        {
            "id": "wf-1",
            "name": "Mentions only",
            "version": 1,
            "definition": {
                "steps": [
                    {
                        "id": "a",
                        "instructions": "use playbook-skill carefully",
                        "skills": [],
                    }
                ]
            },
        }
    ]

    async def fake_list(**_kwargs):
        return rows

    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)
    with patch.object(
        refs.workflow_store,
        "list_workflows_referencing_skill_text",
        new=AsyncMock(side_effect=fake_list),
    ):
        matches = await refs.list_skill_workflow_references(actor, "playbook-skill")
    assert matches["data"] == []
    assert matches["truncated"] is False
