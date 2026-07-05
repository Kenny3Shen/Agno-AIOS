import json
import os
import re
import shutil
import tempfile
import zipfile
from functools import partial
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import TypedDict

import yaml
from anyio import Path as AsyncPath
from anyio import to_thread

from api.config import get_settings
from api.services.runtime_paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path

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


def get_skills_dir() -> Path:
    return resolve_project_path(get_settings().agno_skills_dir or DEFAULT_SKILLS_DIR)


def get_skills_config_file() -> Path:
    return resolve_project_path(
        get_settings().agno_skills_config_file or DEFAULT_SKILLS_CONFIG_FILE
    )


async def load_skills_config_async() -> dict[str, bool]:
    """加载 skills 启用/禁用配置；不存在则返回空 dict（默认全部启用）。"""
    config_file = AsyncPath(get_skills_config_file())
    if not await config_file.exists():
        return {}
    try:
        return json.loads(await config_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def save_skills_config_async(cfg: dict[str, bool]) -> None:
    config_file = AsyncPath(get_skills_config_file())
    await config_file.parent.mkdir(parents=True, exist_ok=True)
    await config_file.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def iter_skill_dirs_async() -> list[Path]:
    skills_dir = AsyncPath(get_skills_dir())
    if not await skills_dir.is_dir():
        return []

    entries: list[Path] = []
    async for entry in skills_dir.iterdir():
        if await entry.is_dir() and not entry.name.startswith("."):
            entries.append(Path(os.fspath(entry)))
    return sorted(entries)


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


async def parse_skill_metadata_async(skill_dir: Path) -> tuple[str, str]:
    """从 SKILL.md 的 YAML front matter 中提取 name 和 description。"""
    md_path = AsyncPath(skill_dir / "SKILL.md")
    name = skill_dir.name
    description = ""
    if not await md_path.exists():
        return name, description

    raw = await md_path.read_text(encoding="utf-8")
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


async def list_skill_scripts_async(skill_dir: Path) -> list[str]:
    """列出 skill 的 scripts/ 目录脚本，或 skill 根目录下的 Python 脚本。"""
    scripts_dir = AsyncPath(skill_dir / "scripts")
    source_dir = scripts_dir if await scripts_dir.is_dir() else AsyncPath(skill_dir)
    scripts: list[str] = []
    async for entry in source_dir.iterdir():
        if await entry.is_file() and entry.suffix == ".py":
            scripts.append(entry.name)
    return scripts


def _skill_enabled_from_config(
    cfg: dict[str, bool], skill_dir: Path, skill_name: str
) -> bool:
    return cfg.get(skill_name, cfg.get(skill_dir.name, True))


async def find_skill_dir_async(skill_name: str) -> Path | None:
    for skill_dir in await iter_skill_dirs_async():
        public_name, _ = await parse_skill_metadata_async(skill_dir)
        if skill_name in {skill_dir.name, public_name}:
            return skill_dir
    return None


async def list_skill_infos_async() -> list[SkillInfoData]:
    if not await AsyncPath(get_skills_dir()).is_dir():
        return []

    cfg = await load_skills_config_async()
    skills: list[SkillInfoData] = []
    for skill_dir in await iter_skill_dirs_async():
        name, description = await parse_skill_metadata_async(skill_dir)
        scripts = await list_skill_scripts_async(skill_dir)
        skills.append(
            {
                "name": name,
                "description": description,
                "enabled": _skill_enabled_from_config(cfg, skill_dir, name),
                "has_scripts": len(scripts) > 0,
                "scripts": scripts,
            }
        )
    return skills


async def set_skill_enabled_async(skill_name: str, enabled: bool) -> str:
    skill_dir = await find_skill_dir_async(skill_name)
    if skill_dir is None:
        raise FileNotFoundError(skill_name)

    public_name, _ = await parse_skill_metadata_async(skill_dir)
    cfg = await load_skills_config_async()
    cfg[public_name] = enabled
    await save_skills_config_async(cfg)
    return public_name


async def get_enabled_skill_dirs_async() -> list[Path]:
    cfg = await load_skills_config_async()
    enabled_dirs: list[Path] = []
    for skill_dir in await iter_skill_dirs_async():
        public_name, _ = await parse_skill_metadata_async(skill_dir)
        if _skill_enabled_from_config(cfg, skill_dir, public_name):
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
) -> tuple[str, str, Path]:
    if not archive:
        raise ValueError("Skill archive is required")
    if len(archive) > MAX_SKILL_ARCHIVE_BYTES:
        raise ValueError("Skill archive is too large")

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
        public_name, description = parse_skill_metadata(skill_root)
        install_name = _safe_dir_name(requested_name or public_name or skill_root.name)
        dest = skills_dir / install_name
        if dest.exists():
            raise FileExistsError(install_name)

        if skill_root == extract_dir:
            _move_contents(skill_root, dest)
        else:
            shutil.move(str(skill_root), str(dest))
        return public_name or install_name, description, dest
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


async def install_skill_archive_async(
    archive: bytes,
    *,
    requested_name: str = "",
) -> tuple[str, str, Path]:
    return await to_thread.run_sync(
        partial(install_skill_archive, archive, requested_name=requested_name),
    )
