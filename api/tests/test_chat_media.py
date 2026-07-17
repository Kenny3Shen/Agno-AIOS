"""Chat multipart attachment processing (Agno media)."""

from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import HTTPException
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
    assert len(bundle.files) == 1
    assert len(bundle.attachments) == 2
    assert bundle.attachments[0]["kind"] == "image"
    assert bundle.attachments[1]["kind"] == "document"
    kwargs = chat_media.media_kwargs(bundle)
    assert "images" in kwargs and "files" in kwargs


def test_process_chat_uploads_rejects_empty():
    try:
        asyncio.run(chat_media.process_chat_uploads([_upload("empty.txt", b"", "text/plain")]))
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


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


def test_media_kwargs_empty():
    empty = chat_media.ChatMediaBundle()
    assert empty.empty
    assert chat_media.media_kwargs(empty) == {}
