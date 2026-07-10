from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agno.knowledge.content import FileData
from fastapi import HTTPException
from fastapi.routing import APIRoute

from api.auth.claims import has_scope
from api.routes import knowledge as knowledge_route
from api.services import knowledge_service
from api.services.knowledge_source_service import SOURCE_METADATA_KEY, source_digest
from api.tests.knowledge_fakes import StrictAsyncKnowledge


def route_dependency(endpoint_name: str):
    for route in knowledge_route.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_rag_settings_route_requires_config_write_scope() -> None:
    ordinary_user = SimpleNamespace(id="u1", role="user", is_superuser=False)
    admin = SimpleNamespace(id="admin", role="admin", is_superuser=False)
    dependency = route_dependency("update_rag_settings")

    assert has_scope(ordinary_user, "knowledge:write")
    assert not has_scope(ordinary_user, "config:write")
    with pytest.raises(HTTPException) as exc:
        dependency(user=ordinary_user)
    assert exc.value.status_code == 403
    assert dependency(user=admin) is admin


@pytest.mark.asyncio
async def test_search_documents_merges_public_and_owner_private_filters() -> None:
    calls: list[dict[str, object]] = []

    async def noop() -> None:
        return None

    async def hydrate_noop(_documents) -> None:
        return None

    async def get_knowledge_async(_search_type=None):
        return knowledge

    async def search(*args, **kwargs):
        calls.append(
            {
                "filters": kwargs.get("filters"),
                "max_results": kwargs.get("max_results"),
                "search_type": kwargs.get("search_type"),
            }
        )
        return []

    knowledge = StrictAsyncKnowledge(search_callback=search)

    with (
        patch.object(knowledge_service, "_ensure_knowledge_storage_async", noop),
        patch.object(knowledge_service, "_get_async_knowledge_base_async", get_knowledge_async),
        patch.object(knowledge_service, "_hydrate_content_ids_async", hydrate_noop),
    ):
        results = await knowledge_service.search_documents_async(
            "policy", owner_user_id="u1"
        )
    assert results == []
    assert [call["filters"] for call in calls] == [
        {"visibility": "public"},
        {"user_id": "u1"},
    ]


