"""
Skills 管理 API
- 列出所有 Skill 及其启用状态
- 切换 Skill 启用/禁用
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from api.auth.models import User
from api.auth.permissions import require_permission
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.skill_service import (
    install_skill_archive_async,
    list_skill_infos_async,
    set_skill_enabled_async,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ── Pydantic models ──────────────────────────────────────────

class SkillInfo(BaseModel):
    name: str
    description: str
    enabled: bool
    has_scripts: bool
    scripts: list[str]


class SkillListResponse(BaseModel):
    skills: list[SkillInfo]


class SkillToggleRequest(BaseModel):
    enabled: bool


class SkillToggleResponse(BaseModel):
    name: str
    enabled: bool


class SkillUploadResponse(BaseModel):
    name: str
    description: str
    path: str
    success: bool = True


# ── API 端点 ──────────────────────────────────────────────────

@router.get("", response_model=SkillListResponse)
async def list_skills(_user: User = Depends(require_permission("skill:read"))):
    """列出所有 Skill 及其元数据和启用状态"""
    return SkillListResponse(skills=[SkillInfo(**item) for item in await list_skill_infos_async()])


@router.put("/{skill_name}/toggle", response_model=SkillToggleResponse)
async def toggle_skill(
    request: Request,
    skill_name: str,
    body: SkillToggleRequest,
    user: User = Depends(require_permission("skill:write")),
):
    """启用或禁用指定 Skill"""
    try:
        public_name = await set_skill_enabled_async(skill_name, body.enabled)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
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
    file: UploadFile = File(...),
    user: User = Depends(require_permission("skill:write")),
):
    """上传并安装 Skill zip 包。"""
    filename = (file.filename or "").strip()
    if filename and not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Skill archive must be a zip file")

    try:
        public_name, description, dest = await install_skill_archive_async(
            await file.read(),
            requested_name=name.strip(),
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
        metadata={"filename": filename, "path": str(dest)},
        **audit_request_context(request),
    )
    return SkillUploadResponse(name=public_name, description=description, path=str(dest))
