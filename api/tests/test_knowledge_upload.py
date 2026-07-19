from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request

from api.auth.models import User
from api.routes import knowledge as knowledge_route
from api.services import knowledge_service
from api.services.knowledge_upload_service import (
    MANAGED_UPLOAD_METADATA_KEY,
    MANAGED_UPLOAD_METADATA_VERSION,
    KnowledgeUploadTooLargeError,
    StoredKnowledgeUpload,
    remove_managed_upload_async,
    store_knowledge_upload_async,
)


def test_json_ingest_options_accept_reader_specific_fields() -> None:
    payload = knowledge_route.KnowledgeIngestOptionsRequest.model_validate(
        {
            "chunk_size": 1500,
            "chunk_overlap": 120,
            "markdown_split_on_headings": 2,
            "csv_skip_header": True,
            "csv_clean_rows": False,
            "code_chunk_size": 2200,
            "code_tokenizer": "gpt2",
            "code_include_nodes": True,
            "semantic_threshold": 0.61,
            "semantic_similarity_window": 4,
            "semantic_min_sentences_per_chunk": 2,
            "semantic_min_characters_per_sentence": 12,
            "reader_strategy": "markdown",
        }
    )

    assert payload.model_dump(exclude_none=True)["code_tokenizer"] == "gpt2"


@pytest.mark.asyncio
async def test_update_route_passes_rebuild_metadata_and_ingest_options_to_lifecycle() -> None:
    current_user = actor()
    enqueue = AsyncMock(return_value=SimpleNamespace(id="job-rebuild-1"))
    with (
        patch.object(knowledge_route, "enqueue_knowledge_ingest_job", enqueue),
    ):
        result = await knowledge_route.update_document(
            request("/api/knowledge/documents/doc-1/update"),
            "doc-1",
            request=knowledge_route.KnowledgeDocumentUpdateActionRequest(
                mode="rebuild",
                metadata=knowledge_route.KnowledgeDocumentMetadataUpdateRequest(
                    title="Updated runbook",
                    source="IR",
                    visibility="public",
                ),
                ingest_options=knowledge_route.KnowledgeIngestOptionsRequest(
                    chunk_size=1800,
                    markdown_split_on_headings=2,
                    reader_strategy="markdown",
                )
            ),
            user=current_user,
        )
        assert result["status"] == "processing"
        assert result["id"] == "job-rebuild-1"

    call = enqueue.await_args
    assert call is not None
    payload = call.kwargs["payload"]
    assert payload["operation"] == "rebuild"
    assert payload["owner_user_id"] == "u1"
    assert payload["data"] == {
        "doc_id": "doc-1",
        "content": "",
        "file_name": "",
        "title": "Updated runbook",
        "source": "IR",
        "visibility": "public",
        "metadata": {},
        "ingest_options": {
            "chunk_size": 1800,
            "markdown_split_on_headings": 2,
            "reader_strategy": "markdown",
        },
    }


def upload_file(
    content: bytes,
    filename: str,
    content_type: str = "text/markdown",
) -> UploadFile:
    return UploadFile(
        BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def request(path: str = "/api/knowledge/documents/upload") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )


def actor() -> User:
    return cast(
        User,
        SimpleNamespace(
            id="u1",
            email="operator@example.com",
            role="user",
            is_superuser=False,
        ),
    )


@pytest.mark.asyncio
async def test_browser_upload_persists_rebuildable_file_and_metadata(tmp_path: Path) -> None:
    stored = await store_knowledge_upload_async(
        upload_file(b"# Runbook\n", "runbook.md"),
        upload_root=tmp_path,
    )

    assert stored.path.read_bytes() == b"# Runbook\n"
    assert stored.path.parent.parent == tmp_path
    assert stored.file_name == "runbook.md"
    assert stored.file_size == 10
    assert stored.mime_type == "text/markdown"
    assert stored.metadata() == {
        "file_name": "runbook.md",
        "file_size": 10,
        "mime_type": "text/markdown",
        "input_mode": "upload",
        "upload_mode": "browser",
        MANAGED_UPLOAD_METADATA_KEY: {
            "version": MANAGED_UPLOAD_METADATA_VERSION,
            "upload_id": stored.upload_id,
            "file_name": "runbook.md",
        },
    }


@pytest.mark.asyncio
async def test_managed_upload_cleanup_removes_only_generated_file_and_directory(
    tmp_path: Path,
) -> None:
    stored = await store_knowledge_upload_async(
        upload_file(b"# Runbook\n", "runbook.md"),
        upload_root=tmp_path,
    )
    upload_dir = stored.path.parent

    removed = await remove_managed_upload_async(
        stored.metadata(),
        upload_root=tmp_path,
    )

    assert removed
    assert not stored.path.exists()
    assert not upload_dir.exists()
    assert tmp_path.exists()


