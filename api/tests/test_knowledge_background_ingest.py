from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from api.auth.models import User
from api.routes import knowledge as knowledge_route
from api.tests.knowledge_fakes import scheduled_work


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
async def test_list_knowledge_has_no_status_snapshot() -> None:
    document = {
        "id": "doc-1",
        "title": "Runbook",
        "source": "manual",
        "chunks": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "type": ".md",
        "size": 12,
        "visibility": "private",
        "owner_user_id": "u1",
        "metadata": {"user_id": "u1"},
    }
    lifecycle = SimpleNamespace(
        list_documents_page_async=AsyncMock(return_value=([document], 1)),
    )
    ingest_defaults = {
        "chunk_size": 1200,
        "chunk_overlap": 160,
        "code_chunk_size": 1800,
        "semantic_threshold": 0.52,
        "search_type": "hybrid",
    }

    with (
        patch.object(knowledge_route, "get_knowledge_base_lifecycle", return_value=lifecycle),
        patch.object(knowledge_route, "current_ingest_defaults", return_value=ingest_defaults),
    ):
        result = await knowledge_route.list_knowledge(
            query="",
            page=1,
            limit=50,
            sort_by="updated_at",
            sort_order="desc",
            user=admin(),
        )

    assert set(result) == {"data", "meta"}
    assert result["data"][0]["id"] == "doc-1"
    assert result["meta"]["ingest_defaults"] == ingest_defaults


@pytest.mark.asyncio
async def test_create_text_document_queues_background_ingest() -> None:
    document = {
        "id": "doc-new",
        "title": "Note",
        "source": "manual",
        "chunks": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "type": "text",
        "size": 4,
        "visibility": "private",
        "owner_user_id": "u1",
        "metadata": {},
    }
    lifecycle = SimpleNamespace(add_text_document_async=AsyncMock(return_value=document))
    scheduled: list[dict[str, object]] = []

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
            user=admin(),
        )
        assert result["status"] == "processing"
        assert "status_message" not in result
        assert str(result["id"]).startswith("processing:text:")
        assert len(scheduled) == 1
        bg = await scheduled_work(scheduled[0])()
        assert bg["id"] == "doc-new"
        lifecycle.add_text_document_async.assert_awaited_once()