@pytest.mark.asyncio
async def test_lifecycle_search_uses_public_and_private_owner_filters() -> None:
    calls: list[dict[str, object]] = []

    async def search(*args, **kwargs):
        calls.append(
            {
                "query": args[0],
                "filters": kwargs.get("filters"),
                "max_results": kwargs.get("max_results"),
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
    stored_sources: dict[str, dict[str, object]] = {}

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
    assert stored_sources["content-1"]["metadata"] == insert_kwargs["metadata"]


@pytest.mark.asyncio
async def test_add_text_document_records_per_request_ingest_options() -> None:
    content_row = SimpleNamespace(
        id="content-options",
        name="Runbook",
        metadata={"user_id": "u1", "source": "manual", "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[content_row])

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            store_source_async=lambda _content_id, _source: None,
        )
    )

    result = await lifecycle.add_text_document_async(
        "Runbook",
        "body",
        owner_user_id="u1",
        ingest_options={
            "chunk_size": 1500,
            "chunk_overlap": 120,
            "code_chunk_size": 2200,
            "semantic_threshold": 0.61,
            "reader_strategy": "markdown",
        },
    )

    assert result["id"] == "content-options"
    insert_kwargs = knowledge.calls[0][2]
    assert insert_kwargs["metadata"]["chunk_size"] == "1500"
    assert insert_kwargs["metadata"]["chunk_overlap"] == "120"
    assert insert_kwargs["metadata"]["code_chunk_size"] == "2200"
    assert insert_kwargs["metadata"]["semantic_threshold"] == "0.61"
    assert insert_kwargs["metadata"]["chunk_strategy"] == "markdown"
    assert insert_kwargs["metadata"]["reader"] == "MarkdownReader"


@pytest.mark.asyncio
async def test_add_text_document_resolves_inserted_content_by_source_digest() -> None:
    content_row = SimpleNamespace(
        id="content-json",
        name="json chunk row",
        metadata={
            "user_id": "u1",
            "source": "upload:alerts.json",
            "chunks": 1,
            SOURCE_METADATA_KEY: {
                "kind": "text",
                "digest": source_digest('{"alerts": []}'),
            },
        },
        created_at=0,
    )
    latest_unrelated = SimpleNamespace(
        id="other-content",
        name="other",
        metadata={"user_id": "u1", "source": "manual", "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[latest_unrelated, content_row])
    stored_sources: dict[str, dict[str, object]] = {}

    async def store_source_async(content_id: str, source: Mapping[str, object]) -> None:
        stored_sources[content_id] = dict(source)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            store_source_async=store_source_async,
        )
    )

    result = await lifecycle.add_text_document_async(
        "alerts",
        '{"alerts": []}',
        source="upload:alerts.json",
        metadata={"file_name": "alerts.json"},
        owner_user_id="u1",
        ingest_options={"reader_strategy": "json"},
    )

    assert result["id"] == "content-json"
    assert stored_sources["content-json"]["text_content"] == '{"alerts": []}'


@pytest.mark.asyncio
async def test_add_file_document_uses_async_insert_and_reload(tmp_path) -> None:
    file_path = tmp_path / "runbook.md"
    file_path.write_text("# runbook\n", encoding="utf-8")
    content_row = SimpleNamespace(
        id="content-2",
        name="Runbook",
        metadata={"user_id": "u1", "source": str(file_path), "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[content_row])
    stored_sources: dict[str, dict[str, object]] = {}

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
        result = await lifecycle.add_file_document_async(
            str(file_path),
            title="Runbook",
            source="kb://runbooks/primary",
            owner_user_id="u1",
        )

    assert result["id"] == "content-2"
    assert result["title"] == "Runbook"
    assert knowledge.calls[0][0] == "ainsert"
    assert knowledge.calls[1][0] == "aget_content"
    insert_kwargs = knowledge.calls[0][2]
    assert insert_kwargs["description"] == "kb://runbooks/primary"
    assert insert_kwargs["metadata"]["source"] == "kb://runbooks/primary"
    assert insert_kwargs["metadata"]["_tais_source"]["kind"] == "path"
    assert "text_content" not in insert_kwargs["metadata"]["_tais_source"]
    assert stored_sources["content-2"]["kind"] == "path"
    assert stored_sources["content-2"]["description"] == "kb://runbooks/primary"
    assert stored_sources["content-2"]["path"] == str(file_path)
    assert stored_sources["content-2"]["metadata"] == insert_kwargs["metadata"]


@pytest.mark.asyncio
async def test_update_document_visibility_uses_agno_patch_content() -> None:
    content_row = SimpleNamespace(
        id="content-visibility",
        name="Runbook",
        metadata={"user_id": "u1", "visibility": "private", "source": "manual"},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-visibility": content_row})

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
        )
    )

    result = await lifecycle.update_document_visibility_async(
        "content-visibility",
        "public",
        SimpleNamespace(id="u1", role="user", is_superuser=False),
    )

    assert result is not None
    assert result["visibility"] == "public"
    assert content_row.metadata["visibility"] == "public"
    assert knowledge.calls[-1][0] == "apatch_content"


@pytest.mark.asyncio
async def test_update_document_metadata_uses_agno_patch_content_and_updates_source_snapshot() -> None:
    content_row = SimpleNamespace(
        id="content-metadata",
        name="Runbook",
        description="manual",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "manual",
            "file_name": "runbook.md",
        },
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-metadata": content_row})
    stored_sources: dict[str, dict[str, object]] = {
        "content-metadata": {
            "kind": "text",
            "name": "Runbook",
            "description": "manual",
            "text_content": "# runbook",
            "metadata": dict(content_row.metadata),
            "filename": "runbook.md",
        }
    }

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def get_source_async(content_id: str) -> dict[str, object] | None:
        return stored_sources.get(content_id)

    async def store_source_async(content_id: str, source: Mapping[str, object]) -> None:
        stored_sources[content_id] = dict(source)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            get_source_async=get_source_async,
            store_source_async=store_source_async,
        )
    )

    result = await lifecycle.update_document_metadata_async(
        "content-metadata",
        title="Runbook v2",
        source="kb://runbooks/v2",
        metadata={"reference": "tier1"},
        user=SimpleNamespace(id="u1", role="user", is_superuser=False),
    )

    assert result is not None
    assert result["title"] == "Runbook v2"
    assert result["source"] == "kb://runbooks/v2"
    assert result["metadata"]["reference"] == "tier1"
    assert content_row.name == "Runbook v2"
    assert content_row.description == "kb://runbooks/v2"
    assert content_row.metadata["source"] == "kb://runbooks/v2"
    assert content_row.metadata["reference"] == "tier1"
    assert stored_sources["content-metadata"]["name"] == "Runbook v2"
    assert stored_sources["content-metadata"]["description"] == "kb://runbooks/v2"
    assert stored_sources["content-metadata"]["metadata"]["reference"] == "tier1"
    assert knowledge.calls[-1][0] == "apatch_content"


@pytest.mark.asyncio
async def test_update_document_metadata_does_not_patch_content_when_source_snapshot_write_fails() -> None:
    content_row = SimpleNamespace(
        id="content-metadata",
        name="Runbook",
        description="manual",
        metadata={"user_id": "u1", "visibility": "private", "source": "manual"},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-metadata": content_row})

    async def store_source_async(_content_id: str, _source: Mapping[str, object]) -> None:
        raise RuntimeError("snapshot unavailable")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
            get_source_async=lambda _content_id: {
                "kind": "text",
                "name": "Runbook",
                "description": "manual",
                "metadata": dict(content_row.metadata),
            },
            store_source_async=store_source_async,
        )
    )

    with pytest.raises(RuntimeError, match="snapshot unavailable"):
        await lifecycle.update_document_metadata_async(
            "content-metadata",
            source="kb://runbooks/v2",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert not any(call[0] == "apatch_content" for call in knowledge.calls)
    assert content_row.description == "manual"
    assert content_row.metadata["source"] == "manual"


@pytest.mark.asyncio
async def test_update_document_metadata_restores_source_snapshot_when_agno_patch_fails() -> None:
    content_row = SimpleNamespace(
        id="content-metadata",
        name="Runbook",
        description="manual",
        metadata={"user_id": "u1", "visibility": "private", "source": "manual"},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-metadata": content_row})
    original_snapshot = {
        "kind": "text",
        "name": "Runbook",
        "description": "manual",
        "metadata": dict(content_row.metadata),
    }
    stored_snapshots: list[dict[str, object]] = []

    async def store_source_async(_content_id: str, source: Mapping[str, object]) -> None:
        stored_snapshots.append(dict(source))

    async def fail_patch(_content: object) -> None:
        raise RuntimeError("agno patch failed")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
            get_source_async=lambda _content_id: original_snapshot,
            store_source_async=store_source_async,
        )
    )

    with (
        patch.object(knowledge, "apatch_content", fail_patch),
        pytest.raises(RuntimeError, match="agno patch failed"),
    ):
        await lifecycle.update_document_metadata_async(
            "content-metadata",
            source="kb://runbooks/v2",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert stored_snapshots[0]["description"] == "kb://runbooks/v2"
    assert stored_snapshots[-1] == original_snapshot


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
async def test_update_document_metadata_rejects_empty_patch() -> None:
    content_row = SimpleNamespace(
        id="content-empty-patch",
        name="Runbook",
        metadata={"user_id": "u1", "visibility": "private", "source": "manual"},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-empty-patch": content_row})

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content_row,
        )
    )

    with pytest.raises(ValueError, match="至少提供一个可更新字段"):
        await lifecycle.update_document_metadata_async(
            "content-empty-patch",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )


