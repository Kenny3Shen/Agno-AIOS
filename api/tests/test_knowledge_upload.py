from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request
from sse_starlette.sse import EventSourceResponse

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
    captured: dict[str, object] = {}
    current_user = actor()

    class Lifecycle:
        async def rebuild_document_async(self, doc_id: str, **kwargs: object) -> dict[str, object]:
            captured["doc_id"] = doc_id
            captured.update(kwargs)
            return {
                "id": "doc-1",
                "title": "Runbook",
                "source": "manual",
                "chunks": 3,
                "created_at": "",
                "updated_at": "",
                "status": "completed",
                "status_message": "",
                "type": ".md",
                "size": 12,
                "visibility": "private",
                "owner_user_id": "u1",
                "metadata": {},
            }

    with (
        patch.object(
            knowledge_route,
            "get_knowledge_base_lifecycle",
            return_value=Lifecycle(),
        ),
        patch.object(knowledge_route, "record_audit_event_async", new=AsyncMock()),
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

    assert not isinstance(result, EventSourceResponse)
    assert result["can_manage"] is True
    assert captured == {
        "doc_id": "doc-1",
        "owner_user_id": "u1",
        "user": current_user,
        "title": "Updated runbook",
        "source": "IR",
        "visibility": "public",
        "metadata": {},
        "ingest_options": {
            "chunk_size": 1800,
            "markdown_split_on_headings": 2,
            "reader_strategy": "markdown",
        },
        "on_progress": None,
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
async def test_upload_route_ingests_persisted_path_with_browser_metadata(tmp_path: Path) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook.md",
        file_name="runbook.md",
        file_size=12,
        mime_type="text/markdown",
        upload_id="c" * 32,
    )
    captured: dict[str, object] = {}

    class Lifecycle:
        async def add_file_document_async(self, **kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "id": "doc-1",
                "title": "Runbook",
                "source": "upload:runbook.md",
                "chunks": 1,
                "created_at": "",
                "updated_at": "",
                "status": "completed",
                "status_message": "",
                "type": ".md",
                "size": 12,
                "visibility": "private",
                "owner_user_id": "u1",
                "metadata": {},
            }

    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(
            knowledge_route,
            "get_knowledge_base_lifecycle",
            return_value=Lifecycle(),
        ),
        patch.object(
            knowledge_route,
            "record_audit_event_async",
            new=AsyncMock(),
        ),
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

    assert not isinstance(result, EventSourceResponse)
    assert result["id"] == "doc-1"
    assert result["can_manage"] is True
    assert captured == {
        "path": str(stored.path),
        "title": "Runbook",
        "source": "upload:runbook.md",
        "metadata": stored.metadata(),
        "owner_user_id": "u1",
        "visibility": "private",
        "ingest_options": {
            "chunk_size": 1500,
            "chunk_overlap": 120,
            "markdown_split_on_headings": 2,
            "reader_strategy": "markdown",
        },
        "on_progress": None,
    }


@pytest.mark.asyncio
async def test_upload_route_removes_file_when_ingest_fails(tmp_path: Path) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook.md",
        file_name="runbook.md",
        file_size=12,
        mime_type="text/markdown",
        upload_id="d" * 32,
    )
    cleanup = AsyncMock(return_value=True)

    class Lifecycle:
        async def add_file_document_async(self, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("ingest failed")

    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(
            knowledge_route,
            "get_knowledge_base_lifecycle",
            return_value=Lifecycle(),
        ),
        patch.object(knowledge_route, "remove_managed_upload_async", cleanup),
        pytest.raises(HTTPException) as exc,
    ):
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

    assert exc.value.status_code == 400
    cleanup.assert_awaited_once_with(stored.metadata())


@pytest.mark.asyncio
async def test_update_upload_route_replaces_selected_document_from_persisted_path(
    tmp_path: Path,
) -> None:
    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook-v2.md",
        file_name="runbook-v2.md",
        file_size=16,
        mime_type="text/markdown",
        upload_id="e" * 32,
    )
    captured: dict[str, object] = {}
    current_user = actor()

    class Lifecycle:
        async def replace_document_file_async(
            self,
            doc_id: str,
            **kwargs: object,
        ) -> dict[str, object]:
            captured["doc_id"] = doc_id
            captured.update(kwargs)
            return {
                "id": "doc-1",
                "title": "Runbook",
                "source": "upload:runbook.md",
                "chunks": 2,
                "created_at": "",
                "updated_at": "",
                "status": "completed",
                "status_message": "",
                "type": ".md",
                "size": 16,
                "visibility": "private",
                "owner_user_id": "u1",
                "metadata": {},
            }

    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(
            knowledge_route,
            "get_knowledge_base_lifecycle",
            return_value=Lifecycle(),
        ),
        patch.object(
            knowledge_route,
            "record_audit_event_async",
            new=AsyncMock(),
        ),
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

    assert not isinstance(result, EventSourceResponse)
    assert result["id"] == "doc-1"
    assert result["can_manage"] is True
    assert captured == {
        "doc_id": "doc-1",
        "path": str(stored.path),
        "title": None,
        "source": None,
        "visibility": None,
        "metadata": stored.metadata(),
        "owner_user_id": "u1",
        "user": current_user,
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
        "on_progress": None,
    }


@pytest.mark.asyncio
async def test_update_upload_route_removes_file_when_document_is_missing(
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

    class Lifecycle:
        async def replace_document_file_async(
            self,
            _doc_id: str,
            **_kwargs: object,
        ) -> None:
            return None

    with (
        patch.object(
            knowledge_route,
            "store_knowledge_upload_async",
            new=AsyncMock(return_value=stored),
        ),
        patch.object(
            knowledge_route,
            "get_knowledge_base_lifecycle",
            return_value=Lifecycle(),
        ),
        patch.object(knowledge_route, "remove_managed_upload_async", cleanup),
        pytest.raises(HTTPException) as exc,
    ):
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

    assert exc.value.status_code == 404
    cleanup.assert_awaited_once_with(stored.metadata())
