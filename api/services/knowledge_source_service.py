from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agno.knowledge.content import Content, FileData
from anyio import Path as AsyncPath


SOURCE_METADATA_KEY = "_tais_source"
SOURCE_METADATA_VERSION = 1


async def resolve_existing_file_async(path: str) -> Path:
    file_path = Path(path).expanduser().resolve()
    if not await AsyncPath(file_path).is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return file_path


def source_digest(*values: object) -> str:
    hasher = hashlib.sha256()
    for value in values:
        hasher.update(str(value or "").encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def source_ref(kind: str, digest: str) -> dict[str, object]:
    return {
        "kind": kind,
        "digest": digest,
        "version": SOURCE_METADATA_VERSION,
    }


def metadata_with_source_ref(
    metadata: Mapping[str, object],
    source_reference: Mapping[str, object],
) -> dict[str, object]:
    return {**dict(metadata), SOURCE_METADATA_KEY: dict(source_reference)}


def mapping_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and item is not None
    }


def text_source_snapshot(
    *,
    name: str,
    description: str,
    text_content: str,
    metadata: Mapping[str, object],
    filename: str,
) -> dict[str, object]:
    return {
        "kind": "text",
        "name": name,
        "description": description,
        "text_content": text_content,
        "metadata": dict(metadata),
        "filename": filename,
        "version": SOURCE_METADATA_VERSION,
    }


def safe_public_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in metadata.items()
        if not key.startswith("_") and value is not None
    }


def path_source_snapshot(
    *,
    name: str,
    description: str,
    path: str,
    metadata: Mapping[str, object],
    filename: str,
) -> dict[str, object]:
    return {
        "kind": "path",
        "name": name,
        "description": description,
        "path": path,
        "metadata": dict(metadata),
        "filename": filename,
        "version": SOURCE_METADATA_VERSION,
    }


async def ainsert_source_snapshot_async(
    knowledge: Any,
    source: Mapping[str, object],
    *,
    reader_for_filename: Callable[[str | None, Mapping[str, object] | None], object],
    content_id: str | None = None,
) -> None:
    kind = str(source.get("kind") or "").strip().lower()
    metadata = mapping_metadata(source.get("metadata"))
    name = str(source.get("name") or metadata.get("title") or "").strip() or None
    description = str(source.get("description") or metadata.get("source") or "").strip() or None
    filename = str(source.get("filename") or metadata.get("file_name") or name or "").strip()
    reader = reader_for_filename(filename, metadata)
    if content_id:
        await _aload_source_snapshot_with_id_async(
            knowledge,
            source,
            kind=kind,
            metadata=metadata,
            name=name,
            description=description,
            filename=filename,
            reader=reader,
            content_id=content_id,
        )
        return
    kwargs: dict[str, object] = {
        "name": name,
        "description": description,
        "metadata": metadata,
        "reader": reader,
        "upsert": True,
        "skip_if_exists": False,
    }
    if kind == "text":
        text_content = source.get("text_content")
        if not isinstance(text_content, str) or not text_content.strip():
            raise ValueError("当前知识记录缺少可重建的文本 source 快照")
        kwargs["text_content"] = text_content
    elif kind == "path":
        path = str(source.get("path") or metadata.get("file_path") or "").strip()
        if not path:
            raise ValueError("当前知识记录缺少可重建的文件路径 source 快照")
        resolved_path = await resolve_existing_file_async(path)
        kwargs["path"] = str(resolved_path)
    else:
        raise ValueError("当前知识记录缺少可重建的原始 source 快照")
    await knowledge.ainsert(**kwargs)


async def _aload_source_snapshot_with_id_async(
    knowledge: Any,
    source: Mapping[str, object],
    *,
    kind: str,
    metadata: Mapping[str, object],
    name: str | None,
    description: str | None,
    filename: str,
    reader: Any,
    content_id: str,
) -> None:
    content: Content
    if kind == "text":
        text_content = source.get("text_content")
        if not isinstance(text_content, str) or not text_content.strip():
            raise ValueError("当前知识记录缺少可重建的文本 source 快照")
        content = Content(
            id=content_id,
            name=name,
            description=description,
            file_data=FileData(content=text_content, type="Text", filename=filename or None),
            metadata=dict(metadata),
            reader=reader,
        )
    elif kind == "path":
        path = str(source.get("path") or metadata.get("file_path") or "").strip()
        if not path:
            raise ValueError("当前知识记录缺少可重建的文件路径 source 快照")
        resolved_path = await resolve_existing_file_async(path)
        content = Content(
            id=content_id,
            name=name,
            description=description,
            path=str(resolved_path),
            metadata=dict(metadata),
            reader=reader,
        )
    else:
        raise ValueError("当前知识记录缺少可重建的原始 source 快照")

    content.content_hash = knowledge._build_content_hash(content)
    await _delete_vectors_by_content_id_async(knowledge, content_id)
    await knowledge._aload_content(content, True, False, None, None)


async def _delete_vectors_by_content_id_async(knowledge: Any, content_id: str) -> None:
    vector_db = getattr(knowledge, "vector_db", None)
    delete_by_content_id = getattr(vector_db, "delete_by_content_id", None)
    if not callable(delete_by_content_id):
        return
    result = delete_by_content_id(content_id)
    if hasattr(result, "__await__"):
        await result
