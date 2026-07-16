from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from agno.knowledge.content import Content, ContentStatus, FileData
from anyio import Path as AsyncPath

from loguru import logger

from api.services.knowledge_progress import emit_progress


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
    on_progress: Callable[[Mapping[str, object]], Any] | None = None,
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
            on_progress=on_progress,
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
    on_progress: Callable[[Mapping[str, object]], Any] | None = None,
) -> None:
    """Safely reload a document under a stable content_id.

    Strategy:
    1. Build the new content payload.
    2. Write vectors under a temporary shadow content_id (old vectors stay searchable).
    3. On success, promote shadow vectors to the stable content_id and remove the old ones.
    4. On failure, drop only the shadow vectors; the live document remains available.
    """
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
    await emit_progress(
        on_progress,
        "parse",
        "running",
        message="解析中",
        detail={"content_id": content_id, "filename": filename},
    )
    await emit_progress(
        on_progress,
        "parse",
        "completed",
        message="已解析",
        detail={"content_id": content_id, "filename": filename},
    )
    await emit_progress(
        on_progress,
        "vectorize",
        "running",
        message="向量化中",
        detail={"content_id": content_id},
    )

    shadow_id = f"{content_id}__safe_{uuid4().hex}"
    shadow_content = Content(
        id=shadow_id,
        name=content.name,
        description=content.description,
        path=content.path,
        url=content.url,
        file_data=content.file_data,
        metadata=dict(content.metadata or {}),
        reader=content.reader,
        topics=content.topics,
        remote_content=content.remote_content,
    )
    shadow_content.content_hash = knowledge._build_content_hash(shadow_content)
    try:
        await knowledge._aload_content(shadow_content, True, False, None, None)
        await _assert_content_ready_async(knowledge, shadow_id)
        await _promote_shadow_content_async(
            knowledge,
            stable_content=content,
            shadow_id=shadow_id,
        )
    except Exception as exc:
        await _best_effort_remove_content_async(knowledge, shadow_id)
        await emit_progress(
            on_progress,
            "vectorize",
            "failed",
            message="失败，已保留旧内容",
            error=str(exc),
            detail={"content_id": content_id, "shadow_id": shadow_id},
        )
        raise

    # After a successful promote, remove residual shadow registration.
    # Shadow vectors were either re-pointed to the stable id or already deleted.
    await _best_effort_remove_content_async(knowledge, shadow_id)

    await emit_progress(
        on_progress,
        "vectorize",
        "completed",
        message="已切换",
        detail={"content_id": content_id},
    )


async def _assert_content_ready_async(knowledge: Any, content_id: str) -> None:
    getter = getattr(knowledge, "aget_content_by_id", None)
    if not callable(getter):
        return
    row = getter(content_id)
    if hasattr(row, "__await__"):
        row = await row
    if row is None:
        raise RuntimeError("新版本内容登记失败")
    status = getattr(row, "status", None)
    value = getattr(status, "value", status)
    status_text = str(value or "").strip().lower()
    if status_text in {"failed", "error"}:
        message = str(getattr(row, "status_message", "") or "新版本向量化失败")
        raise RuntimeError(message)


async def _promote_shadow_content_async(
    knowledge: Any,
    *,
    stable_content: Content,
    shadow_id: str,
) -> None:
    """Switch searchable vectors from shadow_id onto the stable content_id.

    Preferred path (PgVector):
      1. upsert contents_db for stable_id with the new payload
      2. delete old vectors for stable_id
      3. re-point shadow vectors to stable_id

    Fallback path:
      delete old stable vectors, load stable content, delete shadow vectors.
    """
    stable_id = str(stable_content.id or "")
    if not stable_id:
        raise RuntimeError("缺少稳定 content_id，无法完成安全切换")

    stable_content.status = ContentStatus.COMPLETED
    stable_content.status_message = ""
    await knowledge._ainsert_contents_db(stable_content)

    reassigned = await _reassign_vectors_content_id_async(
        knowledge,
        from_content_id=shadow_id,
        to_content_id=stable_id,
        replace_destination=True,
    )
    if reassigned:
        update = getattr(knowledge, "_aupdate_content", None)
        if callable(update):
            result = update(stable_content)
            if hasattr(result, "__await__"):
                await result
        return

    # Fallback for stores without in-place reassignment:
    # load the new revision onto the stable id first, then drop stale vectors.
    # Old vectors remain searchable until the new load succeeds.
    await knowledge._aload_content(stable_content, True, False, None, None)
    await _assert_content_ready_async(knowledge, stable_id)
    new_hash = str(getattr(stable_content, "content_hash", "") or "") or None
    await _delete_vectors_by_content_id_async(
        knowledge,
        stable_id,
        exclude_content_hash=new_hash,
    )
    await _delete_vectors_by_content_id_async(knowledge, shadow_id)


