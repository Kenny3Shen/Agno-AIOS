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

from api.auth.claims import actor_role
from api.auth.visibility import (
    can_manage_resource,
    can_read_resource,
    normalize_visibility,
    visibility_metadata,
)
from loguru import logger

from api.config import get_settings
from api.services.runtime_paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from api.utils.json import JSONDecodeError, dumps, loads

DEFAULT_SKILLS_DIR = PROJECT_ROOT / "api" / "agent" / "skills"
DEFAULT_SKILLS_CONFIG_FILE = CONFIG_DIR / "skills_config.json"
MAX_SKILL_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_SKILL_EXTRACTED_BYTES = 120 * 1024 * 1024

_SKILLS_CFG_CACHE: dict[str, bool] | None = None
_SKILLS_CFG_MTIME: float | None = None




class SkillInfoData(TypedDict):
    capability_key: str
    name: str
    description: str
    enabled: bool
    has_scripts: bool
    scripts: list[str]
    attachments: list[str]
    skill_markdown: str
    visibility: str
    owner_user_id: str
    can_manage: bool
    can_delete: bool


@dataclass(frozen=True)
class SkillMetadata:
    capability_key: str
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
    """加载 skills 启用/禁用配置；不存在则返回空 dict（默认全部启用）。

    Caches by file mtime so list/toggle hot paths avoid re-reading the same JSON.
    """
    global _SKILLS_CFG_CACHE, _SKILLS_CFG_MTIME
    config_file = get_skills_config_file()
    if not config_file.exists():
        _SKILLS_CFG_CACHE = {}
        _SKILLS_CFG_MTIME = None
        return {}
    try:
        mtime = config_file.stat().st_mtime
    except OSError:
        mtime = None
    if (
        _SKILLS_CFG_CACHE is not None
        and mtime is not None
        and mtime == _SKILLS_CFG_MTIME
    ):
        return dict(_SKILLS_CFG_CACHE)
    try:
        raw = loads(config_file.read_text(encoding="utf-8"))
        cfg = raw if isinstance(raw, dict) else {}
        # Normalize to bool map; ignore unexpected shapes.
        parsed = {
            str(key): bool(value)
            for key, value in cfg.items()
            if isinstance(key, str)
        }
    except (JSONDecodeError, OSError, TypeError, ValueError):
        logger.warning(
            "skills config unreadable at {}; treating all skills as enabled",
            config_file,
            exc_info=True,
        )
        parsed = {}
    _SKILLS_CFG_CACHE = parsed
    _SKILLS_CFG_MTIME = mtime
    return dict(parsed)


def save_skills_config(cfg: dict[str, bool]) -> None:
    global _SKILLS_CFG_CACHE, _SKILLS_CFG_MTIME
    config_file = get_skills_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(dumps(cfg, indent=True), encoding="utf-8")
    _SKILLS_CFG_CACHE = dict(cfg)
    try:
        _SKILLS_CFG_MTIME = config_file.stat().st_mtime
    except OSError:
        _SKILLS_CFG_MTIME = None


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
    except yaml.YAMLError:
        logger.debug("skill front matter YAML unreadable", exc_info=True)
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
        return SkillMetadata(skill_dir.name, name, description, visibility, owner_user_id)

    raw = md_path.read_text(encoding="utf-8")
    meta, _body = _split_skill_markdown(raw)

    if isinstance(meta, dict):
        meta_name = meta.get("name")
        meta_description = meta.get("description")
        project_metadata = meta.get("metadata")
        if not isinstance(project_metadata, dict):
            project_metadata = {}
        if isinstance(meta_name, str):
            name = meta_name
        if isinstance(meta_description, str):
            description = meta_description
        visibility = normalize_visibility(
            str(project_metadata.get("visibility") or meta.get("visibility") or "")
        )
        owner_user_id = str(
            project_metadata.get("owner_user_id")
            or project_metadata.get("user_id")
            or meta.get("owner_user_id")
            or meta.get("user_id")
            or ""
        ).strip()
    return SkillMetadata(skill_dir.name, name, description, visibility, owner_user_id)


def write_skill_metadata(skill_dir: Path, updates: dict[str, Any]) -> None:
    md_path = skill_dir / "SKILL.md"
    raw = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    meta, body = _split_skill_markdown(raw)
    project_metadata = meta.get("metadata")
    if not isinstance(project_metadata, dict):
        project_metadata = {}
    for key, value in updates.items():
        if key in {"visibility", "owner_user_id", "user_id"}:
            project_metadata[key] = value
        else:
            meta[key] = value
    # Drop obsolete recommended-default flag from older skill packages.
    project_metadata.pop("default_enabled", None)
    meta.pop("visibility", None)
    meta.pop("owner_user_id", None)
    meta.pop("user_id", None)
    meta.pop("default_enabled", None)
    if project_metadata:
        meta["metadata"] = project_metadata
    else:
        meta.pop("metadata", None)
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