@pytest.mark.asyncio
async def test_browser_upload_rejects_unsafe_or_unsupported_filename(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不能包含路径"):
        await store_knowledge_upload_async(
            upload_file(b"body", "../runbook.md"),
            upload_root=tmp_path,
        )
    with pytest.raises(ValueError, match="支持的文件后缀"):
        await store_knowledge_upload_async(
            upload_file(b"body", "runbook.exe"),
            upload_root=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_browser_upload_enforces_streaming_size_limit_and_removes_partial_file(
    tmp_path: Path,
) -> None:
    with pytest.raises(KnowledgeUploadTooLargeError):
        await store_knowledge_upload_async(
            upload_file(b"12345", "runbook.md"),
            max_bytes=4,
            upload_root=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_managed_upload_cleanup_never_uses_untrusted_file_path(tmp_path: Path) -> None:
    upload_root = tmp_path / "uploads"
    outside = tmp_path / "outside.md"
    outside.write_text("keep", encoding="utf-8")

    removed = await remove_managed_upload_async(
        {
            "file_path": str(outside),
            "input_mode": "upload",
            "upload_mode": "browser",
        },
        upload_root=upload_root,
    )

    assert not removed
    assert outside.read_text(encoding="utf-8") == "keep"


@pytest.mark.asyncio
async def test_managed_upload_cleanup_rejects_symlinked_upload_directory(
    tmp_path: Path,
) -> None:
    upload_root = tmp_path / "uploads"
    outside_dir = tmp_path / "outside"
    upload_root.mkdir()
    outside_dir.mkdir()
    outside_file = outside_dir / "runbook.md"
    outside_file.write_text("keep", encoding="utf-8")
    upload_id = "a" * 32
    upload_root.joinpath(upload_id).symlink_to(outside_dir, target_is_directory=True)

    removed = await remove_managed_upload_async(
        {
            MANAGED_UPLOAD_METADATA_KEY: {
                "version": MANAGED_UPLOAD_METADATA_VERSION,
                "upload_id": upload_id,
                "file_name": "runbook.md",
            }
        },
        upload_root=upload_root,
    )

    assert not removed
    assert outside_file.read_text(encoding="utf-8") == "keep"


@pytest.mark.asyncio
async def test_delete_document_requests_managed_upload_cleanup() -> None:
    metadata = {
        "user_id": "u1",
        "visibility": "private",
        MANAGED_UPLOAD_METADATA_KEY: {
            "version": MANAGED_UPLOAD_METADATA_VERSION,
            "upload_id": "b" * 32,
            "file_name": "runbook.md",
        },
    }
    content = SimpleNamespace(id="doc-1", metadata=metadata)
    cleanup = AsyncMock(return_value=True)
    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content,
            delete_content_async=lambda _knowledge, _content_id: None,
            delete_source_async=lambda _content_id: None,
        )
    )

    with patch.object(knowledge_service, "remove_managed_upload_async", cleanup):
        deleted = await lifecycle.delete_document_async(
            "doc-1",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert deleted
    cleanup.assert_awaited_once_with(metadata)


@pytest.mark.asyncio
async def test_upload_route_enqueues_persisted_path_with_browser_metadata(tmp_path: Path) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook.md",
        file_name="runbook.md",
        file_size=12,
        mime_type="text/markdown",
        upload_id="c" * 32,
    )
    enqueue = AsyncMock(return_value=SimpleNamespace(id="job-upload-1"))

    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(knowledge_route, "enqueue_knowledge_ingest_job", enqueue),
    ):
        result = await knowledge_route.upload_document(
            request(),
            upload_file(b"# Runbook\n", "runbook.md"),
            title="Runbook",
            source=None,
            visibility="private",
            chunk_size=1500,
            chunk_overlap=120,
            markdown_split_on_headings=2,
            csv_skip_header=None,
            csv_clean_rows=None,
            code_chunk_size=None,
            code_tokenizer=None,
            code_include_nodes=None,
            semantic_threshold=None,
            semantic_similarity_window=None,
            semantic_min_sentences_per_chunk=None,
            semantic_min_characters_per_sentence=None,
            reader_strategy="markdown",
            user=actor(),
        )

    assert result["status"] == "processing"
    assert result["id"] == "job-upload-1"
    assert result["can_manage"] is True
    call = enqueue.await_args
    assert call is not None
    payload = call.kwargs["payload"]
    assert payload["operation"] == "upload"
    assert payload["data"] == {
        "path": str(stored.path),
        "title": "Runbook",
        "source": "upload:runbook.md",
        "visibility": "private",
        "metadata": stored.metadata(),
        "ingest_options": {
            "chunk_size": 1500,
            "chunk_overlap": 120,
            "markdown_split_on_headings": 2,
            "reader_strategy": "markdown",
        },
    }


