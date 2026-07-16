from __future__ import annotations

import mimetypes
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from anyio import Path as AsyncPath
from anyio import open_file, to_thread
from loguru import logger

from api.config import get_settings
from api.services.knowledge_ingest_service import SUPPORTED_FILE_SUFFIXES
from api.services.runtime_paths import resolve_project_path

MAX_KNOWLEDGE_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_FILENAME_BYTES = 240
UPLOAD_CHUNK_BYTES = 1024 * 1024
MANAGED_UPLOAD_METADATA_KEY = "_tais_managed_upload"
MANAGED_UPLOAD_METADATA_VERSION = 1
_UPLOAD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class AsyncUpload(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


class KnowledgeUploadTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredKnowledgeUpload:
    path: Path
    file_name: str
    file_size: int
    mime_type: str
    upload_id: str

    def metadata(self) -> dict[str, object]:
        return {
            "file_name": self.file_name,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "input_mode": "upload",
            "upload_mode": "browser",
            MANAGED_UPLOAD_METADATA_KEY: {
                "version": MANAGED_UPLOAD_METADATA_VERSION,
                "upload_id": self.upload_id,
                "file_name": self.file_name,
            },
        }


def _upload_limit_label(max_bytes: int) -> str:
    megabyte = 1024 * 1024
    if max_bytes % megabyte == 0:
        return f"{max_bytes // megabyte} MB"
    return f"{max_bytes} bytes"


def knowledge_upload_root() -> Path:
    return resolve_project_path(get_settings().agno_knowledge_upload_dir).resolve()


def safe_upload_filename(value: str | None) -> str:
    filename = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not filename or filename in {".", ".."}:
        raise ValueError("上传文件名不能为空")
    if "/" in filename or "\\" in filename:
        raise ValueError("上传文件名不能包含路径")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise ValueError("上传文件名包含不安全字符")
    if len(filename.encode("utf-8")) > MAX_UPLOAD_FILENAME_BYTES:
        raise ValueError("上传文件名过长")
    return filename


def validate_supported_upload_filename(value: str | None) -> str:
    filename = safe_upload_filename(value)
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_FILE_SUFFIXES:
        supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
        raise ValueError(f"当前知识库支持的文件后缀: {supported}")
    return filename


def upload_mime_type(filename: str, content_type: str | None) -> str:
    clean_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if clean_content_type and not any(
        ord(character) < 32 or ord(character) == 127
        for character in clean_content_type
    ):
        return clean_content_type[:255]
    guessed_type, _ = mimetypes.guess_type(filename)
    return guessed_type or "application/octet-stream"


async def _remove_known_upload_path_async(path: Path, upload_root: Path) -> None:
    def remove() -> None:
        path.unlink(missing_ok=True)
        if path.parent != upload_root:
            try:
                path.parent.rmdir()
            except OSError:
                logger.debug("knowledge upload parent dir not empty: {}", path.parent)

    await to_thread.run_sync(remove)


async def store_knowledge_upload_async(
    upload: AsyncUpload,
    *,
    max_bytes: int = MAX_KNOWLEDGE_UPLOAD_BYTES,
    upload_root: Path | None = None,
) -> StoredKnowledgeUpload:
    if max_bytes < 1:
        raise ValueError("上传大小限制必须大于 0")

    file_name = validate_supported_upload_filename(upload.filename)
    mime_type = upload_mime_type(file_name, upload.content_type)
    root = (upload_root or knowledge_upload_root()).resolve()
    upload_id = uuid4().hex
    upload_dir = root / upload_id
    destination = upload_dir / file_name

    await AsyncPath(root).mkdir(mode=0o700, parents=True, exist_ok=True)
    await AsyncPath(upload_dir).mkdir(mode=0o700, exist_ok=False)

    file_size = 0
    try:
        async with await open_file(destination, "xb") as target:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                next_size = file_size + len(chunk)
                if next_size > max_bytes:
                    raise KnowledgeUploadTooLargeError(
                        f"上传文件不能超过 {_upload_limit_label(max_bytes)}"
                    )
                await target.write(chunk)
                file_size = next_size
        if file_size == 0:
            raise ValueError("上传文件不能为空")
        await to_thread.run_sync(destination.chmod, 0o600)
    except BaseException:
        await _remove_known_upload_path_async(destination, root)
        raise

    return StoredKnowledgeUpload(
        path=destination,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        upload_id=upload_id,
    )


def _managed_upload_path(
    metadata: Mapping[str, object],
    upload_root: Path,
) -> tuple[Path, Path] | None:
    marker = metadata.get(MANAGED_UPLOAD_METADATA_KEY)
    if not isinstance(marker, Mapping):
        return None
    if marker.get("version") != MANAGED_UPLOAD_METADATA_VERSION:
        return None

    upload_id = str(marker.get("upload_id") or "")
    if _UPLOAD_ID_PATTERN.fullmatch(upload_id) is None:
        return None
    try:
        file_name = safe_upload_filename(str(marker.get("file_name") or ""))
    except ValueError:
        return None

    root = upload_root.resolve()
    upload_dir = root / upload_id
    if upload_dir.is_symlink():
        return None
    if upload_dir.resolve().parent != root:
        return None
    return upload_dir / file_name, root


async def remove_managed_upload_async(
    metadata: Mapping[str, object],
    *,
    upload_root: Path | None = None,
) -> bool:
    managed_path = _managed_upload_path(
        metadata,
        upload_root or knowledge_upload_root(),
    )
    if managed_path is None:
        return False
    path, root = managed_path
    if path.exists() and not (path.is_file() or path.is_symlink()):
        return False
    await _remove_known_upload_path_async(path, root)
    return True
