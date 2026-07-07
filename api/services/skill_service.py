import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, TypedDict

import yaml

from api.auth.visibility import (
    can_manage_resource,
    can_read_resource,
    normalize_visibility,
    visibility_metadata,
)
from api.config import get_settings
from api.services.runtime_paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from api.utils.json import dumps, loads

DEFAULT_SKILLS_DIR = PROJECT_ROOT / "api" / "agent" / "skills"
DEFAULT_SKILLS_CONFIG_FILE = CONFIG_DIR / "skills_config.json"
MAX_SKILL_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_SKILL_EXTRACTED_BYTES = 120 * 1024 * 1024


class SkillInfoData(TypedDict):
    name: str
    description: str
    enabled: bool
    has_scripts: bool
    scripts: list[str]
    skill_markdown: str
    visibility: str
    owner_user_id: str
    can_manage: bool


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    visibility: str
    owner_user_id: str

    def as_visibility_metadata(self) -> dict[str, str]:
        metadata = {"visibility": self.visibility}
        if self.owner_user_id:
            metadata["owner_user_id"] = self.owner_user_id
            metadata["user_id"] = self.owner_user_id
        return metadata


def get_skills_dir() -> Path:
    return resolve_project_path(get_settings().agno_skills_dir or DEFAULT_SKILLS_DIR)


def get_skills_config_file() -> Path:
    return resolve_project_path(
        get_settings().agno_skills_config_file or DEFAULT_SKILLS_CONFIG_FILE
    )


def load_skills_config() -> dict[str, bool]:
    """加载 skills 启用/禁用配置；不存在则返回空 dict（默认全部启用）。"""
    config_file = get_skills_config_file()
    if not config_file.exists():
        return {}
    try:
        return loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_skills_config(cfg: dict[str, bool]) -> None:
    config_file = get_skills_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(dumps(cfg, indent=True), encoding="utf-8")


def iter_skill_dirs() -> list[Path]:
    skills_dir = get_skills_dir()
    if not skills_dir.is_dir():
        return []

    entries: list[Path] = []
    for entry in skills_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            entries.append(Path(os.fspath(entry)))
    return sorted(entries)


def _split_skill_markdown(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        meta = yaml.safe_load(parts[1])
    except Exception:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), parts[2].lstrip("\n")


def parse_skill_metadata(skill_dir: Path) -> SkillMetadata:
    """从 SKILL.md 的 YAML front matter 中提取 Skill 元数据。"""
    md_path = skill_dir / "SKILL.md"
    name = skill_dir.name
    description = ""
    visibility = "private"
    owner_user_id = ""
    if not md_path.exists():
        return SkillMetadata(name, description, visibility, owner_user_id)

    raw = md_path.read_text(encoding="utf-8")
    meta, _body = _split_skill_markdown(raw)

    if isinstance(meta, dict):
        meta_name = meta.get("name")
        meta_description = meta.get("description")
        if isinstance(meta_name, str):
            name = meta_name
        if isinstance(meta_description, str):
            description = meta_description
        visibility = normalize_visibility(str(meta.get("visibility") or ""))
        owner_user_id = str(meta.get("owner_user_id") or meta.get("user_id") or "").strip()
    return SkillMetadata(name, description, visibility, owner_user_id)


def write_skill_metadata(skill_dir: Path, updates: dict[str, str]) -> None:
    md_path = skill_dir / "SKILL.md"
    raw = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    meta, body = _split_skill_markdown(raw)
    meta.update(updates)
    md_path.write_text(
        "---\n"
        + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        + "---\n"
        + body,
        encoding="utf-8",
    )


def list_skill_scripts(skill_dir: Path) -> list[str]:
    """列出 skill 的 scripts/ 目录脚本，或 skill 根目录下的 Python 脚本。"""
    scripts_dir = skill_dir / "scripts"
    source_dir = scripts_dir if scripts_dir.is_dir() else skill_dir
    scripts: list[str] = []
    for entry in source_dir.iterdir():
        if entry.is_file() and entry.suffix == ".py":
            scripts.append(entry.name)
    return scripts


def read_skill_markdown(skill_dir: Path) -> str:
    md_path = skill_dir / "SKILL.md"
    if not md_path.exists():
        return ""
    return md_path.read_text(encoding="utf-8")


def _skill_enabled_from_config(
    cfg: dict[str, bool], skill_dir: Path, skill_name: str
) -> bool:
    return cfg.get(skill_name, cfg.get(skill_dir.name, True))


def find_skill_dir(skill_name: str) -> Path | None:
    for skill_dir in iter_skill_dirs():
        metadata = parse_skill_metadata(skill_dir)
        if skill_name in {skill_dir.name, metadata.name}:
            return skill_dir
    return None


