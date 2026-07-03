"""
Skills 管理 API
- 列出所有 Skill 及其启用状态
- 切换 Skill 启用/禁用
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth.models import User
from api.auth.permissions import require_permission
from api.services.audit_service import audit_request_context, record_audit_event
from api.services.skill_service import (
    find_skill_dir,
    get_skills_dir,
    is_skill_enabled,
    iter_skill_dirs,
    list_skill_scripts,
    parse_skill_metadata,
    set_skill_enabled,
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


# ── API 端点 ──────────────────────────────────────────────────

@router.get("", response_model=SkillListResponse)
async def list_skills(_user: User = Depends(require_permission("skill:read"))):
    """列出所有 Skill 及其元数据和启用状态"""
    if not get_skills_dir().is_dir():
        return SkillListResponse(skills=[])

    skills: list[SkillInfo] = []

    for entry in iter_skill_dirs():
        name, description = parse_skill_metadata(entry)
        scripts = list_skill_scripts(entry)
        skills.append(
            SkillInfo(
                name=name,
                description=description,
                enabled=is_skill_enabled(entry, name),
                has_scripts=len(scripts) > 0,
                scripts=scripts,
            )
        )

    return SkillListResponse(skills=skills)


@router.put("/{skill_name}/toggle", response_model=SkillToggleResponse)
async def toggle_skill(
    request: Request,
    skill_name: str,
    body: SkillToggleRequest,
    user: User = Depends(require_permission("skill:write")),
):
    """启用或禁用指定 Skill"""
    if find_skill_dir(skill_name) is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")

    public_name = set_skill_enabled(skill_name, body.enabled)
    record_audit_event(
        user,
        action="skill.toggle",
        resource_type="skill",
        resource_id=public_name,
        metadata={"enabled": body.enabled},
        **audit_request_context(request),
    )
    return SkillToggleResponse(name=public_name, enabled=body.enabled)
