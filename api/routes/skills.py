"""
Skills 管理 API
- 列出所有 Skill 及其启用状态
- 切换 Skill 启用/禁用
- 预留上传 Skill 文件夹接口
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

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
async def list_skills():
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
async def toggle_skill(skill_name: str, body: SkillToggleRequest):
    """启用或禁用指定 Skill"""
    if find_skill_dir(skill_name) is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")

    public_name = set_skill_enabled(skill_name, body.enabled)
    return SkillToggleResponse(name=public_name, enabled=body.enabled)


@router.post("/upload", status_code=201)
async def upload_skill(file: UploadFile = File(...)):
    """
    预留接口：上传 Skill 压缩包（.zip / .tar.gz）。
    上传后自动解压到 Agent skills 目录。
    当前为占位实现，返回 501 Not Implemented。
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Skill 上传功能尚未实现，请手动将 Skill 文件夹放置到 "
            f"{get_skills_dir()} 目录"
        ),
    )