@pytest.mark.asyncio
async def test_rebuild_document_reloads_content_with_public_ainsert() -> None:
    source_metadata = {
        "user_id": "u1",
        "visibility": "private",
        "source": "manual",
        "file_name": "runbook.txt",
        "_tais_source": {"kind": "text", "digest": "digest-1", "version": 1},
    }
    content_row = SimpleNamespace(
        id="content-rebuild",
        name="Runbook",
        description="manual",
        metadata=source_metadata,
        size=12,
        file_type=".txt",
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(
        content_by_id={"content-rebuild": content_row},
    )
    deleted: list[str] = []

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)
        knowledge._content_by_id.pop(content_id, None)

    async def get_source_async(content_id: str) -> dict[str, object] | None:
        assert content_id == "content-rebuild"
        return {
            "kind": "text",
            "name": "Runbook",
            "description": "manual",
            "text_content": "runbook body",
            "metadata": source_metadata,
            "filename": "runbook.txt",
        }

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
            get_source_async=get_source_async,
        )
    )

    with patch.object(knowledge_service, "reader_for_filename", return_value=object()):
        result = await lifecycle.rebuild_document_async(
            "content-rebuild",
            owner_user_id="u1",
        )

    assert result is not None
    assert result["id"] == "content-rebuild"
    assert deleted == []
    assert [call for call in knowledge.calls if call[0] == "_aload_content"] == []
    insert_calls = [call for call in knowledge.calls if call[0] == "ainsert"]
    assert len(insert_calls) == 1
    insert_kwargs = insert_calls[0][2]
    assert insert_kwargs["name"] == "Runbook"
    assert insert_kwargs["description"] == "manual"
    assert insert_kwargs["text_content"] == "runbook body"
    assert insert_kwargs["metadata"] == source_metadata
    assert insert_kwargs["upsert"] is True
    assert insert_kwargs["skip_if_exists"] is False


