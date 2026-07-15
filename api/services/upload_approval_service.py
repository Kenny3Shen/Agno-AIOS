from __future__ import annotations

import os
import tempfile
import time
import zipfile
from functools import partial
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from anyio import to_thread
from fastapi import HTTPException

from api.config import get_settings
from api.persistence.upload_approvals import (
    claim_upload_approval,
    get_upload_approval,
    insert_upload_approval,
    list_upload_approvals,
    release_upload_approval,
    resolve_upload_approval,
)
from api.services.mcp_config_service import apply_mcp_upload
from api.services.notification_service import notify_submitter_of_rejection
from api.services.runtime_paths import CONFIG_DIR, resolve_project_path
from api.services.skill_service import MAX_SKILL_ARCHIVE_BYTES, install_skill_archive

MAX_PREVIEW_ENTRIES = 100
MAX_PREVIEW_FILE_BYTES = 64 * 1024
MAX_PREVIEW_TOTAL_BYTES = 256 * 1024
MAX_PREVIEW_RATIO = 100

ApprovalType = Literal["skill", "mcp"]


def _staging_dir() -> Path:
    configured = getattr(get_settings(), "agno_upload_approval_dir", None)
    return resolve_project_path(configured or CONFIG_DIR / "upload_approvals")


def _archive_path(approval_id: str) -> Path:
    return _staging_dir() / f"{approval_id}.zip"


def _write_archive(approval_id: str, archive: bytes) -> str:
    if not archive:
        raise ValueError("Skill archive is required")
    if len(archive) > MAX_SKILL_ARCHIVE_BYTES:
        raise ValueError("Skill archive is too large")
    directory = _staging_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = _archive_path(approval_id)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{approval_id}-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(archive)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return path.name


def _delete_archive(approval_id: str) -> None:
    path = _archive_path(approval_id)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _public(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record.get("payload") or {})
    # Never return a staging path or a manifest that may include credentials.
    payload.pop("archive_file", None)
    if record.get("resource_type") == "mcp":
        payload.pop("manifest", None)
    submitted_id = str(record.get("submitted_by") or "")
    resolved_id = str(record.get("resolved_by") or "")
    return {
        **record,
        "payload": payload,
        "submitted_by": {"id": submitted_id, "email": str(record.get("submitted_by_email") or "")},
        "resolved_by": ({"id": resolved_id, "email": str(record.get("resolved_by_email") or "")} if resolved_id else None),
    }


async def submit_skill_upload(
    *, archive: bytes, requested_name: str, visibility: str, submitted_by: str, submitted_by_email: str = "", filename: str
) -> dict[str, Any]:
    approval_id = str(uuid4())
    archive_file = await to_thread.run_sync(_write_archive, approval_id, archive)
    now = int(time.time())
    try:
        record = await insert_upload_approval({
            "id": approval_id, "resource_type": "skill", "status": "pending", "submitted_by": submitted_by, "submitted_by_email": submitted_by_email,
            "payload": {"name": requested_name, "visibility": visibility, "filename": filename, "archive_file": archive_file},
            "created_at": now, "updated_at": now,
        })
    except Exception:
        await to_thread.run_sync(_delete_archive, approval_id)
        raise
    return _public(record)


async def submit_mcp_upload(*, payload: dict[str, Any], submitted_by: str, submitted_by_email: str = "") -> dict[str, Any]:
    now = int(time.time())
    record = await insert_upload_approval({
        "id": str(uuid4()), "resource_type": "mcp", "status": "pending", "submitted_by": submitted_by, "submitted_by_email": submitted_by_email,
        "payload": payload, "created_at": now, "updated_at": now,
    })
    return _public(record)


async def list_submission_approvals(
    status: str | None = None,
    *,
    submitted_by: str | None = None,
    page: int = 1,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return upload approvals, optionally limited to their submitter."""
    return [
        _public(record)
        for record in await list_upload_approvals(
            status,
            submitted_by=submitted_by,
            page=page,
            limit=limit,
        )
    ]


async def list_submission_approvals_page(
    status: str | None = None,
    *,
    submitted_by: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Agno-style ``{data, meta}`` for upload submissions."""
    from api.persistence.upload_approvals import count_upload_approvals
    from api.utils.pagination import pagination_meta

    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 50), 100))
    total = await count_upload_approvals(status, submitted_by=submitted_by)
    rows = await list_submission_approvals(
        status,
        submitted_by=submitted_by,
        page=safe_page,
        limit=safe_limit,
    )
    return {
        "data": rows,
        "meta": pagination_meta(page=safe_page, limit=safe_limit, total_count=total),
    }


async def get_submission_approval(approval_id: str) -> dict[str, Any] | None:
    """Load a public upload approval without exposing its staged payload."""
    record = await get_upload_approval(approval_id)
    return _public(record) if record is not None else None


