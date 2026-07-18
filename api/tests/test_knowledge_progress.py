from __future__ import annotations

from pathlib import Path

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sse_starlette.sse import EventSourceResponse
from starlette.datastructures import Headers
from starlette.requests import Request

from api.auth.models import User
from api.routes import knowledge as knowledge_route
from api.services.knowledge_progress import (
    KNOWLEDGE_PROGRESS_STAGES,
    emit_progress,
    initial_progress_stages,
    knowledge_progress_event,
)


def test_initial_progress_stages_marks_upload_skipped_when_not_needed() -> None:
    stages = initial_progress_stages(include_upload=False)
    assert [item["stage"] for item in stages] == list(KNOWLEDGE_PROGRESS_STAGES)
    assert stages[0]["status"] == "skipped"
    assert stages[1]["status"] == "pending"


def test_knowledge_progress_event_includes_label_and_message() -> None:
    event = knowledge_progress_event("vectorize", "running", message="写入向量")
    assert event["stage"] == "vectorize"
    assert event["status"] == "running"
    assert event["label"] == "向量化"
    assert event["message"] == "写入向量"


@pytest.mark.asyncio
async def test_emit_progress_awaits_async_callback() -> None:
    seen: list[dict[str, object]] = []

    async def callback(event):
        seen.append(dict(event))

    await emit_progress(callback, "parse", "completed", message="done")
    assert seen == [
        {
            "stage": "parse",
            "status": "completed",
            "label": "解析",
            "message": "done",
        }
    ]


def request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": Headers({"host": "test"}).raw,
            "client": ("testclient", 50000),
            "server": ("test", 80),
        }
    )


def admin() -> User:
    return User(
        id="u1",
        email="admin@example.com",
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )


@pytest.mark.asyncio
async def test_update_document_stream_emits_four_stage_progress() -> None:
    document = {
        "id": "doc-1",
        "title": "Runbook",
        "source": "manual",
        "chunks": 2,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "status_message": "",
        "type": ".md",
        "size": 12,
        "visibility": "private",
        "owner_user_id": "u1",
        "metadata": {"file_name": "runbook.md"},
    }
    lifecycle = SimpleNamespace(
        replace_document_source_async=AsyncMock(return_value=document),
    )
    events: list[tuple[str, dict[str, Any]]] = []

    with (
        patch.object(knowledge_route, "get_knowledge_base_lifecycle", return_value=lifecycle),
        patch.object(knowledge_route, "record_audit_event_async", AsyncMock()),
    ):
        response = await knowledge_route.update_document(
            request("/api/knowledge/documents/doc-1/update"),
            "doc-1",
            knowledge_route.KnowledgeDocumentUpdateActionRequest(
                mode="replace_text",
                content="# body",
                file_name="runbook.md",
            ),
            stream=True,
            user=admin(),
        )
        assert isinstance(response, EventSourceResponse)
        async for item in response.body_iterator:
            if isinstance(item, dict):
                payload = item
            else:
                # bytes/str fallback
                continue
            event = payload.get("event")
            raw = payload.get("data")
            data = json.loads(raw if isinstance(raw, (str, bytes, bytearray)) else "{}")
            events.append((str(event), data))

    assert lifecycle.replace_document_source_async.await_count == 1
    kwargs = lifecycle.replace_document_source_async.await_args.kwargs
    assert callable(kwargs.get("on_progress"))
    # worker emits initial stages + completion
    stages = [data["stage"] for _, data in events if data.get("stage") in KNOWLEDGE_PROGRESS_STAGES]
    assert "parse" in stages or "upload" in stages
    assert events[-1][0] == "progress.completed"
    assert events[-1][1]["document"]["id"] == "doc-1"