@pytest.mark.asyncio
async def test_rebuild_document_requires_stored_source_snapshot() -> None:
    content_row = SimpleNamespace(
        id="content-rebuild",
        name="Runbook",
        description="manual",
        path=None,
        file_data=FileData(content="runbook body", type="Text", filename="runbook.txt"),
        metadata={"user_id": "u1", "visibility": "private", "source": "manual"},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(content_by_id={"content-rebuild": content_row})

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def get_source_async(content_id: str) -> dict[str, object] | None:
        assert content_id == "content-rebuild"
        return None

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            get_source_async=get_source_async,
        )
    )

    with pytest.raises(ValueError, match="source 快照"):
        await lifecycle.rebuild_document_async(
            "content-rebuild",
            owner_user_id="u1",
        )

    assert [call for call in knowledge.calls if call[0] == "ainsert"] == []


@pytest.mark.asyncio
async def test_rebuild_document_preserves_existing_content_when_reload_fails() -> None:
    content_row = SimpleNamespace(
        id="content-rebuild",
        name="Runbook",
        description="manual",
        path=None,
        url=None,
        file_data=FileData(content="runbook body", type="Text", filename="runbook.txt"),
        metadata={"user_id": "u1", "visibility": "private", "source": "manual"},
        topics=None,
        remote_content=None,
        reader=None,
        size=12,
        file_type=".txt",
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(
        content_by_id={"content-rebuild": content_row},
    )
    deleted: list[str] = []

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)
        knowledge._content_by_id.pop(content_id, None)

    async def get_source_async(content_id: str) -> dict[str, object] | None:
        assert content_id == "content-rebuild"
        return {
            "kind": "text",
            "name": "Runbook",
            "description": "manual",
            "text_content": "runbook body",
            "metadata": content_row.metadata,
            "filename": "runbook.txt",
        }

    async def fail_reload(*_args, **_kwargs) -> None:
        raise RuntimeError("reload failed")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
            get_source_async=get_source_async,
        )
    )

    with (
        patch.object(knowledge, "ainsert", fail_reload),
        patch.object(knowledge_service, "reader_for_filename", return_value=object()),
        pytest.raises(RuntimeError, match="reload failed"),
    ):
        await lifecycle.rebuild_document_async(
            "content-rebuild",
            owner_user_id="u1",
        )

    assert deleted == []
    assert knowledge._content_by_id["content-rebuild"] is content_row


