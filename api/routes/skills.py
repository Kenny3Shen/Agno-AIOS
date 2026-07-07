"""
Skills 管理 API
- 列出所有 Skill 及其启用状态
- 切换 Skill 启用/禁用
"""

from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from api.auth.claims import actor_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.visibility import normalize_visibility
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.skill_service import (
    install_skill_archive,
    list_skill_infos,
    set_skill_enabled,
    set_skill_visibility,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ── Pydantic models ──────────────────────────────────────────

class SkillInfo(BaseModel):
    name: str
    description: str
    enabled: bool
    has_scripts: bool
    scripts: list[str]
    visibility: str
    owner_user_id: str
    can_manage: bool


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
    name: str
    description: str
    path: str
    visibility: str
    success: bool = True


class SkillVisibilityRequest(BaseModel):
    visibility: str


# ── API 端点 ──────────────────────────────────────────────────

@router.get("", response_model=SkillListResponse)
def list_skills(user: User = Depends(require_scope("skill:read"))):
    """列出所有 Skill 及其元数据和启用状态"""
    return SkillListResponse(
        skills=[SkillInfo(**item) for item in list_skill_infos(user)]
    )


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
    user: User = Depends(require_scope("skill:write")),
):
    """上传并安装 Skill zip 包。"""
    filename = (file.filename or "").strip()
    if filename and not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Skill archive must be a zip file")

    try:
        public_name, description, dest = await to_thread.run_sync(
            partial(
                install_skill_archive,
                await file.read(),
                requested_name=name.strip(),
                visibility=visibility,
                owner_user_id=actor_id(user),
            )
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Skill '{exc}' already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_visibility = normalize_visibility(visibility)
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
