from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock, patch
from zipfile import ZipFile

import pytest

from api.services import upload_approval_service as service


def record(*, resource_type: str, status: str = "pending") -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "demo",
        "visibility": "private",
        "archive_file": "approval-1.zip",
    }
    if resource_type == "mcp":
        payload.update({"manifest": '{"mcpServers":{"demo":{"command":"python"}}}', "enabled": True})
    return {
        "id": "approval-1", "resource_type": resource_type, "status": status,
        "submitted_by": "user-1", "payload": payload, "created_at": 1, "updated_at": 1,
    }


@pytest.mark.asyncio
async def test_submit_skill_stages_archive_and_hides_staging_filename():
    inserted = AsyncMock(side_effect=lambda value: value)
    with (
        patch.object(service, "_write_archive", return_value="approval-1.zip"),
        patch.object(service, "insert_upload_approval", inserted),
        patch.object(service, "uuid4", return_value="approval-1"),
    ):
        result = await service.submit_skill_upload(
            archive=b"zip", requested_name="demo", visibility="private", submitted_by="user-1", filename="demo.zip"
        )
    assert result["status"] == "pending"
    assert "archive_file" not in result["payload"]
    assert inserted.await_args is not None
    assert inserted.await_args.args[0]["payload"]["archive_file"] == "approval-1.zip"


@pytest.mark.asyncio
async def test_list_submission_approvals_can_be_limited_to_submitter():
    stored = [record(resource_type="skill")]
    with patch.object(service, "list_upload_approvals", AsyncMock(return_value=stored)) as list_records:
        approvals = await service.list_submission_approvals("pending", submitted_by="user-1")

    list_records.assert_awaited_once_with("pending", submitted_by="user-1", page=1, limit=None)
    assert approvals[0]["submitted_by"] == {"id": "user-1", "email": ""}


@pytest.mark.asyncio
async def test_resolving_skill_approval_installs_then_removes_staged_archive(tmp_path: Path):
    staged = tmp_path / "approval-1.zip"
    staged.write_bytes(b"zip")
    install = Mock()
    resolved = {**record(resource_type="skill"), "status": "approved", "resolved_by": "admin"}
    with (
        patch.object(service, "get_upload_approval", AsyncMock(return_value=record(resource_type="skill"))),
        patch.object(service, "claim_upload_approval", AsyncMock(return_value=record(resource_type="skill"))),
        patch.object(service, "_archive_path", return_value=staged),
        patch.object(service, "install_skill_archive", install),
        patch.object(service, "resolve_upload_approval", AsyncMock(return_value=resolved)),
    ):
        result = await service.resolve_submission_approval("approval-1", status="approved", resolved_by="admin")
    install.assert_called_once()
    assert not staged.exists()
    assert result is not None
    assert result["status"] == "approved"


@pytest.mark.asyncio
async def test_rejecting_skill_approval_discards_staged_archive(tmp_path: Path):
    staged = tmp_path / "approval-1.zip"
    staged.write_bytes(b"zip")
    resolved = {**record(resource_type="skill"), "status": "rejected", "resolved_by": "admin"}
    with (
        patch.object(service, "get_upload_approval", AsyncMock(return_value=record(resource_type="skill"))),
        patch.object(service, "claim_upload_approval", AsyncMock(return_value=record(resource_type="skill"))),
        patch.object(service, "_archive_path", return_value=staged),
        patch.object(service, "resolve_upload_approval", AsyncMock(return_value=resolved)),
        patch.object(service, "notify_submitter_of_rejection", new=AsyncMock()) as notify,
    ):
        await service.resolve_submission_approval(
            "approval-1", status="rejected", resolved_by="admin", rejection_reason="Unsafe package"
        )
    assert not staged.exists()
    notify.assert_awaited_once_with(
        approval_id="approval-1",
        resource_type="skill",
        submitter_id="user-1",
        rejection_reason="Unsafe package",
    )


@pytest.mark.asyncio
async def test_rejecting_upload_requires_a_nonblank_reason():
    with pytest.raises(ValueError, match="rejection reason"):
        await service.resolve_submission_approval("approval-1", status="rejected", resolved_by="admin", rejection_reason="  ")


@pytest.mark.asyncio
async def test_resolving_mcp_approval_applies_persisted_manifest():
    apply = AsyncMock()
    resolved = {**record(resource_type="mcp"), "status": "approved", "resolved_by": "admin"}
    with (
        patch.object(service, "get_upload_approval", AsyncMock(return_value=record(resource_type="mcp"))),
        patch.object(service, "claim_upload_approval", AsyncMock(return_value=record(resource_type="mcp"))),
        patch.object(service, "apply_mcp_upload", apply),
        patch.object(service, "resolve_upload_approval", AsyncMock(return_value=resolved)),
    ):
        result = await service.resolve_submission_approval("approval-1", status="approved", resolved_by="admin")
    apply.assert_awaited_once()
    assert apply.await_args is not None
    assert apply.await_args.kwargs["owner_user_id"] == "user-1"
    assert result is not None
    assert "manifest" not in result["payload"]


def test_skill_preview_reads_safe_text_without_extracting(tmp_path: Path):
    archive = tmp_path / "approval-1.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("SKILL.md", "# Demo\n")
        zip_file.writestr("scripts/run.py", "print('safe')\n")
    with patch.object(service, "_archive_path", return_value=archive):
        preview = service._preview_archive("approval-1")
    assert preview["entry_count"] == 2
    previews = cast(dict[str, str], preview["previews"])
    assert previews["SKILL.md"] == "# Demo\n"


def test_skill_preview_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "approval-1.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../outside.txt", "no")
    with patch.object(service, "_archive_path", return_value=archive):
        with pytest.raises(ValueError, match="unsafe path"):
            service._preview_archive("approval-1")
