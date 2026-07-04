import json
import os
import re
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

import yaml

from api.services.runtime_paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path

DEFAULT_SKILLS_DIR = PROJECT_ROOT / "api" / "agent" / "skills"
DEFAULT_SKILLS_CONFIG_FILE = CONFIG_DIR / "skills_config.json"
MAX_SKILL_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_SKILL_EXTRACTED_BYTES = 120 * 1024 * 1024


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
