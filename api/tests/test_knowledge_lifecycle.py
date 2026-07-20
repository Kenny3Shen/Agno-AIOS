"""Critical knowledge lifecycle business tests (ownership, search, list, mutate)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.services import knowledge_service
from api.tests.knowledge_fakes import StrictAsyncKnowledge


def int_kwarg(values: Mapping[str, object], key: str, default: int) -> int:
    value = values.get(key, default)
    assert isinstance(value, int)
    return value


@pytest.mark.asyncio
async def test_search_documents_merges_public_and_owner_private_filters() -> None:
    calls: list[dict[str, object]] = []

    async def search(*args, **kwargs):
        calls.append(
            {
                "query": args[0],
                "filters": kwargs.get("filters"),
                "search_type": kwargs.get("search_type"),
            }
        )
        return []

    knowledge = StrictAsyncKnowledge(search_callback=search)
    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            hydrate_content_ids_async=lambda _documents: None,
        )
    )
    results = await lifecycle.search_documents_async(
        "policy", search_type="hybrid", owner_user_id="u1"
    )
    assert results == []
    assert [call["query"] for call in calls] == ["policy", "policy"]
    assert [call["filters"] for call in calls] == [
        {"visibility": "public"},
        {"user_id": "u1"},
    ]
    assert [call["search_type"] for call in calls] == ["hybrid", "hybrid"]


@pytest.mark.asyncio
async def test_add_text_document_uses_async_insert_and_reload() -> None:
    content_row = SimpleNamespace(
        id="content-1",
        name="Runbook",
        metadata={"user_id": "u1", "source": "manual", "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[content_row])
    stored_sources: dict[str, dict[str, Any]] = {}

    async def store_source_async(content_id: str, source: Mapping[str, object]) -> None:
        stored_sources[content_id] = dict(source)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            store_source_async=store_source_async,
        )
    )

    with patch.object(knowledge_service, "reader_for_profile", return_value=object()):
        result = await lifecycle.add_text_document_async(
            "Runbook",
            "  content  ",
            owner_user_id="u1",
        )

    assert result["id"] == "content-1"
    assert result["title"] == "Runbook"
    assert knowledge.calls[0][0] == "ainsert"
    assert knowledge.calls[1][0] == "aget_content"
    insert_kwargs = knowledge.calls[0][2]
    assert insert_kwargs["metadata"]["_tais_source"]["kind"] == "text"
    assert "text_content" not in insert_kwargs["metadata"]["_tais_source"]
    assert stored_sources["content-1"]["kind"] == "text"
    assert stored_sources["content-1"]["text_content"] == "content"


@pytest.mark.asyncio
async def test_list_documents_page_filters_sorts_and_reports_total() -> None:
    contents = [
        SimpleNamespace(
            id="doc-1",
            name="Zulu Runbook",
            description="manual",
            metadata={"user_id": "u1", "source": "manual", "team": "blue"},
            created_at=1,
        ),
        SimpleNamespace(
            id="doc-2",
            name="Alpha Policy",
            description="manual",
            metadata={"user_id": "u1", "source": "manual", "team": "blue"},
            created_at=2,
        ),
        SimpleNamespace(
            id="doc-3",
            name="Other",
            description="manual",
            metadata={"user_id": "u1", "source": "manual", "team": "red"},
            created_at=3,
        ),
    ]

    async def content_rows_async(**kwargs: object):
        return contents, len(contents)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            chunk_counts_by_content_id_async=lambda _owner: {},
        )
    )

    documents, total = await lifecycle.list_documents_page_async(
        owner_user_id="u1",
        query="blue",
        page=1,
        limit=1,
        sort_by="name",
        sort_order="asc",
    )

    assert total == 2
    assert [document["id"] for document in documents] == ["doc-2"]


@pytest.mark.asyncio
async def test_list_documents_page_pagination_window() -> None:
    rows = [
        SimpleNamespace(
            id=f"doc-{i}",
            name=f"Doc {i}",
            metadata={"user_id": "u1"},
            created_at=i,
        )
        for i in range(1, 6)
    ]
    calls: list[dict[str, object]] = []

    async def content_rows_async(**kwargs: object):
        calls.append(dict(kwargs))
        page = int_kwarg(kwargs, "page", 1)
        limit = int_kwarg(kwargs, "limit", 50)
        start = (page - 1) * limit
        window = rows[start : start + limit]
        return window, len(rows)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            chunk_counts_by_content_id_async=lambda _owner: {},
        )
    )

    documents, total = await lifecycle.list_documents_page_async(
        owner_user_id=None,
        page=2,
        limit=2,
        sort_by="updated_at",
        sort_order="desc",
    )

    assert total == 5
    assert [document["id"] for document in documents] == ["doc-3", "doc-4"]
    assert calls == [
        {"limit": 2, "page": 2, "sort_by": "updated_at", "sort_order": "desc"}
    ]


@pytest.mark.asyncio
async def test_delete_document_rejects_foreign_owner() -> None:
    lookups: list[str] = []

    async def content_by_id(content_id: str):
        lookups.append(content_id)
        return SimpleNamespace(id="doc-1", metadata={"user_id": "u2"})

    def fail_runtime(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delete authorization must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
        )
    )
    result = await lifecycle.delete_document_async("doc-1", owner_user_id="u1")
    assert not result
    assert lookups == ["doc-1"]


@pytest.mark.asyncio
async def test_delete_document_rejects_public_content_owned_by_another_user() -> None:
    content = SimpleNamespace(
        id="public-doc",
        metadata={"user_id": "u2", "visibility": "public"},
    )
    deleted: list[str] = []
    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content,
            delete_content_async=lambda _knowledge, content_id: deleted.append(content_id),
        )
    )
    user = SimpleNamespace(id="u1", role="user", is_superuser=False)

    result = await lifecycle.delete_document_async("public-doc", user=user)

    assert not result
    assert deleted == []


@pytest.mark.asyncio
async def test_update_document_metadata_rejects_public_foreign_non_manager() -> None:
    content_row = SimpleNamespace(
        id="content-public",
        name="Runbook",
        description="manual",
        metadata={"user_id": "u1", "visibility": "public", "source": "manual"},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-public": content_row})
    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
        )
    )

    result = await lifecycle.update_document_metadata_async(
        "content-public",
        source="kb://forbidden",
        user=SimpleNamespace(id="u2", role="user", is_superuser=False),
    )

    assert result is None
    assert not any(call[0] == "apatch_content" for call in knowledge.calls)


@pytest.mark.asyncio
async def test_rebuild_document_requires_ownership() -> None:
    content_row = SimpleNamespace(
        id="content-public",
        name="Shared",
        metadata={"user_id": "u2", "visibility": "public"},
        created_at=0,
    )

    def fail_runtime(_search_type=None):
        raise AssertionError("unauthorized rebuild must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_storage_async=lambda: None,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
        )
    )

    result = await lifecycle.rebuild_document_async(
        "content-public",
        owner_user_id="u1",
        user=SimpleNamespace(id="u1", role="user", is_superuser=False),
    )

    assert result is None


@pytest.mark.asyncio
async def test_replace_document_source_requires_ownership() -> None:
    content_row = SimpleNamespace(
        id="content-public",
        name="Shared",
        metadata={"user_id": "u2", "visibility": "public"},
        created_at=0,
    )

    def fail_runtime(_search_type=None):
        raise AssertionError("unauthorized source replacement must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
        )
    )

    result = await lifecycle.replace_document_source_async(
        "content-public",
        content="new body",
        file_name="shared.md",
        user=SimpleNamespace(id="u1", role="user", is_superuser=False),
    )

    assert result is None


@pytest.mark.asyncio
async def test_clear_knowledge_only_deletes_resources_managed_by_user() -> None:
    contents = [
        SimpleNamespace(id="own-private", metadata={"user_id": "u1"}),
        SimpleNamespace(
            id="other-public",
            metadata={"user_id": "u2", "visibility": "public"},
        ),
        SimpleNamespace(id="other-private", metadata={"user_id": "u2"}),
    ]
    deleted: list[str] = []

    async def content_rows_async(**kwargs: object):
        page = int_kwarg(kwargs, "page", 1)
        limit = int_kwarg(kwargs, "limit", 200)
        start = (page - 1) * limit
        end = start + limit
        return contents[start:end], len(contents)

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)
        contents[:] = [row for row in contents if str(row.id) != content_id]

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            delete_content_async=delete_content_async,
        )
    )
    user = SimpleNamespace(id="u1", role="user", is_superuser=False)

    result = await lifecycle.clear_knowledge_base_async(user=user)

    assert result["deleted_ids"] == ["own-private"]
    assert result["failed_ids"] == []
    assert deleted == ["own-private"]