async def can_view_submission_approval(approval_id: str, *, submitted_by: str, is_admin: bool) -> bool:
    """Whether an administrator or the submitting user can view an upload approval."""
    if is_admin:
        return (await get_upload_approval(approval_id)) is not None
    record = await get_upload_approval(approval_id)
    return record is not None and str(record.get("submitted_by") or "") == submitted_by


async def resolve_submission_approval(
    approval_id: str,
    *,
    status: Literal["approved", "rejected"],
    resolved_by: str,
    resolved_by_email: str = "",
    rejection_reason: str | None = None,
) -> dict[str, Any] | None:
    normalized_reason = rejection_reason.strip() if rejection_reason else None
    if status == "rejected" and not normalized_reason:
        raise ValueError("A rejection reason is required")
    record = await get_upload_approval(approval_id)
    if record is None:
        return None
    claimed = await claim_upload_approval(
        approval_id, resolved_by=resolved_by, resolved_by_email=resolved_by_email, updated_at=int(time.time())
    )
    if claimed is None:
        raise HTTPException(status_code=409, detail="Approval is not pending")
    record = claimed

    payload = dict(record.get("payload") or {})
    try:
        if status == "approved":
            if record.get("resource_type") == "skill":
                archive_name = str(payload.get("archive_file") or "")
                if archive_name != f"{approval_id}.zip":
                    raise HTTPException(status_code=400, detail="Staged skill archive is invalid")
                try:
                    archive = await to_thread.run_sync(_archive_path(approval_id).read_bytes)
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=410, detail="Staged skill archive is missing") from exc
                await to_thread.run_sync(
                    partial(
                        install_skill_archive,
                        archive,
                        requested_name=str(payload.get("name") or ""),
                        visibility=str(payload.get("visibility") or "private"),
                        owner_user_id=str(record.get("submitted_by") or ""),
                    )
                )
            elif record.get("resource_type") == "mcp":
                await apply_mcp_upload(
                    name=str(payload.get("name") or ""), description=str(payload.get("description") or ""),
                    manifest=str(payload.get("manifest") or ""), enabled=bool(payload.get("enabled", True)),
                    visibility=str(payload.get("visibility") or "private"), owner_user_id=str(record.get("submitted_by") or ""),
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported approval resource type")
    except Exception:
        await release_upload_approval(approval_id, updated_at=int(time.time()))
        raise

    resolved = await resolve_upload_approval(
        approval_id,
        status=status,
        resolved_by=resolved_by,
        resolved_by_email=resolved_by_email,
        rejection_reason=normalized_reason if status == "rejected" else None,
        resolved_at=int(time.time()),
    )
    if resolved is None:
        raise HTTPException(status_code=409, detail="Approval is not pending")
    if record.get("resource_type") == "skill":
        await to_thread.run_sync(_delete_archive, approval_id)
    if status == "rejected":
        await notify_submitter_of_rejection(
            approval_id=approval_id,
            resource_type=str(record["resource_type"]),
            submitter_id=str(record["submitted_by"]),
            rejection_reason=normalized_reason or "",
        )
    return _public(resolved)


def _preview_archive(approval_id: str) -> dict[str, object]:
    path = _archive_path(approval_id)
    if path.is_symlink():
        raise ValueError("Staged skill archive is invalid")
    try:
        archive = zipfile.ZipFile(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError("Staged skill archive is missing") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("Staged skill archive is invalid") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_PREVIEW_ENTRIES:
            raise ValueError("Skill archive contains too many entries")
        files: list[dict[str, object]] = []
        previews: dict[str, str] = {}
        total = 0
        for info in infos:
            name = info.filename
            parts = Path(name).parts
            if name.startswith(("/", "\\")) or ".." in parts or any(part in {"", "."} for part in parts):
                raise ValueError("Skill archive contains an unsafe path")
            if info.is_dir():
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Skill archive contains a symlink")
            if info.file_size > MAX_PREVIEW_FILE_BYTES or info.compress_size == 0 and info.file_size:
                raise ValueError("Skill archive entry is too large")
            if info.file_size / max(info.compress_size, 1) > MAX_PREVIEW_RATIO:
                raise ValueError("Skill archive compression ratio is too high")
            files.append({"name": name, "size": info.file_size})
            if name.lower().endswith((".md", ".txt", ".json", ".yaml", ".yml", ".py")) and total < MAX_PREVIEW_TOTAL_BYTES:
                read_size = min(info.file_size, MAX_PREVIEW_FILE_BYTES, MAX_PREVIEW_TOTAL_BYTES - total)
                content = archive.read(info, pwd=None)[:read_size]
                total += len(content)
                previews[name] = content.decode("utf-8", errors="replace")
        return {"files": files, "previews": previews, "entry_count": len(files)}


async def preview_skill_submission(approval_id: str) -> dict[str, object]:
    record = await get_upload_approval(approval_id)
    if record is None or record.get("resource_type") != "skill":
        raise FileNotFoundError("Approval not found")
    return await to_thread.run_sync(_preview_archive, approval_id)