@pytest.mark.asyncio
async def test_rebuild_document_rejects_public_foreign_non_manager() -> None:
    content_row = SimpleNamespace(
        id="content-public",
        name="Shared",
        metadata={"user_id": "u2", "visibility": "public"},
        file_data=FileData(content="body", type="Text", filename="shared.txt"),
        created_at=0,
    )

    def fail_runtime(_search_type=None):
        raise AssertionError("unauthorized rebuild must not load Knowledge runtime")

    def fail_storage():
        raise AssertionError("unauthorized rebuild must not initialize vector storage")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_storage_async=fail_storage,
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
async def test_replace_document_source_uploads_new_version_and_deletes_old_content() -> None:
    old_metadata = {
        "user_id": "u1",
        "visibility": "private",
        "source": "upload:runbook.md",
        "title": "Runbook",
        "file_name": "runbook.md",
        "file_type": ".md",
        "_tais_source": {"kind": "text", "digest": "old", "version": 1},
    }
    new_metadata = {
        **old_metadata,
        "source": "upload:runbook-v2.md",
        "file_name": "runbook-v2.md",
        "file_size": "27",
    }
    old_row = SimpleNamespace(
        id="content-old",
        name="Runbook",
        description="upload:runbook.md",
        metadata=old_metadata,
        created_at=0,
    )
    new_row = SimpleNamespace(
        id="content-new",
        name="Runbook",
        description="upload:runbook-v2.md",
        metadata=new_metadata,
        created_at=1,
    )
    knowledge = StrictAsyncKnowledge(
        contents=[new_row],
        content_by_id={"content-old": old_row, "content-new": new_row},
    )
    deleted: list[str] = []
    deleted_sources: list[str] = []
    stored_sources: dict[str, dict[str, object]] = {}

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)
        knowledge._content_by_id.pop(content_id, None)

    async def delete_source_async(content_id: str) -> None:
        deleted_sources.append(content_id)

    async def store_source_async(content_id: str, source: Mapping[str, object]) -> None:
        stored_sources[content_id] = dict(source)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
            delete_source_async=delete_source_async,
            store_source_async=store_source_async,
        )
    )

    with patch.object(knowledge_service, "reader_for_profile", return_value=object()):
        result = await lifecycle.replace_document_source_async(
            "content-old",
            content="  # v2\nnew body  ",
            file_name="runbook-v2.md",
            source="upload:runbook-v2.md",
            visibility="public",
            metadata={"file_size": "27"},
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert result is not None
    assert result["id"] == "content-new"
    assert deleted == ["content-old"]
    assert deleted_sources == ["content-old"]
    insert_calls = [call for call in knowledge.calls if call[0] == "ainsert"]
    assert len(insert_calls) == 1
    insert_kwargs = insert_calls[0][2]
    assert insert_kwargs["name"] == "Runbook"
    assert insert_kwargs["description"] == "upload:runbook-v2.md"
    assert insert_kwargs["text_content"] == "# v2\nnew body"
    assert insert_kwargs["metadata"]["visibility"] == "public"
    assert insert_kwargs["metadata"]["user_id"] == "u1"
    assert insert_kwargs["metadata"]["file_name"] == "runbook-v2.md"
    assert insert_kwargs["metadata"]["_tais_source"]["kind"] == "text"
    assert insert_kwargs["metadata"]["_tais_source"]["digest"] != "old"
    assert stored_sources["content-new"]["text_content"] == "# v2\nnew body"
    assert stored_sources["content-new"]["metadata"] == insert_kwargs["metadata"]


@pytest.mark.asyncio
async def test_replace_document_source_rejects_public_foreign_non_manager() -> None:
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
async def test_replace_document_source_reports_old_cleanup_failure() -> None:
    old_row = SimpleNamespace(
        id="content-old",
        name="Runbook",
        description="upload:runbook.md",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "upload:runbook.md",
            "title": "Runbook",
            "file_name": "runbook.md",
            "file_type": ".md",
            "_tais_source": {"kind": "text", "digest": "old", "version": 1},
        },
        created_at=0,
    )
    new_row = SimpleNamespace(
        id="content-new",
        name="Runbook",
        description="upload:runbook-v2.csv",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "upload:runbook-v2.csv",
            "title": "Runbook",
            "file_name": "runbook-v2.csv",
            "file_type": ".csv",
            "_tais_source": {
                "kind": "text",
                "digest": knowledge_service.source_digest(
                    "col\nvalue", "runbook-v2.csv"
                ),
                "version": 1,
            },
        },
        created_at=1,
    )
    knowledge = StrictAsyncKnowledge(
        contents=[new_row],
        content_by_id={"content-old": old_row, "content-new": new_row},
    )

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def delete_content_async(_knowledge, content_id: str) -> None:
        assert content_id == "content-old"
        raise RuntimeError("old cleanup failed")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
            store_source_async=lambda _content_id, _source: None,
        )
    )

    with (
        patch.object(knowledge_service, "reader_for_profile", return_value=object()),
        pytest.raises(RuntimeError, match="old cleanup failed"),
    ):
        await lifecycle.replace_document_source_async(
            "content-old",
            content="col\nvalue\n",
            file_name="runbook-v2.csv",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )


