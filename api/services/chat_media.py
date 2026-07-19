"""Chat file attachments via Agno media types + Docling Markdown conversion.

Binary documents (PDF/DOCX/PPTX/…) are converted with Agno ``DoclingReader``
into Markdown and injected into the chat message so models that do not accept
raw Office/PDF bytes (e.g. xAI Grok) still see the full text. Images/audio/video
continue as Agno media objects.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import cast

from anyio import to_thread
from fastapi import HTTPException, UploadFile as AgnoUploadFile
from loguru import logger
from starlette.datastructures import UploadFile

from agno.media import Audio, File, Image, Video
from agno.os.utils import (
    classify_upload_file,
    process_audio,
    process_document,
    process_image,
    process_video,
)

from api.services.docling_service import (
    convert_bytes_to_markdown,
    estimate_markdown_tokens,
    truncate_markdown_output,
)

# Keep chat uploads bounded (not Knowledge-scale).
MAX_CHAT_FILES = 8
MAX_CHAT_FILE_BYTES = 20 * 1024 * 1024
MAX_CHAT_TOTAL_BYTES = 40 * 1024 * 1024

# Docling can be CPU/GPU intensive.  Keep conversions off the ASGI event loop
# and cap live jobs globally for this process.  A timed-out task keeps its slot
# until the worker actually exits, preventing stranded threads from turning
# into unbounded parallel conversions.
MAX_CHAT_DOCUMENT_CONCURRENCY = 2
CHAT_DOCUMENT_CONVERSION_TIMEOUT_SECONDS = 45.0
CHAT_DOCUMENT_QUEUE_TIMEOUT_SECONDS = 5.0

# Bound prompt growth independently from uploaded byte limits.  The token
# count is intentionally an estimate because chat supports provider-specific
# tokenizers; see ``estimate_markdown_tokens`` for its estimation policy.
MAX_CHAT_DOCUMENT_MARKDOWN_CHARS = 48_000
MAX_CHAT_DOCUMENT_MARKDOWN_TOKENS = 12_000
MAX_CHAT_TOTAL_DOCUMENT_MARKDOWN_CHARS = 96_000
MAX_CHAT_TOTAL_DOCUMENT_MARKDOWN_TOKENS = 24_000

_DOCUMENT_CONVERSION_EXECUTOR = ThreadPoolExecutor(
    max_workers=MAX_CHAT_DOCUMENT_CONCURRENCY,
    thread_name_prefix="chat-docling",
)
_DOCUMENT_CONVERSION_SLOTS = BoundedSemaphore(MAX_CHAT_DOCUMENT_CONCURRENCY)


@dataclass(frozen=True)
class ChatMediaBundle:
    """Model media, workspace-only media, and metadata for a chat upload."""

    images: tuple[Image, ...] = ()
    files: tuple[File, ...] = ()
    # Documents converted to Markdown are retained only for the isolated
    # data-analysis / Team workspace.  Passing those same File objects to a
    # Chat Completions provider produces an unsupported ``file`` content part
    # for providers such as DeepSeek.
    workspace_files: tuple[File, ...] = ()
    audio: tuple[Audio, ...] = ()
    videos: tuple[Video, ...] = ()
    # UI-facing: name / mime / kind (image|document|audio|video)
    attachments: tuple[dict[str, str], ...] = ()
    # Docling-converted Markdown keyed by original filename (order preserved).
    document_markdown: tuple[tuple[str, str], ...] = ()


def _attachment_meta(
    *,
    kind: str,
    filename: str | None,
    mime: str | None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    name = (filename or "file").strip() or "file"
    payload = {
        "name": name,
        "mime": (mime or "").strip(),
        "kind": kind,
    }
    if extra:
        payload.update(extra)
    return payload


def _read_upload_bytes_sync(upload: UploadFile) -> bytes:
    file_obj = upload.file
    file_obj.seek(0)
    raw = file_obj.read()
    file_obj.seek(0)
    return raw or b""


async def _read_upload_bytes(upload: UploadFile) -> bytes:
    """Read multipart data without blocking the ASGI event loop."""
    return await to_thread.run_sync(_read_upload_bytes_sync, upload)


def _convert_and_process_document(
    raw: bytes,
    upload: UploadFile,
    *,
    filename: str,
    max_output_chars: int,
    max_output_tokens: int,
) -> tuple[str, File | None]:
    """Run every synchronous document operation in the bounded worker pool."""
    markdown = convert_bytes_to_markdown(
        raw,
        filename=filename,
        max_output_chars=max_output_chars,
        max_output_tokens=max_output_tokens,
    )
    # Keep the output cap at the worker boundary even if a future converter is
    # swapped in and does not honor its optional limits.
    markdown = truncate_markdown_output(
        markdown,
        max_output_chars=max_output_chars,
        max_output_tokens=max_output_tokens,
    )
    return markdown, process_document(cast(AgnoUploadFile, upload))


async def _run_document_conversion(
    raw: bytes,
    upload: UploadFile,
    *,
    filename: str,
    max_output_chars: int,
    max_output_tokens: int,
) -> tuple[str, File | None]:
    """Schedule one document conversion without blocking or overloading ASGI."""
    slots = _DOCUMENT_CONVERSION_SLOTS
    deadline = asyncio.get_running_loop().time() + CHAT_DOCUMENT_QUEUE_TIMEOUT_SECONDS
    while not slots.acquire(blocking=False):
        if asyncio.get_running_loop().time() >= deadline:
            raise HTTPException(status_code=503, detail="文档转换繁忙，请稍后重试")
        await asyncio.sleep(0.01)

    try:
        future = _DOCUMENT_CONVERSION_EXECUTOR.submit(
            _convert_and_process_document,
            raw,
            upload,
            filename=filename,
            max_output_chars=max_output_chars,
            max_output_tokens=max_output_tokens,
        )
    except Exception:
        slots.release()
        raise
    future.add_done_callback(lambda _completed: slots.release())

    try:
        return await asyncio.wait_for(
            asyncio.wrap_future(future),
            timeout=CHAT_DOCUMENT_CONVERSION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        logger.warning("chat Docling conversion timed out for {}", filename)
        raise HTTPException(
            status_code=504,
            detail=f"文档转换超时: {filename}",
        ) from exc


async def process_chat_uploads(files: list[UploadFile] | None) -> ChatMediaBundle:
    """Classify and convert multipart uploads into Agno media + Docling Markdown."""
    if not files:
        return ChatMediaBundle()

    uploads = [upload for upload in files if upload.filename]
    if not uploads:
        # Some clients send empty file parts; ignore them.
        return ChatMediaBundle()
    if len(uploads) > MAX_CHAT_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {MAX_CHAT_FILES} 个附件",
        )

    images: list[Image] = []
    workspace_docs: list[File] = []
    audios: list[Audio] = []
    videos: list[Video] = []
    attachments: list[dict[str, str]] = []
    document_markdown: list[tuple[str, str]] = []
    total = 0
    document_text_chars = 0
    document_text_tokens = 0

    for upload in uploads:
        agno_upload = cast(AgnoUploadFile, upload)
        raw = await _read_upload_bytes(upload)
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

        category = classify_upload_file(agno_upload)
        if category is None:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {upload.filename or upload.content_type or 'unknown'}",
            )
        try:
            if category == "image":
                media = process_image(agno_upload)
                images.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="image",
                        filename=upload.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            elif category == "audio":
                media = process_audio(agno_upload)
                audios.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="audio",
                        filename=upload.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            elif category == "video":
                media = process_video(agno_upload)
                videos.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="video",
                        filename=upload.filename,
                        mime=upload.content_type or media.mime_type,
                    )
                )
            elif category == "document":
                # Convert documents to Markdown for model input.  Keep the
                # original File only for a run-scoped analysis workspace; never
                # also send it to the model as a ``file`` content variant.
                filename = upload.filename or "document"
                remaining_chars = max(
                    0,
                    MAX_CHAT_TOTAL_DOCUMENT_MARKDOWN_CHARS - document_text_chars,
                )
                remaining_tokens = max(
                    0,
                    MAX_CHAT_TOTAL_DOCUMENT_MARKDOWN_TOKENS - document_text_tokens,
                )
                try:
                    markdown, media = await _run_document_conversion(
                        raw,
                        upload,
                        filename=filename,
                        max_output_chars=min(
                            MAX_CHAT_DOCUMENT_MARKDOWN_CHARS,
                            remaining_chars,
                        ),
                        max_output_tokens=min(
                            MAX_CHAT_DOCUMENT_MARKDOWN_TOKENS,
                            remaining_tokens,
                        ),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                if markdown:
                    document_markdown.append((filename, markdown))
                    document_text_chars += len(markdown)
                    document_text_tokens += estimate_markdown_tokens(markdown)
                # The model sees only the Markdown injected into the message.
                # Retain raw bytes exclusively for sandbox staging.
                if media is not None:
                    workspace_docs.append(media)
                attachments.append(
                    _attachment_meta(
                        kind="document",
                        filename=filename,
                        mime=upload.content_type or getattr(media, "mime_type", None),
                        extra={"converted": "markdown", "engine": "docling"},
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
        workspace_files=tuple(workspace_docs),
        audio=tuple(audios),
        videos=tuple(videos),
        attachments=tuple(attachments),
        document_markdown=tuple(document_markdown),
    )
