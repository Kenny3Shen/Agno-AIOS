"""Chat file attachments via Agno media types (aligned with Agno OS agent upload)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from loguru import logger

from agno.media import Audio, File, Image, Video
from agno.os.utils import (
    classify_upload_file,
    process_audio,
    process_document,
    process_image,
    process_video,
)

# Keep chat uploads bounded (not Knowledge-scale).
MAX_CHAT_FILES = 8
MAX_CHAT_FILE_BYTES = 20 * 1024 * 1024
MAX_CHAT_TOTAL_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True)
class ChatMediaBundle:
    """Agno media objects + light metadata for UI history projection."""

    images: tuple[Image, ...] = ()
    files: tuple[File, ...] = ()
    audio: tuple[Audio, ...] = ()
    videos: tuple[Video, ...] = ()
    # UI-facing: name / mime / kind (image|document|audio|video)
    attachments: tuple[dict[str, str], ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.images or self.files or self.audio or self.videos)


def _attachment_meta(
    *,
    kind: str,
    filename: str | None,
    mime: str | None,
) -> dict[str, str]:
    name = (filename or "file").strip() or "file"
    return {
        "name": name,
        "mime": (mime or "").strip(),
        "kind": kind,
    }


async def process_chat_uploads(files: list[Any] | None) -> ChatMediaBundle:
    """Classify and convert multipart uploads into Agno Image/File/Audio/Video."""
    if not files:
        return ChatMediaBundle()

    uploads = [f for f in files if f is not None and getattr(f, "filename", None)]
    if not uploads:
        # Some clients send empty file parts; ignore.
        uploads = [f for f in files if f is not None]
    if len(uploads) > MAX_CHAT_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {MAX_CHAT_FILES} 个附件",
        )

    images: list[Image] = []
    docs: list[File] = []
    audios: list[Audio] = []
    videos: list[Video] = []
    attachments: list[dict[str, str]] = []
    total = 0

    for upload in uploads:
        # Size gate: sync read (Agno processors also use file.file.read).
        file_obj = getattr(upload, "file", None)
        if file_obj is not None:
            try:
                file_obj.seek(0)
            except Exception:
                pass
            raw = file_obj.read()
            try:
                file_obj.seek(0)
            except Exception:
                pass
        else:
            raw = await upload.read()
            if hasattr(upload, "seek"):
                await upload.seek(0)
        size = len(raw or b"")
        if size <= 0:
            raise HTTPException(status_code=400, detail=f"空文件: {upload.filename or 'file'}")
        if size > MAX_CHAT_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"文件过大（上限 {MAX_CHAT_FILE_BYTES // (1024 * 1024)}MB）: {upload.filename or 'file'}",
            )
        total += size
        if total > MAX_CHAT_TOTAL_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"附件总大小超过 {MAX_CHAT_TOTAL_BYTES // (1024 * 1024)}MB",
            )

        category = classify_upload_file(upload)
        if category is None:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {upload.filename or upload.content_type or 'unknown'}",
            )
        try:
            if category == "image":
                media = process_image(upload)
                images.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="image",
                        filename=upload.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            elif category == "audio":
                media = process_audio(upload)
                audios.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="audio",
                        filename=upload.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            elif category == "video":
                media = process_video(upload)
                videos.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="video",
                        filename=upload.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            elif category == "document":
                media = process_document(upload)
                if media is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"无法解析文档: {upload.filename or 'file'}",
                    )
                docs.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="document",
                        filename=upload.filename or media.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type")
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("chat attachment process failed: {}", upload.filename)
            raise HTTPException(
                status_code=400,
                detail=f"处理附件失败: {upload.filename or 'file'} ({exc})",
            ) from exc

    return ChatMediaBundle(
        images=tuple(images),
        files=tuple(docs),
        audio=tuple(audios),
        videos=tuple(videos),
        attachments=tuple(attachments),
    )


def media_kwargs(bundle: ChatMediaBundle) -> dict[str, Any]:
    """Keyword args for Agent.arun (omit empty lists)."""
    kwargs: dict[str, Any] = {}
    if bundle.images:
        kwargs["images"] = list(bundle.images)
    if bundle.files:
        kwargs["files"] = list(bundle.files)
    if bundle.audio:
        kwargs["audio"] = list(bundle.audio)
    if bundle.videos:
        kwargs["videos"] = list(bundle.videos)
    return kwargs
