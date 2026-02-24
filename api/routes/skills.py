"""
Skills 管理 API
- 列出所有 Skill 及其启用状态
- 切换 Skill 启用/禁用
- 预留上传 Skill 文件夹接口
"""

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/api/skills", tags=["skills"])

SKILLS_DIR = Path(".skills")
SKILLS_CONFIG_FILE = Path("tmp/skills_config.json")


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


# ── 内部工具函数 ─────────────────────────────────────────────

def _load_config() -> dict[str, bool]:
    """加载 skills 启用/禁用配置；不存在则返回空 dict（默认全部启用）"""
    if SKILLS_CONFIG_FILE.exists():
        try:
            return json.loads(SKILLS_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(cfg: dict[str, bool]) -> None:
    SKILLS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    SKILLS_CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _parse_skill_md(skill_dir: Path) -> tuple[str, str]:
    """从 SKILL.md 的 YAML front-matter 中提取 name 和 description"""
    md_path = skill_dir / "SKILL.md"
    name = skill_dir.name
    description = ""
    if md_path.exists():
        raw = md_path.read_text(encoding="utf-8")
        # 解析 YAML front-matter（--- ... ---）
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1])
                    if isinstance(meta, dict):
                        name = meta.get("name", name)
                        description = meta.get("description", "")
                except Exception:
                    pass
    return name, description


def _list_scripts(skill_dir: Path) -> list[str]:
    """列出 skill 的 scripts/ 目录下的脚本文件"""
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        # 也可能直接在 skill_dir 下有 .py 文件（如 intranet-ip-skill/agent.py）
        return [
            f.name for f in skill_dir.iterdir()
            if f.is_file() and f.suffix == ".py"
        ]
    return [
        f.name for f in scripts_dir.iterdir()
        if f.is_file() and f.suffix == ".py"
    ]


# ── API 端点 ──────────────────────────────────────────────────

@router.get("", response_model=SkillListResponse)
async def list_skills():
    """列出所有 Skill 及其元数据和启用状态"""
    if not SKILLS_DIR.is_dir():
        return SkillListResponse(skills=[])

    cfg = _load_config()
    skills: list[SkillInfo] = []

    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        name, description = _parse_skill_md(entry)
        scripts = _list_scripts(entry)
        # 默认启用
        enabled = cfg.get(name, True)
        skills.append(
            SkillInfo(
                name=name,
                description=description,
                enabled=enabled,
                has_scripts=len(scripts) > 0,
                scripts=scripts,
            )
        )

    return SkillListResponse(skills=skills)


@router.put("/{skill_name}/toggle", response_model=SkillToggleResponse)
async def toggle_skill(skill_name: str, body: SkillToggleRequest):
    """启用或禁用指定 Skill"""
    # 校验 skill 是否存在
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")

    cfg = _load_config()
    cfg[skill_name] = body.enabled
    _save_config(cfg)

    return SkillToggleResponse(name=skill_name, enabled=body.enabled)


@router.post("/upload", status_code=201)
async def upload_skill(file: UploadFile = File(...)):
    """
    预留接口：上传 Skill 压缩包（.zip / .tar.gz）。
    上传后自动解压到 .skills/ 目录。
    当前为占位实现，返回 501 Not Implemented。
    """
    raise HTTPException(
        status_code=501,
        detail="Skill 上传功能尚未实现，请手动将 Skill 文件夹放置到 .skills/ 目录",
    )
