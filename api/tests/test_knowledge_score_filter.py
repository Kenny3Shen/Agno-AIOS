from __future__ import annotations

from types import SimpleNamespace

from api.services import knowledge_document_service, knowledge_runtime_service
from api.services.knowledge_rag_settings_service import normalize_similarity_threshold


def test_normalize_similarity_threshold_disables_non_positive() -> None:
    assert normalize_similarity_threshold(None) is None
    assert normalize_similarity_threshold(0) is None
    assert normalize_similarity_threshold(-1) is None
    assert normalize_similarity_threshold(0.35) == 0.35
    assert normalize_similarity_threshold(1.5) == 1.0


def test_filter_documents_by_score_drops_low_and_allows_empty() -> None:
    docs = [
        SimpleNamespace(content="a", meta_data={"similarity_score": 0.9}, reranking_score=None),
        SimpleNamespace(content="b", meta_data={"similarity_score": 0.2}, reranking_score=None),
        SimpleNamespace(content="c", meta_data={}, reranking_score=0.8),
    ]
    filtered = knowledge_runtime_service.filter_documents_by_score(docs, min_score=0.5)
    assert [item.content for item in filtered] == ["a", "c"]
    empty = knowledge_runtime_service.filter_documents_by_score(docs, min_score=0.95)
    assert empty == []


def test_result_projection_prefers_reranking_score_attribute() -> None:
    document = SimpleNamespace(
        content="answer",
        content_id="content-1",
        name="Runbook",
        meta_data={"similarity_score": 0.4, "source": "manual", "chunk": "2"},
        reranking_score=0.91234,
    )
    result = knowledge_document_service.result_from_document(document)
    assert result["score"] == 0.9123
    assert result["metadata"]["rerank_score"] == 0.91234


def test_project_document_for_agent_includes_score() -> None:
    document = SimpleNamespace(
        content="body",
        name="Doc",
        content_id="c1",
        meta_data={"similarity_score": 0.66, "chunk": 1},
        reranking_score=None,
    )
    payload = knowledge_runtime_service.project_document_for_agent(document)
    assert payload["score"] == 0.66
    assert payload["meta_data"]["score"] == 0.66