@pytest.mark.asyncio
async def test_replace_document_source_cross_type_uses_new_reader_profile() -> None:
    old_row = SimpleNamespace(
        id="content-old-json",
        name="Asset Policy",
        description="upload:policy.json",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "upload:policy.json",
            "title": "Asset Policy",
            "file_name": "policy.json",
            "file_type": ".json",
        },
        created_at=0,
    )
    new_row = SimpleNamespace(
        id="content-new-js",
        name="Asset Policy",
        description="upload:policy.js",
        metadata={"user_id": "u1", "source": "upload:policy.js"},
        created_at=1,
    )
    knowledge = StrictAsyncKnowledge(
        contents=[new_row],
        content_by_id={"content-old-json": old_row, "content-new-js": new_row},
    )

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=lambda _knowledge, _content_id: None,
            delete_source_async=lambda _content_id: None,
            store_source_async=lambda _content_id, _source: None,
        )
    )

    with patch.object(knowledge_service, "reader_for_profile", return_value=object()):
        result = await lifecycle.replace_document_source_async(
            "content-old-json",
            content="console.log('policy')",
            file_name="policy.js",
            source="upload:policy.js",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert result is not None
    insert_kwargs = knowledge.calls[0][2]
    assert insert_kwargs["metadata"]["file_name"] == "policy.js"
    assert insert_kwargs["metadata"]["file_type"] == ".js"
    assert insert_kwargs["metadata"]["chunk_strategy"] == "code"
    assert insert_kwargs["metadata"]["reader"] == "TextReader"


@pytest.mark.asyncio
async def test_list_documents_uses_contents_db_without_runtime() -> None:
    content_row = SimpleNamespace(
        id="content-3",
        name="Runbook",
        metadata={"user_id": "u1", "source": "/kb/runbook.md", "chunks": 1},
        created_at=0,
    )
    content_calls: list[dict[str, object]] = []

    async def content_rows_async(**kwargs: object):
        content_calls.append(kwargs)
        return [content_row], 1

    def fail_runtime(_search_type=None):
        raise AssertionError("status/list must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            chunk_counts_by_content_id_async=lambda _owner_user_id=None: {
                "content-3": 4
            },
        )
    )

    documents = await lifecycle.list_documents_async(owner_user_id="u1")

    assert documents == [
        {
            "id": "content-3",
            "title": "Runbook",
            "source": "/kb/runbook.md",
            "chunks": 4,
            "created_at": "1970-01-01T00:00:00+00:00",
            "status": "",
            "status_message": "",
            "type": "",
            "size": None,
            "visibility": "private",
            "owner_user_id": "u1",
            "metadata": {
                "user_id": "u1",
                "source": "/kb/runbook.md",
                "chunks": "1",
            },
        }
    ]
    assert content_calls == [
        {"limit": 500, "page": 1, "sort_by": "updated_at", "sort_order": "desc"}
    ]


@pytest.mark.asyncio
async def test_list_documents_treats_completed_markdown_as_ready_when_count_missing() -> None:
    content_row = SimpleNamespace(
        id="content-ready",
        name="Runbook",
        status="completed",
        status_message="",
        type=".md",
        size=256,
        metadata={"user_id": "u1", "source": "/kb/runbook.md", "file_type": ".md"},
        created_at=0,
    )

    def fail_runtime(_search_type=None):
        raise AssertionError("list must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=lambda **_kwargs: ([content_row], 1),
            chunk_counts_by_content_id_async=lambda _owner_user_id=None: {},
        )
    )

    documents = await lifecycle.list_documents_async(owner_user_id="u1")

    assert documents[0]["chunks"] == 1
    assert documents[0]["status"] == "completed"
    assert documents[0]["type"] == ".md"
    assert documents[0]["size"] == 256


@pytest.mark.asyncio
async def test_knowledge_status_uses_prefetched_documents_without_runtime() -> None:
    def fail_runtime(_search_type=None):
        raise AssertionError("status must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            chunk_count_async=lambda _owner_user_id=None: 7,
        )
    )

    status = await lifecycle.knowledge_status_async(
        owner_user_id="u1",
        documents=[{"id": "content-1"}],
    )

    assert status["documents"] == 1
    assert status["chunks"] == 7
    assert status["rag_settings"]["top_k"] == knowledge_service.knowledge_settings().top_k
    assert "runtime_loaded" in status


