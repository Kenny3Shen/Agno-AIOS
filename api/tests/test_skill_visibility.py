from pathlib import Path
from types import SimpleNamespace

import pytest

from api.services import skill_service


def actor(actor_id: str, role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=actor_id, role=role, is_superuser=is_superuser)


def write_skill(
    root: Path,
    dirname: str,
    *,
    name: str,
    visibility: str = "private",
    owner: str = "u1",
) -> Path:
    skill_dir = root / dirname
    skill_dir.mkdir()
    skill_dir.joinpath("SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            "description: Test\n"
            "metadata:\n"
            f"  visibility: {visibility}\n"
            f"  owner_user_id: {owner}\n"
            "---\n"
            "Body\n"
        ),
        encoding="utf-8",
    )
    return skill_dir


def test_list_skill_infos_filters_public_and_owned_private(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_service, "get_skills_dir", lambda: tmp_path)
    monkeypatch.setattr(skill_service, "load_skills_config", lambda: {})
    write_skill(tmp_path, "owned", name="Owned", visibility="private", owner="u1")
    write_skill(tmp_path, "foreign", name="Foreign", visibility="private", owner="u2")
    write_skill(tmp_path, "public", name="Public", visibility="public", owner="u2")

    skills = skill_service.list_skill_infos(actor("u1"))

    assert [item["name"] for item in skills] == ["Owned", "Public"]
    assert skills[0]["visibility"] == "private"
    assert skills[0]["can_manage"] is True
    assert skills[1]["visibility"] == "public"
    assert skills[1]["can_manage"] is False


def test_set_skill_visibility_requires_owner_or_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_service, "get_skills_dir", lambda: tmp_path)
    monkeypatch.setattr(skill_service, "load_skills_config", lambda: {})
    write_skill(tmp_path, "owned", name="Owned", visibility="private", owner="u1")

    public_name, visibility = skill_service.set_skill_visibility(
        "Owned",
        "public",
        actor("u1"),
    )

    assert public_name == "Owned"
    assert visibility == "public"
    assert skill_service.list_skill_infos(actor("u1"))[0]["visibility"] == "public"
    markdown = (tmp_path / "owned" / "SKILL.md").read_text(encoding="utf-8")
    assert "metadata:\n  visibility: public" in markdown
    with pytest.raises(PermissionError):
        skill_service.set_skill_visibility("Owned", "private", actor("u2"))
