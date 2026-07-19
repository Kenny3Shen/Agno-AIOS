"""Chat multipart attachment processing (Agno media)."""

from __future__ import annotations

import asyncio
import time
from io import BytesIO
from threading import BoundedSemaphore, Lock, get_ident

from fastapi import HTTPException
import pytest
from starlette.datastructures import Headers, UploadFile

from api.services import chat_media


def _upload(name: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


def test_process_chat_uploads_image_and_pdf():
    bundle = asyncio.run(
        chat_media.process_chat_uploads(
            [
                _upload("shot.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png"),
                _upload("note.pdf", b"%PDF-1.4 fake", "application/pdf"),
            ]
        )
    )
    assert len(bundle.images) == 1
    # Docling documents become Markdown model input.  Their original bytes are
    # reserved for the isolated analysis workspace, never an Agno ``file``
    # content part sent to a Chat Completions model.
    assert bundle.files == ()
    assert len(bundle.workspace_files) == 1
    assert len(bundle.attachments) == 2
    assert bundle.attachments[0]["kind"] == "image"
    assert bundle.attachments[1]["kind"] == "document"


def test_process_chat_uploads_rejects_empty():
    try:
        asyncio.run(chat_media.process_chat_uploads([_upload("empty.txt", b"", "text/plain")]))
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_readme_markdown_is_workspace_only_after_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real README.md upload path must not yield a model ``file`` part."""

    monkeypatch.setattr(
        chat_media,
        "convert_bytes_to_markdown",
        lambda *_args, **_kwargs: "# README converted",
    )

    bundle = asyncio.run(
        chat_media.process_chat_uploads(
            [_upload("README.md", b"# README", "text/markdown")]
        )
    )

    assert bundle.document_markdown == (("README.md", "# README converted"),)
    assert bundle.files == ()
    assert len(bundle.workspace_files) == 1


def test_process_chat_uploads_rejects_too_many(monkeypatch):
    monkeypatch.setattr(chat_media, "MAX_CHAT_FILES", 1)
    try:
        asyncio.run(
            chat_media.process_chat_uploads(
                [
                    _upload("a.txt", b"hello", "text/plain"),
                    _upload("b.txt", b"world", "text/plain"),
                ]
            )
        )
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_document_conversion_runs_in_worker_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    request_thread = get_ident()
    worker_threads: list[int] = []

    def convert(*_args, **_kwargs) -> str:
        worker_threads.append(get_ident())
        return "converted"

    monkeypatch.setattr(chat_media, "convert_bytes_to_markdown", convert)

    bundle = asyncio.run(
        chat_media.process_chat_uploads(
            [_upload("report.pdf", b"%PDF-1.4 fake", "application/pdf")]
        )
    )

    assert bundle.document_markdown == (("report.pdf", "converted"),)
    assert worker_threads
    assert all(thread != request_thread for thread in worker_threads)


def test_document_conversion_respects_global_concurrency_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    peak = 0
    lock = Lock()

    def convert(*_args, **_kwargs) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return "converted"

    monkeypatch.setattr(chat_media, "convert_bytes_to_markdown", convert)
    monkeypatch.setattr(chat_media, "_DOCUMENT_CONVERSION_SLOTS", BoundedSemaphore(1))

    async def process_three() -> None:
        bundles = await asyncio.gather(
            *(
                chat_media.process_chat_uploads(
                    [_upload(f"report-{index}.pdf", b"%PDF-1.4 fake", "application/pdf")]
                )
                for index in range(3)
            )
        )
        assert all(bundle.document_markdown for bundle in bundles)

    asyncio.run(process_three())
    assert peak == 1


def test_document_conversion_times_out_without_blocking_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def convert(*_args, **_kwargs) -> str:
        time.sleep(0.08)
        return "converted"

    monkeypatch.setattr(chat_media, "convert_bytes_to_markdown", convert)
    monkeypatch.setattr(chat_media, "CHAT_DOCUMENT_CONVERSION_TIMEOUT_SECONDS", 0.01)

    async def process_slow_document() -> HTTPException:
        task = asyncio.create_task(
            chat_media.process_chat_uploads(
                [_upload("slow.pdf", b"%PDF-1.4 fake", "application/pdf")]
            )
        )
        # Reaching this checkpoint before the converter completes proves that
        # the synchronous converter did not occupy the request event loop.
        await asyncio.sleep(0.005)
        assert not task.done()
        with pytest.raises(HTTPException) as error:
            await task
        return error.value

    error = asyncio.run(process_slow_document())
    assert error.status_code == 504
    # The timed-out worker is deliberately allowed to release its held slot
    # before other tests reuse the shared executor.
    time.sleep(0.1)


def test_document_markdown_obeys_per_request_output_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_limits: list[tuple[int | None, int | None]] = []

    def convert(*_args, **kwargs) -> str:
        requested_limits.append(
            (kwargs.get("max_output_chars"), kwargs.get("max_output_tokens"))
        )
        # Deliberately ignore the requested budgets.  The worker boundary must
        # still prevent an oversized converter result reaching the chat prompt.
        return "a" * 100

    monkeypatch.setattr(chat_media, "convert_bytes_to_markdown", convert)
    monkeypatch.setattr(chat_media, "MAX_CHAT_DOCUMENT_MARKDOWN_CHARS", 8)
    monkeypatch.setattr(chat_media, "MAX_CHAT_DOCUMENT_MARKDOWN_TOKENS", 8)
    monkeypatch.setattr(chat_media, "MAX_CHAT_TOTAL_DOCUMENT_MARKDOWN_CHARS", 10)
    monkeypatch.setattr(chat_media, "MAX_CHAT_TOTAL_DOCUMENT_MARKDOWN_TOKENS", 10)

    bundle = asyncio.run(
        chat_media.process_chat_uploads(
            [
                _upload("first.pdf", b"%PDF-1.4 fake", "application/pdf"),
                _upload("second.pdf", b"%PDF-1.4 fake", "application/pdf"),
            ]
        )
    )

    assert requested_limits == [(8, 8), (2, 8)]
    converted = [markdown for _name, markdown in bundle.document_markdown]
    assert sum(map(len, converted)) <= 10
    assert sum(map(chat_media.estimate_markdown_tokens, converted)) <= 10