def list_skill_infos(user: Any | None = None) -> list[SkillInfoData]:
    if not get_skills_dir().is_dir():
        return []

    cfg = load_skills_config()
    skills: list[SkillInfoData] = []
    for skill_dir in iter_skill_dirs():
        metadata = parse_skill_metadata(skill_dir)
        visibility_info = metadata.as_visibility_metadata()
        if user is not None and not can_read_resource(user, visibility_info):
            continue
        scripts = list_skill_scripts(skill_dir)
        skills.append(
            {
                "name": metadata.name,
                "description": metadata.description,
                "enabled": _skill_enabled_from_config(cfg, skill_dir, metadata.name),
                "has_scripts": len(scripts) > 0,
                "scripts": scripts,
                "skill_markdown": read_skill_markdown(skill_dir),
                "visibility": metadata.visibility,
                "owner_user_id": metadata.owner_user_id,
                "can_manage": user is None or can_manage_resource(user, visibility_info),
            }
        )
    return skills


def set_skill_enabled(skill_name: str, enabled: bool, user: Any | None = None) -> str:
    skill_dir = find_skill_dir(skill_name)
    if skill_dir is None:
        raise FileNotFoundError(skill_name)

    metadata = parse_skill_metadata(skill_dir)
    if user is not None and not can_manage_resource(
        user, metadata.as_visibility_metadata()
    ):
        raise PermissionError(skill_name)
    cfg = load_skills_config()
    cfg[metadata.name] = enabled
    save_skills_config(cfg)
    return metadata.name


def set_skill_visibility(skill_name: str, visibility: str, user: Any) -> tuple[str, str]:
    skill_dir = find_skill_dir(skill_name)
    if skill_dir is None:
        raise FileNotFoundError(skill_name)

    metadata = parse_skill_metadata(skill_dir)
    if not can_manage_resource(user, metadata.as_visibility_metadata()):
        raise PermissionError(skill_name)
    normalized_visibility = normalize_visibility(visibility, strict=True)
    write_skill_metadata(skill_dir, {"visibility": normalized_visibility})
    return metadata.name, normalized_visibility


def get_enabled_skill_dirs() -> list[Path]:
    cfg = load_skills_config()
    enabled_dirs: list[Path] = []
    for skill_dir in iter_skill_dirs():
        metadata = parse_skill_metadata(skill_dir)
        if _skill_enabled_from_config(cfg, skill_dir, metadata.name):
            enabled_dirs.append(skill_dir)
    return enabled_dirs


def _safe_dir_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return safe or "skill"


def _validate_zip_member(info: zipfile.ZipInfo) -> int:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Skill archive contains an unsafe path")
    if not path.parts or path.parts[0] in {"", ".", "__MACOSX"}:
        return 0
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        raise ValueError("Skill archive must not contain symlinks")
    return int(info.file_size)


def _find_extracted_skill_root(extract_dir: Path) -> Path:
    candidates: list[Path] = []
    if (extract_dir / "SKILL.md").is_file():
        candidates.append(extract_dir)
    for child in extract_dir.iterdir():
        if child.is_dir() and child.name != "__MACOSX" and (child / "SKILL.md").is_file():
            candidates.append(child)
    if len(candidates) != 1:
        raise ValueError("Skill archive must contain exactly one SKILL.md")
    return candidates[0]


def _move_contents(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=False)
    for child in source.iterdir():
        shutil.move(str(child), str(dest / child.name))


def install_skill_archive(
    archive: bytes,
    *,
    requested_name: str = "",
    visibility: str = "private",
    owner_user_id: str | None = None,
) -> tuple[str, str, Path]:
    if not archive:
        raise ValueError("Skill archive is required")
    if len(archive) > MAX_SKILL_ARCHIVE_BYTES:
        raise ValueError("Skill archive is too large")
    normalized_visibility = normalize_visibility(visibility, strict=True)

    skills_dir = get_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    temp_parent = Path(tempfile.mkdtemp(prefix=".skill-upload-", dir=skills_dir))
    extract_dir = temp_parent / "extract"
    extract_dir.mkdir()

    try:
        try:
            with zipfile.ZipFile(BytesIO(archive)) as zf:
                total_size = sum(_validate_zip_member(info) for info in zf.infolist())
                if total_size > MAX_SKILL_EXTRACTED_BYTES:
                    raise ValueError("Skill archive extracts to too much data")
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError("Skill archive must be a valid zip file") from exc

        skill_root = _find_extracted_skill_root(extract_dir)
        metadata = parse_skill_metadata(skill_root)
        install_name = _safe_dir_name(requested_name or metadata.name or skill_root.name)
        dest = skills_dir / install_name
        if dest.exists():
            raise FileExistsError(install_name)

        if skill_root == extract_dir:
            _move_contents(skill_root, dest)
        else:
            shutil.move(str(skill_root), str(dest))
        write_skill_metadata(
            dest,
            visibility_metadata(normalized_visibility, owner_user_id),
        )
        return metadata.name or install_name, metadata.description, dest
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)
