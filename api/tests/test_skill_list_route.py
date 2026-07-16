from types import SimpleNamespace
from unittest.mock import patch

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
        result = skills.list_skills(user=user)  # type: ignore[arg-type]
    assert [item.name for item in result["data"]] == ["Owned"]
    assert result["meta"]["total_count"] == 1
    assert result["meta"]["page"] == 1