def list_skill_attachments(skill_dir: Path) -> list[str]:
    """列出 protocol 相关的非脚本附件，例如 assets/ 与 references/。"""
    attachments: list[str] = []
    for dirname in ("assets", "references"):
        root = skill_dir / dirname
        if not root.is_dir():
            continue
        for entry in sorted(root.rglob("*")):
            if entry.is_file():
                attachments.append(entry.relative_to(skill_dir).as_posix())
    return attachments


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


def _skill_info_for_dir(
    skill_dir: Path,
    *,
    cfg: dict[str, bool],
    user: Any | None,
    include_detail: bool,
) -> SkillInfoData | None:
    metadata = parse_skill_metadata(skill_dir)
    visibility_info = metadata.as_visibility_metadata()
    if user is not None and not can_read_resource(user, visibility_info):
        return None
    if include_detail:
        scripts = list_skill_scripts(skill_dir)
        attachments = list_skill_attachments(skill_dir)
        markdown = read_skill_markdown(skill_dir)
    else:
        # Cheap list: only presence of scripts/ dir matters for the table badge.
        scripts = []
        attachments = []
        markdown = ""
        scripts_dir = skill_dir / "scripts"
        has_scripts_dir = scripts_dir.is_dir() and any(scripts_dir.iterdir())
    return {
        "capability_key": metadata.capability_key,
        "name": metadata.name,
        "description": metadata.description,
        "enabled": _skill_enabled_from_config(cfg, skill_dir, metadata.name),
        "has_scripts": (len(scripts) > 0) if include_detail else has_scripts_dir,
        "scripts": scripts,
        "attachments": attachments,
        # List payloads skip body + file inventory; detail loads on demand.
        "skill_markdown": markdown,
        "visibility": metadata.visibility,
        "owner_user_id": metadata.owner_user_id,
        "can_manage": user is None or can_manage_resource(user, visibility_info),
        "can_delete": user is not None and actor_role(user) == "admin",
    }


def list_skill_infos(
    user: Any | None = None,
    *,
    include_detail: bool = False,
) -> list[SkillInfoData]:
    if not get_skills_dir().is_dir():
        return []

    cfg = load_skills_config()
    skills: list[SkillInfoData] = []
    for skill_dir in iter_skill_dirs():
        info = _skill_info_for_dir(
            skill_dir,
            cfg=cfg,
            user=user,
            include_detail=include_detail,
        )
        if info is not None:
            skills.append(info)
    return skills


def get_skill_info(
    skill_name: str,
    user: Any | None = None,
    *,
    include_detail: bool = True,
) -> SkillInfoData | None:
    skill_dir = find_skill_dir(skill_name)
    if skill_dir is None:
        return None
    return _skill_info_for_dir(
        skill_dir,
        cfg=load_skills_config(),
        user=user,
        include_detail=include_detail,
    )


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




def delete_skill(skill_name: str, user: Any) -> str:
    """Permanently remove a skill and its enabled-state configuration.

    This is intentionally an administrator-only operation.  Unlike visibility
    and enablement changes, a resource owner cannot delete a Skill: uploaded
    Skills can contain executable code and removal affects the whole runtime.
    """
    if actor_role(user) != "admin":
        raise PermissionError(skill_name)

    skill_dir = find_skill_dir(skill_name)
    if skill_dir is None:
        raise FileNotFoundError(skill_name)

    # ``iter_skill_dirs`` follows directory symlinks.  Never let deletion
    # escape the configured skills directory if one was introduced manually.
    skills_root = get_skills_dir().resolve()
    if skill_dir.is_symlink() or skill_dir.parent.resolve() != skills_root:
        raise ValueError("Skill path is unsafe")

    metadata = parse_skill_metadata(skill_dir)
    shutil.rmtree(skill_dir)

    cfg = load_skills_config()
    cfg.pop(metadata.name, None)
    cfg.pop(skill_dir.name, None)
    save_skills_config(cfg)
    return metadata.name


def get_enabled_skill_dirs() -> list[Path]:
    cfg = load_skills_config()
    enabled_dirs: list[Path] = []
    for skill_dir in iter_skill_dirs():
        metadata = parse_skill_metadata(skill_dir)
        if _skill_enabled_from_config(cfg, skill_dir, metadata.name):
            enabled_dirs.append(skill_dir)
    return enabled_dirs


def resolve_enabled_skill_dirs(skill_names: list[str] | None = None) -> list[Path]:
    """Return enabled skill dirs, optionally filtered by bound names.

    - ``None``: all enabled (Chat default).
    - ``[]`` or only blanks: empty (Workflow step with no binding).
    - non-empty list: enabled ∩ requested (by metadata name or directory name).
    """
    enabled = get_enabled_skill_dirs()
    if skill_names is None:
        return enabled
    wanted = {str(name).strip() for name in skill_names if str(name).strip()}
    if not wanted:
        return []
    matched: list[Path] = []
    for skill_dir in enabled:
        metadata = parse_skill_metadata(skill_dir)
        if metadata.name in wanted or skill_dir.name in wanted:
            matched.append(skill_dir)
    return matched


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
