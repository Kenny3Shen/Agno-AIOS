"""Shared Docling conversion helpers for Chat uploads and Knowledge ingest.

Uses Agno's ``DoclingReader`` (IBM Docling) to turn office/PDF/HTML documents
into Markdown text that models can consume as plain input.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from loguru import logger

# Extensions that benefit from Docling (binary / structured docs).
# Plain text formats are decoded directly for speed and predictability.
DOCLING_SUFFIXES = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".asciidoc",
        ".adoc",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".webp",
    }
)

# Decoded as UTF-8 (with fallback) instead of full Docling pipeline.
PLAIN_TEXT_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".mdown",
        ".mkd",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".xml",
        ".yaml",
        ".yml",
        ".toml",
        ".log",
        ".rst",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".css",
        ".sql",
        ".sh",
        ".rb",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".php",
        ".rtf",
    }
)


def _suffix(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


@lru_cache(maxsize=1)
def docling_reader_markdown(*, chunk: bool = False) -> Any:
    """Cached Agno DoclingReader exporting Markdown (no chunking by default)."""
    from agno.knowledge.reader.docling_reader import DoclingReader

    return DoclingReader(output_format="markdown", chunk=chunk)


def knowledge_docling_reader(chunking_strategy: Any | None = None) -> Any:
    """DoclingReader for Knowledge ingest (chunking applied by the reader)."""
    from agno.knowledge.reader.docling_reader import DoclingReader

    return DoclingReader(
        output_format="markdown",
        chunking_strategy=chunking_strategy,
        chunk=True,
    )


def _decode_plain_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def convert_bytes_to_markdown(
    content: bytes,
    *,
    filename: str | None = None,
    force_docling: bool = False,
) -> str:
    """Convert file bytes to Markdown (or plain text for source-like files).

    Args:
        content: Raw upload bytes.
        filename: Original filename (used for format detection).
        force_docling: Always run Docling even for plain-text suffixes.

    Returns:
        Markdown / text string. Raises ValueError when conversion yields nothing.
    """
    if not content:
        raise ValueError("empty file")

    suffix = _suffix(filename)
    if not force_docling and suffix in PLAIN_TEXT_SUFFIXES:
        text = _decode_plain_text(content).strip()
        if not text:
            raise ValueError("empty text content")
        return text

    # Prefer Docling for structured docs; fall back to plain decode for unknown.
    use_docling = force_docling or suffix in DOCLING_SUFFIXES or not suffix
    if use_docling:
        try:
            reader = docling_reader_markdown(chunk=False)
            stream = BytesIO(content)
            # Docling DocumentStream uses the stream name for format sniffing.
            stream.name = filename or f"upload{suffix or '.bin'}"
            documents = reader.read(stream, name=filename or stream.name)
            parts = [
                str(getattr(doc, "content", "") or "").strip()
                for doc in (documents or [])
                if str(getattr(doc, "content", "") or "").strip()
            ]
            if parts:
                return "\n\n".join(parts)
            logger.warning(
                "Docling returned empty content for {}; falling back when possible",
                filename,
            )
        except Exception as exc:
            logger.warning(
                "Docling conversion failed for {}: {}",
                filename,
                exc,
            )
            if suffix in DOCLING_SUFFIXES:
                raise ValueError(f"Docling 无法解析: {filename or 'file'} ({exc})") from exc

    # Fallback: treat as text
    text = _decode_plain_text(content).strip()
    if not text:
        raise ValueError(f"无法解析文档内容: {filename or 'file'}")
    return text


def format_attachment_markdown_block(filename: str, markdown: str) -> str:
    """Wrap converted attachment content for chat message injection."""
    name = (filename or "attachment").strip() or "attachment"
    body = (markdown or "").strip()
    return f"\n\n---\n### 附件：{name}\n\n{body}\n"


def append_document_markdown_to_message(
    message: str,
    documents: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    """Append Docling-converted Markdown blocks to the user message."""
    base = (message or "").strip()
    if not documents:
        return base
    blocks = [format_attachment_markdown_block(name, md) for name, md in documents]
    if not base:
        base = "请根据以下附件内容进行分析。"
    return base + "".join(blocks)