async def _reassign_vectors_content_id_async(
    knowledge: Any,
    *,
    from_content_id: str,
    to_content_id: str,
    replace_destination: bool = True,
) -> bool:
    """Re-point vector rows from shadow content_id to stable content_id.

    Returns True when the vector store supports in-place reassignment.
    """
    vector_db = getattr(knowledge, "vector_db", None)
    if vector_db is None:
        return False

    reassign = getattr(vector_db, "reassign_content_id", None)
    if callable(reassign):
        result = reassign(from_content_id, to_content_id)
        if hasattr(result, "__await__"):
            result = await result
        return bool(result)

    table = getattr(vector_db, "table", None)
    session_factory = getattr(vector_db, "Session", None)
    if table is None or session_factory is None:
        return False
    if not hasattr(table.c, "content_id"):
        return False

    def _sync_reassign() -> int:
        with session_factory() as sess, sess.begin():
            if replace_destination:
                sess.execute(table.delete().where(table.c.content_id == to_content_id))
            result = sess.execute(
                table.update()
                .where(table.c.content_id == from_content_id)
                .values(content_id=to_content_id)
            )
            return int(getattr(result, "rowcount", 0) or 0)

    try:
        await asyncio.to_thread(_sync_reassign)
    except Exception:
        return False
    return True


async def _best_effort_remove_content_async(
    knowledge: Any,
    content_id: str,
    *,
    vectors_only: bool = False,
    contents_only: bool = False,
) -> None:
    if not content_id:
        return
    try:
        if contents_only:
            await _delete_contents_registration_async(knowledge, content_id)
            return
        if vectors_only:
            await _delete_vectors_by_content_id_async(knowledge, content_id)
            return
        remover = getattr(knowledge, "aremove_content_by_id", None)
        if callable(remover):
            result = remover(content_id)
            if hasattr(result, "__await__"):
                await result
            return
        await _delete_vectors_by_content_id_async(knowledge, content_id)
        await _delete_contents_registration_async(knowledge, content_id)
    except Exception:
        return


async def _delete_contents_registration_async(knowledge: Any, content_id: str) -> None:
    contents_db = getattr(knowledge, "contents_db", None)
    if contents_db is not None:
        delete = getattr(contents_db, "delete_knowledge_content", None)
        if callable(delete):
            result = delete(content_id)
            if hasattr(result, "__await__"):
                await result
            return
    # Test doubles may only keep an in-memory content map.
    content_map = getattr(knowledge, "_content_by_id", None)
    if isinstance(content_map, dict):
        content_map.pop(content_id, None)


async def _delete_vectors_by_content_id_async(
    knowledge: Any,
    content_id: str,
    *,
    exclude_content_hash: str | None = None,
) -> None:
    vector_db = getattr(knowledge, "vector_db", None)
    if vector_db is None:
        return

    if exclude_content_hash:
        table = getattr(vector_db, "table", None)
        session_factory = getattr(vector_db, "Session", None)
        if table is not None and session_factory is not None and hasattr(table.c, "content_hash"):
            def _sync_delete() -> None:
                with session_factory() as sess, sess.begin():
                    sess.execute(
                        table.delete().where(
                            (table.c.content_id == content_id)
                            & (table.c.content_hash != exclude_content_hash)
                        )
                    )

            try:
                await asyncio.to_thread(_sync_delete)
                return
            except Exception:
                logger.warning(
                    "selective vector delete by content_hash failed for {}",
                    content_id,
                    exc_info=True,
                )
        # Selective delete unavailable: do not wipe the whole content_id (would
        # remove the revision we just wrote). Leave stale hashes for a later
        # rebuild, or rely on content_hash upsert semantics.
        return

    delete_by_content_id = getattr(vector_db, "delete_by_content_id", None)
    if not callable(delete_by_content_id):
        return
    result = delete_by_content_id(content_id)
    if hasattr(result, "__await__"):
        await result
