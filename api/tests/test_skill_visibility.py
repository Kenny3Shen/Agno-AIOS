from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi import UploadFile
from starlette.requests import Request

from api.routes import skills
from api.routes.skills import read_skill_archive
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


def test_delete_skill_requires_admin_and_removes_config(tmp_path, monkeypatch):
    config_file = tmp_path / "skills_config.json"
    monkeypatch.setattr(skill_service, "get_skills_dir", lambda: tmp_path)
    monkeypatch.setattr(skill_service, "get_skills_config_file", lambda: config_file)
    write_skill(tmp_path, "owned", name="Owned", visibility="private", owner="u1")
    skill_service.save_skills_config({"Owned": False, "owned": False, "Other": True})

    with pytest.raises(PermissionError):
        skill_service.delete_skill("Owned", actor("u1"))

    assert skill_service.delete_skill("Owned", actor("admin", role="admin")) == "Owned"
    assert not (tmp_path / "owned").exists()
    assert skill_service.load_skills_config() == {"Other": True}


def test_delete_skill_refuses_symlinked_directory(tmp_path, monkeypatch):
    external = tmp_path.parent / "external-skill"
    external.mkdir()
    external.joinpath("SKILL.md").write_text("---\nname: External\n---\n", encoding="utf-8")
    symlink = tmp_path / "linked"
    symlink.symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(skill_service, "get_skills_dir", lambda: tmp_path)

    with pytest.raises(ValueError, match="unsafe"):
        skill_service.delete_skill("External", actor("admin", role="admin"))
    assert external.exists()


def request() -> Request:
    return Request({"type": "http", "method": "DELETE", "path": "/api/skills/Owned", "headers": []})


@pytest.mark.asyncio
async def test_delete_skill_route_records_audit():
    current_user = actor("admin", role="admin")
    with (
        patch.object(skills, "delete_skill", return_value="Owned") as delete_mock,
        patch.object(skills, "record_audit_event_async", new=AsyncMock()) as audit_mock,
    ):
        result = await skills.delete_skill_route(request(), "Owned", current_user)

    assert result == {"success": True, "name": "Owned"}
    delete_mock.assert_called_once_with("Owned", current_user)
    assert audit_mock.await_args is not None
    assert audit_mock.await_args.kwargs["action"] == "skill.delete"
    assert audit_mock.await_args.kwargs["resource_id"] == "Owned"


@pytest.mark.asyncio
async def test_delete_skill_route_maps_missing_to_404():
    with patch.object(skills, "delete_skill", side_effect=FileNotFoundError("Missing")):
        with pytest.raises(HTTPException) as error:
            await skills.delete_skill_route(request(), "Missing", actor("admin", role="admin"))
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_read_skill_archive_rejects_uploads_over_limit():
    file = UploadFile(
        filename="oversized.zip",
        file=BytesIO(b"x" * (skill_service.MAX_SKILL_ARCHIVE_BYTES + 1)),
    )

    with pytest.raises(ValueError, match="too large"):
        await read_skill_archive(file)


def test_uploaded_skill_name_defaults_to_archive_stem():
    assert skills.uploaded_skill_name("my-skill.zip", "") == "my-skill"
    assert skills.uploaded_skill_name(r"nested\\my-skill.zip", "  ") == "my-skill"
    assert skills.uploaded_skill_name("my-skill.zip", "Custom name") == "Custom name"
