from __future__ import annotations

from types import SimpleNamespace

from api.services import knowledge_document_service


def test_owner_visibility_hides_foreign_knowledge_content() -> None:
    owned = SimpleNamespace(metadata={"user_id": "u1", "visibility": "private"})
    foreign = SimpleNamespace(metadata={"user_id": "u2", "visibility": "private"})
    public = SimpleNamespace(metadata={"user_id": "u2", "visibility": "public"})
    unowned = SimpleNamespace(metadata={})
    assert knowledge_document_service.content_visible_to_owner(owned, "u1")
    assert not knowledge_document_service.content_visible_to_owner(foreign, "u1")
    assert knowledge_document_service.content_visible_to_owner(public, "u1")
    assert not knowledge_document_service.content_visible_to_owner(unowned, "u1")
    assert knowledge_document_service.content_visible_to_owner(foreign, None)


def test_document_projection_compacts_metadata_and_formats_timestamps() -> None:
    content = SimpleNamespace(
        id="doc-1",
        name="Policy",
        created_at=0,
        updated_at=3600,
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
    assert document["created_at"] == "1970-01-01T00:00:00+00:00"
    assert document["updated_at"] == "1970-01-01T01:00:00+00:00"
    assert document["metadata"]["user_id"] == "u1"
    assert "ignored" not in document["metadata"]
    assert 0 < len(document["metadata"]["custom"]) < 200


def test_document_projection_falls_back_updated_at_to_created_at() -> None:
    content = SimpleNamespace(
        id="doc-2",
        name="Policy",
        created_at=0,
        metadata={"source": "manual"},
    )
    document = knowledge_document_service.content_to_document(content)
    assert document["created_at"] == "1970-01-01T00:00:00+00:00"
    assert document["updated_at"] == document["created_at"]


def test_document_projection_hides_internal_source_metadata() -> None:
    content = SimpleNamespace(
        id="doc-1",
        name="Policy",
        created_at=0,
        metadata={
            "user_id": "u1",
            "source": "manual",
            "_tais_source": {"kind": "text", "digest": "digest-1", "version": 1},
        },
    )

    document = knowledge_document_service.content_to_document(content)

    assert "_tais_source" not in document["metadata"]


def test_document_projection_includes_persisted_ingest_options() -> None:
    content = SimpleNamespace(
        id="doc-options",
        name="Runbook",
        created_at=0,
        metadata={
            "file_name": "runbook.md",
            "chunk_size": "1800",
            "chunk_overlap": "120",
            "markdown_split_on_headings": "2",
            "csv_skip_header": "false",
            "csv_clean_rows": "true",
            "code_chunk_size": "2200",
            "code_tokenizer": "gpt2",
            "code_include_nodes": "true",
            "semantic_threshold": "0.61",
            "semantic_similarity_window": "4",
            "semantic_min_sentences_per_chunk": "2",
            "semantic_min_characters_per_sentence": "12",
            "reader_strategy": "markdown",
        },
    )

    document = knowledge_document_service.content_to_document(content)

    assert document["metadata"] == content.metadata


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
    assert result["score"] == 0.8765
    assert result["doc_id"] == "content-1"
    assert result["title"] == "Runbook"
    assert result["source"] == "manual"
    assert result["chunk_index"] == 2
