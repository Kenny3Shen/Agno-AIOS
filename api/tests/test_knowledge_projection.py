from __future__ import annotations

from types import SimpleNamespace

from api.services import knowledge_document_service


def test_owner_visibility_hides_foreign_knowledge_content() -> None:
    owned = SimpleNamespace(metadata={"user_id": "u1", "visibility": "private"})
    foreign = SimpleNamespace(metadata={"user_id": "u2", "visibility": "private"})
    public = SimpleNamespace(metadata={"user_id": "u2", "visibility": "public"})
    legacy = SimpleNamespace(metadata={})
    assert knowledge_document_service.content_visible_to_owner(owned, "u1")
    assert not knowledge_document_service.content_visible_to_owner(foreign, "u1")
    assert knowledge_document_service.content_visible_to_owner(public, "u1")
    assert not knowledge_document_service.content_visible_to_owner(legacy, "u1")
    assert knowledge_document_service.content_visible_to_owner(foreign, None)


def test_document_projection_compacts_metadata_and_formats_timestamps() -> None:
    content = SimpleNamespace(
        id="doc-1",
        name="Policy",
        created_at=0,
        status="completed",
        status_message="",
        type=".md",
        size=128,
        metadata={
            "user_id": "u1",
            "source": "/kb/policy.md",
            "chunks": 3,
            "custom": "x" * 200,
            "ignored": None,
        },
    )
    document = knowledge_document_service.content_to_document(content)
    assert document["id"] == "doc-1"
    assert document["title"] == "Policy"
    assert document["source"] == "/kb/policy.md"
    assert document["chunks"] == 3
    assert document["status"] == "completed"
    assert document["type"] == ".md"
    assert document["size"] == 128
    assert document["created_at"] == "1970-01-01T00:00:00+00:00"
    assert document["metadata"]["user_id"] == "u1"
    assert "ignored" not in document["metadata"]
    assert len(document["metadata"]["custom"]) == 160


def test_completed_document_projection_has_minimum_chunk_count() -> None:
    content = SimpleNamespace(
        id="doc-ready",
        name="Markdown",
        created_at=0,
        status="completed",
        metadata={"user_id": "u1", "file_type": ".md"},
    )

    document = knowledge_document_service.content_to_document(content)

    assert document["status"] == "completed"
    assert document["chunks"] == 1


def test_result_projection_uses_rerank_score_and_source_metadata() -> None:
    document = SimpleNamespace(
        content="answer",
        content_id="content-1",
        name="Runbook",
        meta_data={"rerank_score": "0.87654", "source": "manual", "chunk": "2"},
    )
    result = knowledge_document_service.result_from_document(document)
    assert result["content"] == "answer"
    assert result["score"] == 0.8765
    assert result["doc_id"] == "content-1"
    assert result["title"] == "Runbook"
    assert result["source"] == "manual"
    assert result["chunk_index"] == 2
