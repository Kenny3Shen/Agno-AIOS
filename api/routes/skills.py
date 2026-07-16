"""
Skills 管理 API
- 列出所有 Skill 及其启用状态
- 切换 Skill 启用/禁用
"""

from functools import partial
from pathlib import PurePosixPath

from anyio import to_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from api.auth.claims import ADMIN_SCOPE, actor_id, actor_role
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.visibility import normalize_visibility
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.skill_service import (
    MAX_SKILL_ARCHIVE_BYTES,
    delete_skill,
    get_skill_info,
    install_skill_archive,
    list_skill_infos,
    set_skill_enabled,
    set_skill_visibility,
)
from api.services.upload_approval_service import submit_skill_upload
from api.services.notification_service import notify_admins_of_submission

router = APIRouter(prefix="/api/skills", tags=["skills"])

UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


def uploaded_skill_name(filename: str, requested_name: str) -> str:
    """Use the archive filename when the upload form leaves the name blank."""
    if requested_name.strip():
        return requested_name.strip()
    return PurePosixPath(filename.replace("\\", "/")).stem.strip()


async def read_skill_archive(file: UploadFile) -> bytes:
    """Read an uploaded archive with a hard limit before retaining it in memory."""
    chunks: list[bytes] = []
    total_size = 0
    while chunk := await file.read(UPLOAD_READ_CHUNK_BYTES):
        total_size += len(chunk)
        if total_size > MAX_SKILL_ARCHIVE_BYTES:
            raise ValueError("Skill archive is too large")
        chunks.append(chunk)
    return b"".join(chunks)


# ── Pydantic models ──────────────────────────────────────────

class SkillInfo(BaseModel):
    name: str
    description: str
    enabled: bool
    has_scripts: bool
    scripts: list[str]
    attachments: list[str] = []
    skill_markdown: str
    visibility: str
    owner_user_id: str
    can_manage: bool
    can_delete: bool


class SkillListResponse(BaseModel):
    skills: list[SkillInfo]


class SkillToggleRequest(BaseModel):
    enabled: bool


class SkillToggleResponse(BaseModel):
    name: str
    enabled: bool


class SkillVisibilityResponse(BaseModel):
    name: str
    visibility: str


class SkillUploadResponse(BaseModel):
    name: str = ""
    description: str = ""
    path: str = ""
    visibility: str = "private"
    success: bool = True
    status: str = "approved"
    approval_id: str | None = None


class SkillVisibilityRequest(BaseModel):
    visibility: str


# ── API 端点 ──────────────────────────────────────────────────

@router.get("", response_model=SkillListResponse)
def list_skills(user: User = Depends(require_scope("skill:read"))):
    """List skill metadata (no full SKILL.md body; use GET /{name} for detail)."""
    return SkillListResponse(
        skills=[
            SkillInfo(**item)
            for item in list_skill_infos(user, include_markdown=False)
        ]
    )


@router.get("/{skill_name}", response_model=SkillInfo)
def get_skill(skill_name: str, user: User = Depends(require_scope("skill:read"))):
    """Return one skill including full SKILL.md for the detail drawer."""
    info = get_skill_info(skill_name, user, include_markdown=True)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    return SkillInfo(**info)


@router.put("/{skill_name}/toggle", response_model=SkillToggleResponse)
async def toggle_skill(
    request: Request,
    skill_name: str,
    body: SkillToggleRequest,
    user: User = Depends(require_scope("skill:write")),
):
    """启用或禁用指定 Skill"""
    try:
        public_name = await to_thread.run_sync(
            set_skill_enabled,
            skill_name,
            body.enabled,
            user,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Skill is not manageable") from exc
    await record_audit_event_async(
        user,
        action="skill.toggle",
        resource_type="skill",
        resource_id=public_name,
        metadata={"enabled": body.enabled},
        **audit_request_context(request),
    )
    return SkillToggleResponse(name=public_name, enabled=body.enabled)


@router.post("/upload", response_model=SkillUploadResponse)
async def upload_skill(
    request: Request,
    name: str = Form(""),
    visibility: str = Form("private"),
    file: UploadFile = File(...),
    user: User = Depends(require_scope("skill:submit")),
):
    """上传 Skill；非管理员提交会进入审批队列。"""
    filename = (file.filename or "").strip()
    if filename and not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Skill archive must be a zip file")

    try:
        archive = await read_skill_archive(file)
        normalized_visibility = normalize_visibility(visibility, strict=True)
        requested_name = uploaded_skill_name(filename, name)
        if actor_role(user) != "admin":
            approval = await submit_skill_upload(
                archive=archive,
                requested_name=requested_name,
                visibility=visibility,
                submitted_by=actor_id(user),
                submitted_by_email=str(getattr(user, "email", "") or ""),
                filename=filename,
            )
            await notify_admins_of_submission(approval_id=str(approval["id"]), resource_type="skill", submitter_email=str(getattr(user, "email", "") or ""))
            await record_audit_event_async(
                user,
                action="skill.upload_submitted",
                resource_type="skill_approval",
                resource_id=str(approval["id"]),
                metadata={"filename": filename, "visibility": normalized_visibility},
                **audit_request_context(request),
            )
            return SkillUploadResponse(
                success=True, status="pending", approval_id=str(approval["id"]),
                visibility=normalized_visibility,
            )
        public_name, description, dest = await to_thread.run_sync(
            partial(
                install_skill_archive,
                archive,
                requested_name=requested_name,
                visibility=visibility,
                owner_user_id=actor_id(user),
            )
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Skill '{exc}' already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event_async(
        user,
        action="skill.upload",
        resource_type="skill",
        resource_id=public_name,
        metadata={
            "filename": filename,
            "path": str(dest),
            "visibility": normalized_visibility,
        },
        **audit_request_context(request),
    )
    return SkillUploadResponse(
        name=public_name,
        description=description,
        path=str(dest),
        visibility=normalized_visibility,
    )


@router.delete("/{skill_name}")
async def delete_skill_route(
    request: Request,
    skill_name: str,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
):
    """Permanently delete a Skill. This operation is restricted to admins."""
    try:
        public_name = await to_thread.run_sync(delete_skill, skill_name, user)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Administrator permission required") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event_async(
        user,
        action="skill.delete",
        resource_type="skill",
        resource_id=public_name,
        metadata={"requested_name": skill_name},
        **audit_request_context(request),
    )
    return {"success": True, "name": public_name}


@router.put("/{skill_name}/visibility", response_model=SkillVisibilityResponse)
async def update_skill_visibility(
    request: Request,
    skill_name: str,
    body: SkillVisibilityRequest,
    user: User = Depends(require_scope("skill:write")),
):
    try:
        public_name, visibility = await to_thread.run_sync(
            set_skill_visibility,
            skill_name,
            body.visibility,
            user,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Skill is not manageable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit_event_async(
        user,
        action="skill.visibility_update",
        resource_type="skill",
        resource_id=public_name,
        metadata={"visibility": visibility},
        **audit_request_context(request),
    )
    return SkillVisibilityResponse(name=public_name, visibility=visibility)
