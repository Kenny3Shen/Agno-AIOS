"""Docling conversion for Chat + Knowledge."""

from __future__ import annotations

from io import BytesIO

import pytest
from starlette.datastructures import Headers, UploadFile

from api.services import chat_media, docling_service, knowledge_ingest_service
from api.tests.knowledge_fakes import FakeEmbedder


def reader_config() -> knowledge_ingest_service.KnowledgeReaderConfig:
    return knowledge_ingest_service.KnowledgeReaderConfig(
        embedder=FakeEmbedder(),
        chunk_size=1200,
        chunk_overlap=160,
        markdown_split_on_headings=None,
        csv_skip_header=False,
        csv_clean_rows=True,
        code_chunk_size=1800,
        code_tokenizer="character",
        code_include_nodes=False,
        semantic_threshold=0.52,
        semantic_similarity_window=None,
        semantic_min_sentences_per_chunk=None,
        semantic_min_characters_per_sentence=None,
    )


def test_convert_plain_text_skips_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    def docling_must_not_run(**_kwargs: object) -> object:
        raise AssertionError("plain text should not initialize Docling")

    monkeypatch.setattr(docling_service, "docling_reader_markdown", docling_must_not_run)
    text = docling_service.convert_bytes_to_markdown(
        b"# Hello\n\nWorld",
        filename="note.md",
    )
    assert "Hello" in text
    assert "World" in text


def test_convert_plain_text_honors_character_and_token_budgets() -> None:
    text = docling_service.convert_bytes_to_markdown(
        b"a" * 100,
        filename="note.txt",
        max_output_chars=12,
        max_output_tokens=3,
    )
    assert len(text) <= 12
    assert docling_service.estimate_markdown_tokens(text) <= 3


def test_convert_structured_docling_honors_output_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Document:
        content = "a" * 100

    class Reader:
        def read(self, *_args: object, **_kwargs: object) -> list[Document]:
            return [Document()]

    monkeypatch.setattr(docling_service, "docling_reader_markdown", lambda **_kwargs: Reader())
    text = docling_service.convert_bytes_to_markdown(
        b"%PDF-1.4 fake",
        filename="report.pdf",
        max_output_chars=12,
        max_output_tokens=3,
    )
    assert len(text) <= 12
    assert docling_service.estimate_markdown_tokens(text) <= 3


def test_convert_html_via_docling() -> None:
    html = b"<html><body><h1>Incident</h1><p>Critical alert.</p></body></html>"
    text = docling_service.convert_bytes_to_markdown(html, filename="incident.html")
    assert "Incident" in text
    assert "Critical" in text


def test_append_document_markdown_to_message() -> None:
    out = docling_service.append_document_markdown_to_message(
        "请总结",
        [("a.pdf", "# A\n\nBody")],
    )
    assert out.startswith("请总结")
    assert "附件：a.pdf" in out
    assert "Body" in out


def test_append_document_markdown_default_prompt() -> None:
    out = docling_service.append_document_markdown_to_message(
        "",
        [("a.pdf", "content")],
    )
    assert "请根据以下附件内容进行分析" in out
    assert "content" in out


def test_structured_profile_uses_docling_reader() -> None:
    profile = knowledge_ingest_service.profile_for_filename("report.pdf")
    assert profile.strategy == "document"
    assert profile.reader == "DoclingReader"
    reader = knowledge_ingest_service.reader_for_profile(profile, reader_config(), "report.pdf")
    assert reader.__class__.__name__ == "DoclingReader"


def test_structured_profile_propagates_docling_initialization_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_docling_reader(**_kwargs: object) -> object:
        raise RuntimeError("docling unavailable")

    monkeypatch.setattr(knowledge_ingest_service, "knowledge_docling_reader", fail_docling_reader)

    with pytest.raises(RuntimeError, match="docling unavailable"):
        knowledge_ingest_service.reader_for_profile(
            knowledge_ingest_service.PROFILE_STRUCTURED,
            reader_config(),
            "report.pdf",
        )


def test_chat_document_upload_produces_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_media,
        "convert_bytes_to_markdown",
        lambda content, filename=None, force_docling=False, **_kwargs: f"# from {filename}\n\nok",
    )
    # process_document still builds File media
    upload = UploadFile(
        file=BytesIO(b"%PDF-1.4 fake"),
        filename="note.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    import asyncio

    bundle = asyncio.run(chat_media.process_chat_uploads([upload]))
    assert bundle.document_markdown
    assert bundle.document_markdown[0][0] == "note.pdf"
    assert "ok" in bundle.document_markdown[0][1]
    assert bundle.files == ()
    assert len(bundle.workspace_files) == 1
    assert bundle.attachments[0]["engine"] == "docling"
    assert bundle.attachments[0]["converted"] == "markdown"
