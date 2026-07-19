from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from api.auth.models import User
from api.routes import skills


def test_list_skills_returns_data_meta_envelope():
    user = SimpleNamespace(id="u1", role="user", is_superuser=False)
    rows = [
        {
            "name": "Owned",
            "description": "d",
            "enabled": True,
            "has_scripts": False,
            "scripts": [],
            "attachments": [],
            "skill_markdown": "",
            "visibility": "private",
            "owner_user_id": "u1",
            "can_manage": True,
            "can_delete": True,
        }
    ]
    with patch.object(skills, "list_skill_infos", return_value=rows):
        result = skills.list_skills(user=cast(User, user))
    assert [item.name for item in result["data"]] == ["Owned"]
    assert result["meta"]["total_count"] == 1
    assert result["meta"]["page"] == 1


@pytest.mark.asyncio
async def test_skill_references_projects_service_envelope():
    user = SimpleNamespace(id="u1", role="user", is_superuser=False)
    reference = {"workflow_id": "wf-1", "name": "Incident response", "version": "3"}
    with (
        patch.object(skills, "get_skill_info", return_value={"name": "cve-intel-skill"}),
        patch.object(
            skills,
            "list_skill_workflow_references",
            new=AsyncMock(return_value={"data": [reference], "truncated": True}),
        ),
    ):
        result = await skills.skill_references("cve-intel-skill", user=cast(User, user))

    assert result["data"] == [reference]
    assert result["meta"]["total_count"] == 1
    assert result["meta"]["truncated"] is True