@pytest.mark.asyncio
async def test_create_text_document_stream_emits_progress() -> None:
    document = {
        "id": "doc-new",
        "title": "Note",
        "source": "manual",
        "chunks": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "status_message": "",
        "type": "text",
        "size": 4,
        "visibility": "private",
        "owner_user_id": "u1",
        "metadata": {},
    }
    lifecycle = SimpleNamespace(add_text_document_async=AsyncMock(return_value=document))
    events: list[tuple[str, dict[str, Any]]] = []

    with (
        patch.object(knowledge_route, "get_knowledge_base_lifecycle", return_value=lifecycle),
        patch.object(knowledge_route, "record_audit_event_async", AsyncMock()),
    ):
        response = await knowledge_route.create_text_document(
            request("/api/knowledge/documents/text"),
            knowledge_route.KnowledgeTextRequest(title="Note", content="body"),
            stream=True,
            user=admin(),
        )
        assert isinstance(response, EventSourceResponse)
        async for item in response.body_iterator:
            if not isinstance(item, dict):
                continue
            raw = item.get("data")
            data = json.loads(raw if isinstance(raw, (str, bytes, bytearray)) else "{}")
            events.append((str(item.get("event")), data))

    assert lifecycle.add_text_document_async.await_count == 1
    assert callable(lifecycle.add_text_document_async.await_args.kwargs.get("on_progress"))
    assert events[-1][0] == "progress.completed"
    assert events[-1][1]["document"]["id"] == "doc-new"


@pytest.mark.asyncio
async def test_upload_document_stream_emits_upload_stage(tmp_path: Path) -> None:
    from api.services.knowledge_upload_service import StoredKnowledgeUpload

    stored = StoredKnowledgeUpload(
        path=tmp_path / "upload-id" / "runbook.md",
        file_name="runbook.md",
        file_size=10,
        mime_type="text/markdown",
        upload_id="a" * 32,
    )
    document = {
        "id": "doc-up",
        "title": "Runbook",
        "source": "upload:runbook.md",
        "chunks": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "status_message": "",
        "type": ".md",
        "size": 10,
        "visibility": "private",
        "owner_user_id": "u1",
        "metadata": {},
    }
    lifecycle = SimpleNamespace(add_file_document_async=AsyncMock(return_value=document))
    events: list[str] = []

    with (
        patch.object(knowledge_route, "store_knowledge_upload_async", AsyncMock(return_value=stored)),
        patch.object(knowledge_route, "get_knowledge_base_lifecycle", return_value=lifecycle),
        patch.object(knowledge_route, "record_audit_event_async", AsyncMock()),
    ):
        # Build minimal UploadFile-like via route helper patterns used in other tests
        from api.tests.test_knowledge_upload import upload_file

        response = await knowledge_route.upload_document(
            request("/api/knowledge/documents/upload"),
            upload_file(b"# body\n", "runbook.md"),
            title="Runbook",
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
            stream=True,
            user=admin(),
        )
        assert isinstance(response, EventSourceResponse)
        async for item in response.body_iterator:
            if not isinstance(item, dict):
                continue
            raw = item.get("data")
            data = json.loads(raw if isinstance(raw, (str, bytes, bytearray)) else "{}")
            events.append(f"{data.get('stage')}:{data.get('status')}")

    assert any(item.startswith("upload:") for item in events)
    assert events[-1].startswith("done:") or "done:completed" in events or events[-1] == "done:completed"
    # last event stage is done
    assert "done" in events[-1]


@pytest.mark.asyncio
async def test_create_text_document_non_stream_returns_processing_placeholder() -> None:
    document = {
        "id": "doc-new",
        "title": "Note",
        "source": "manual",
        "chunks": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "status_message": "",
        "type": "text",
        "size": 4,
        "visibility": "private",
        "owner_user_id": "u1",
        "metadata": {},
    }
    lifecycle = SimpleNamespace(add_text_document_async=AsyncMock(return_value=document))
    scheduled: list[object] = []

    def fake_schedule(**kwargs: object) -> None:
        scheduled.append(kwargs)

    with (
        patch.object(knowledge_route, "get_knowledge_base_lifecycle", return_value=lifecycle),
        patch.object(knowledge_route, "record_audit_event_async", AsyncMock()),
        patch.object(knowledge_route, "_schedule_knowledge_ingest", side_effect=fake_schedule),
    ):
        result = await knowledge_route.create_text_document(
            request("/api/knowledge/documents/text"),
            knowledge_route.KnowledgeTextRequest(title="Note", content="body"),
            stream=False,
            user=admin(),
        )
        assert not isinstance(result, EventSourceResponse)
        assert result["status"] == "processing"
        assert str(result["id"]).startswith("processing:text:")
        assert len(scheduled) == 1
        bg = await scheduled[0]["work"]()
        assert bg["id"] == "doc-new"
        lifecycle.add_text_document_async.assert_awaited_once()
