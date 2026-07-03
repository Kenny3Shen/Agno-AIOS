import json
import os
from pathlib import Path

import yaml

from api.services.runtime_paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path

DEFAULT_SKILLS_DIR = PROJECT_ROOT / "api" / "agent" / "skills"
DEFAULT_SKILLS_CONFIG_FILE = CONFIG_DIR / "skills_config.json"


def get_skills_dir() -> Path:
    return resolve_project_path(os.getenv("AGNO_SKILLS_DIR") or DEFAULT_SKILLS_DIR)


def get_skills_config_file() -> Path:
    return resolve_project_path(
        os.getenv("AGNO_SKILLS_CONFIG_FILE") or DEFAULT_SKILLS_CONFIG_FILE
    )


def load_skills_config() -> dict[str, bool]:
    """加载 skills 启用/禁用配置；不存在则返回空 dict（默认全部启用）。"""
    config_file = get_skills_config_file()
    if config_file.exists():
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_skills_config(cfg: dict[str, bool]) -> None:
    config_file = get_skills_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def iter_skill_dirs() -> list[Path]:
    skills_dir = get_skills_dir()
    if not skills_dir.is_dir():
        return []
    return [
        entry
        for entry in sorted(skills_dir.iterdir())
        if entry.is_dir() and not entry.name.startswith(".")
    ]


def parse_skill_metadata(skill_dir: Path) -> tuple[str, str]:
    """从 SKILL.md 的 YAML front matter 中提取 name 和 description。"""
    md_path = skill_dir / "SKILL.md"
    name = skill_dir.name
    description = ""
    if not md_path.exists():
        return name, description

    raw = md_path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return name, description

    parts = raw.split("---", 2)
    if len(parts) < 3:
        return name, description

    try:
        meta = yaml.safe_load(parts[1])
    except Exception:
        return name, description

    if isinstance(meta, dict):
        meta_name = meta.get("name")
        meta_description = meta.get("description")
        if isinstance(meta_name, str):
            name = meta_name
        if isinstance(meta_description, str):
            description = meta_description
    return name, description


def list_skill_scripts(skill_dir: Path) -> list[str]:
    """列出 skill 的 scripts/ 目录脚本，或 skill 根目录下的 Python 脚本。"""
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return [
            f.name for f in skill_dir.iterdir() if f.is_file() and f.suffix == ".py"
        ]
    return [
        f.name for f in scripts_dir.iterdir() if f.is_file() and f.suffix == ".py"
    ]


def is_skill_enabled(skill_dir: Path, skill_name: str | None = None) -> bool:
    cfg = load_skills_config()
    public_name = skill_name or parse_skill_metadata(skill_dir)[0]
    return cfg.get(public_name, cfg.get(skill_dir.name, True))


def find_skill_dir(skill_name: str) -> Path | None:
    for skill_dir in iter_skill_dirs():
        public_name, _ = parse_skill_metadata(skill_dir)
        if skill_name in {skill_dir.name, public_name}:
            return skill_dir
    return None


def set_skill_enabled(skill_name: str, enabled: bool) -> str:
    skill_dir = find_skill_dir(skill_name)
    if skill_dir is None:
        raise FileNotFoundError(skill_name)

    public_name, _ = parse_skill_metadata(skill_dir)
    cfg = load_skills_config()
    cfg[public_name] = enabled
    save_skills_config(cfg)
    return public_name


def get_enabled_skill_dirs() -> list[Path]:
    return [
        skill_dir
        for skill_dir in iter_skill_dirs()
        if is_skill_enabled(skill_dir, parse_skill_metadata(skill_dir)[0])
    ]