@pytest.mark.asyncio
async def test_delete_document_rejects_foreign_owner() -> None:
    lookups: list[str] = []

    async def noop() -> None:
        return None

    async def content_by_id(content_id: str):
        lookups.append(content_id)
        return SimpleNamespace(id="doc-1", metadata={"user_id": "u2"})

    def fail_runtime(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delete authorization must not load Knowledge runtime")

    with (
        patch.object(knowledge_service, "_ensure_knowledge_contents_storage_async", noop),
        patch.object(knowledge_service, "_knowledge_content_by_id_async", content_by_id),
        patch.object(knowledge_service, "get_async_knowledge_base", fail_runtime),
    ):
        result = await knowledge_service.delete_document_async(
            "doc-1", owner_user_id="u1"
        )
    assert not result
    assert lookups == ["doc-1"]


@pytest.mark.asyncio
async def test_delete_document_uses_async_delete_dependency_for_owned_content() -> None:
    deleted: list[str] = []

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)

    async def content_by_id(content_id: str):
        assert content_id == "doc-1"
        return SimpleNamespace(id="doc-1", metadata={"user_id": "u1"})

    def fail_runtime(_search_type=None):
        raise AssertionError("delete must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
        )
    )

    result = await lifecycle.delete_document_async("doc-1", owner_user_id="u1")

    assert result
    assert deleted == ["doc-1"]


@pytest.mark.asyncio
async def test_clear_knowledge_base_deletes_all_visible_content_with_async_dependency() -> None:
    deleted: list[str] = []
    contents = [
        SimpleNamespace(id="doc-1", metadata={"user_id": "u1"}),
        SimpleNamespace(id="doc-2", metadata={"user_id": "u1"}),
        SimpleNamespace(id="doc-3", metadata={"user_id": "u2"}),
    ]

    async def delete_content_async(_knowledge, content_id: str) -> None:
        deleted.append(content_id)

    async def content_rows_async(**_kwargs: object):
        return contents, len(contents)

    def fail_runtime(_search_type=None):
        raise AssertionError("clear must not load Knowledge runtime")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=fail_runtime,
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            delete_content_async=delete_content_async,
        )
    )

    result = await lifecycle.clear_knowledge_base_async(owner_user_id="u1")

    assert result == {
        "documents": 0,
        "chunks": 0,
        "deleted_documents": 2,
        "deleted_ids": ["doc-1", "doc-2"],
        "failed_ids": [],
    }
    assert deleted == ["doc-1", "doc-2"]


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

    async def content_rows_async(**_kwargs: object):
        return contents, len(contents)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            ensure_contents_storage_async=lambda: None,
            knowledge_content_rows_async=content_rows_async,
            delete_content_async=lambda _knowledge, content_id: deleted.append(content_id),
        )
    )
    user = SimpleNamespace(id="u1", role="user", is_superuser=False)

    result = await lifecycle.clear_knowledge_base_async(user=user)

    assert result["deleted_ids"] == ["own-private"]
    assert result["failed_ids"] == []
    assert deleted == ["own-private"]


@pytest.mark.asyncio
async def test_delete_document_uses_agno_remove_and_cleans_source_snapshot() -> None:
    calls: list[tuple[str, str]] = []
    content = SimpleNamespace(id="doc-1", metadata={"user_id": "u1"})

    class KnowledgeDeleteFake:
        async def aremove_content_by_id(self, content_id: str) -> None:
            calls.append(("agno", content_id))

    async def delete_source_async(content_id: str) -> None:
        calls.append(("source", content_id))

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: KnowledgeDeleteFake(),
            ensure_contents_storage_async=lambda: None,
            knowledge_content_by_id_async=lambda _content_id: content,
            delete_source_async=delete_source_async,
        )
    )
    user = SimpleNamespace(id="u1", role="user", is_superuser=False)

    result = await lifecycle.delete_document_async("doc-1", user=user)

    assert result
    assert calls == [("agno", "doc-1"), ("source", "doc-1")]


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

    async def content_rows_async(**_kwargs: object):
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