@pytest.mark.asyncio
async def test_upload_route_removes_file_when_enqueue_fails(tmp_path: Path) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook.md",
        file_name="runbook.md",
        file_size=12,
        mime_type="text/markdown",
        upload_id="d" * 32,
    )
    cleanup = AsyncMock(return_value=True)

    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(knowledge_route, "remove_managed_upload_async", cleanup),
        patch.object(
            knowledge_route,
            "enqueue_knowledge_ingest_job",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ),
    ):
        with pytest.raises(RuntimeError, match="database unavailable"):
            await knowledge_route.upload_document(
                request(),
                upload_file(b"# Runbook\n", "runbook.md"),
                title=None,
                source=None,
                visibility="private",
                chunk_size=None,
                chunk_overlap=None,
                markdown_split_on_headings=None,
                csv_skip_header=None,
                csv_clean_rows=None,
                code_chunk_size=None,
                code_tokenizer=None,
                code_include_nodes=None,
                semantic_threshold=None,
                semantic_similarity_window=None,
                semantic_min_sentences_per_chunk=None,
                semantic_min_characters_per_sentence=None,
                reader_strategy=None,
                user=actor(),
            )
    cleanup.assert_awaited_once_with(stored.metadata())


@pytest.mark.asyncio
async def test_update_upload_route_enqueues_replacement_from_persisted_path(
    tmp_path: Path,
) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook-v2.md",
        file_name="runbook-v2.md",
        file_size=16,
        mime_type="text/markdown",
        upload_id="e" * 32,
    )
    current_user = actor()
    enqueue = AsyncMock(return_value=SimpleNamespace(id="job-replace-file-1"))
    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(knowledge_route, "enqueue_knowledge_ingest_job", enqueue),
    ):
        result = await knowledge_route.update_document_upload(
            request("/api/knowledge/documents/doc-1/update/upload"),
            "doc-1",
            upload_file(b"# Runbook v2\n", "runbook-v2.md"),
            title=None,
            source=None,
            visibility=None,
            chunk_size=None,
            chunk_overlap=None,
            markdown_split_on_headings=None,
            csv_skip_header=True,
            csv_clean_rows=False,
            code_chunk_size=2200,
            code_tokenizer="gpt2",
            code_include_nodes=True,
            semantic_threshold=0.61,
            semantic_similarity_window=4,
            semantic_min_sentences_per_chunk=2,
            semantic_min_characters_per_sentence=12,
            reader_strategy=None,
            user=current_user,
        )
        assert result["status"] == "processing"
        assert result["id"] == "job-replace-file-1"
        assert result["can_manage"] is True
    call = enqueue.await_args
    assert call is not None
    payload = call.kwargs["payload"]
    assert payload["operation"] == "replace_file"
    assert payload["data"] == {
        "doc_id": "doc-1",
        "path": str(stored.path),
        "title": "",
        "source": "",
        "visibility": "",
        "metadata": stored.metadata(),
        "ingest_options": {
            "csv_skip_header": True,
            "csv_clean_rows": False,
            "code_chunk_size": 2200,
            "code_tokenizer": "gpt2",
            "code_include_nodes": True,
            "semantic_threshold": 0.61,
            "semantic_similarity_window": 4,
            "semantic_min_sentences_per_chunk": 2,
            "semantic_min_characters_per_sentence": 12,
        },
    }


@pytest.mark.asyncio
async def test_update_upload_route_removes_file_when_enqueue_fails(
    tmp_path: Path,
) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook-v2.md",
        file_name="runbook-v2.md",
        file_size=16,
        mime_type="text/markdown",
        upload_id="f" * 32,
    )
    cleanup = AsyncMock(return_value=True)
    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(knowledge_route, "remove_managed_upload_async", cleanup),
        patch.object(
            knowledge_route,
            "enqueue_knowledge_ingest_job",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ),
    ):
        with pytest.raises(RuntimeError, match="database unavailable"):
            await knowledge_route.update_document_upload(
                request("/api/knowledge/documents/doc-missing/update/upload"),
                "doc-missing",
                upload_file(b"# Runbook v2\n", "runbook-v2.md"),
                title=None,
                source=None,
                visibility=None,
                chunk_size=None,
                chunk_overlap=None,
                markdown_split_on_headings=None,
                csv_skip_header=None,
                csv_clean_rows=None,
                code_chunk_size=None,
                code_tokenizer=None,
                code_include_nodes=None,
                semantic_threshold=None,
                semantic_similarity_window=None,
                semantic_min_sentences_per_chunk=None,
                semantic_min_characters_per_sentence=None,
                reader_strategy=None,
                user=actor(),
            )
    cleanup.assert_awaited_once_with(stored.metadata())
