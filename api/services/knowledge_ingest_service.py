from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agno.knowledge.chunking.code import CodeChunking
from agno.knowledge.chunking.document import DocumentChunking
from agno.knowledge.chunking.markdown import MarkdownChunking
from agno.knowledge.chunking.recursive import RecursiveChunking
from agno.knowledge.chunking.row import RowChunking
from agno.knowledge.chunking.semantic import SemanticChunking
from agno.knowledge.embedder import Embedder
from agno.knowledge.reader.csv_reader import CSVReader
from agno.knowledge.reader.docx_reader import DocxReader
from agno.knowledge.reader.json_reader import JSONReader
from agno.knowledge.reader.markdown_reader import MarkdownReader
from agno.knowledge.reader.pdf_reader import PDFReader
from agno.knowledge.reader.text_reader import TextReader


@dataclass(frozen=True)
class KnowledgeIngestProfile:
    suffixes: tuple[str, ...]
    strategy: str
    reader: str
    label: str
    description: str


@dataclass(frozen=True)
class KnowledgeReaderConfig:
    embedder: Embedder | None
    chunk_size: int
    chunk_overlap: int
    code_chunk_size: int
    semantic_threshold: float


KnowledgeReader = TextReader | MarkdownReader | CSVReader | JSONReader | PDFReader | DocxReader

MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")
CSV_SUFFIXES = (".csv", ".tsv")
JSON_SUFFIXES = (".json", ".jsonl")
CODE_SUFFIXES = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".sh",
    ".sql",
)
STRUCTURED_DOC_SUFFIXES = (".pdf", ".docx")
TEXT_SUFFIXES = (".txt", ".log", ".rst", ".yaml", ".yml", ".toml")

SUPPORTED_FILE_SUFFIXES = (
    *MARKDOWN_SUFFIXES,
    *CSV_SUFFIXES,
    *JSON_SUFFIXES,
    *CODE_SUFFIXES,
    *STRUCTURED_DOC_SUFFIXES,
    *TEXT_SUFFIXES,
)

PROFILE_MARKDOWN = KnowledgeIngestProfile(
    suffixes=MARKDOWN_SUFFIXES,
    strategy="markdown",
    reader="MarkdownReader",
    label="Markdown",
    description="按标题结构保留层级，适合 runbook、设计文档和知识手册。",
)
PROFILE_CSV = KnowledgeIngestProfile(
    suffixes=CSV_SUFFIXES,
    strategy="csv_row",
    reader="CSVReader",
    label="CSV Row",
    description="每行一个逻辑 chunk，适合资产、告警和漏洞清单。",
)
PROFILE_JSON = KnowledgeIngestProfile(
    suffixes=JSON_SUFFIXES,
    strategy="json",
    reader="JSONReader",
    label="JSON",
    description="对象和数组元素先结构化读取，再按递归策略切分长字段。",
)
PROFILE_CODE = KnowledgeIngestProfile(
    suffixes=CODE_SUFFIXES,
    strategy="code",
    reader="TextReader",
    label="Code",
    description="按函数、类和语法节点边界切分，适合脚本和源码。",
)
PROFILE_STRUCTURED = KnowledgeIngestProfile(
    suffixes=STRUCTURED_DOC_SUFFIXES,
    strategy="document",
    reader="DocumentReader",
    label="Document",
    description="按段落、页和章节保留文档结构，适合 PDF/DOCX。",
)
PROFILE_TEXT = KnowledgeIngestProfile(
    suffixes=TEXT_SUFFIXES,
    strategy="semantic",
    reader="TextReader",
    label="Semantic",
    description="按语义边界切分通用文本，提升自然语言检索命中质量。",
)

INGEST_PROFILES = (
    PROFILE_MARKDOWN,
    PROFILE_CSV,
    PROFILE_JSON,
    PROFILE_CODE,
    PROFILE_STRUCTURED,
    PROFILE_TEXT,
)


def profile_for_filename(filename: str | None) -> KnowledgeIngestProfile:
    suffix = Path(filename or "").suffix.lower()
    for profile in INGEST_PROFILES:
        if suffix in profile.suffixes:
            return profile
    return PROFILE_TEXT


def _semantic_chunking(config: KnowledgeReaderConfig) -> SemanticChunking:
    if config.embedder is None:
        raise RuntimeError("semantic knowledge reader requires an embedder")
    return SemanticChunking(
        embedder=config.embedder,
        chunk_size=config.chunk_size,
        similarity_threshold=config.semantic_threshold,
    )


def _document_chunking(config: KnowledgeReaderConfig) -> DocumentChunking:
    return DocumentChunking(chunk_size=config.chunk_size, overlap=config.chunk_overlap)


def _recursive_chunking(config: KnowledgeReaderConfig) -> RecursiveChunking:
    return RecursiveChunking(chunk_size=config.chunk_size, overlap=config.chunk_overlap)


def reader_for_profile(
    profile: KnowledgeIngestProfile,
    config: KnowledgeReaderConfig,
    filename: str | None = None,
) -> KnowledgeReader:
    suffix = Path(filename or "").suffix.lower()
    if profile.strategy == "markdown":
        return MarkdownReader(
            chunking_strategy=MarkdownChunking(
                chunk_size=config.chunk_size,
                overlap=config.chunk_overlap,
                split_on_headings=True,
            )
        )
    if profile.strategy == "csv_row":
        return CSVReader(chunking_strategy=RowChunking(skip_header=False))
    if profile.strategy == "json":
        return JSONReader(chunking_strategy=_recursive_chunking(config))
    if profile.strategy == "code":
        return TextReader(
            chunking_strategy=CodeChunking(
                chunk_size=config.code_chunk_size,
                language="auto",
            )
        )
    if profile.strategy == "document":
        if suffix == ".pdf":
            return PDFReader(chunking_strategy=_document_chunking(config))
        if suffix == ".docx":
            return DocxReader(chunking_strategy=_document_chunking(config))
        return TextReader(chunking_strategy=_document_chunking(config))
    return TextReader(chunking_strategy=_semantic_chunking(config))


def reader_for_filename(filename: str | None, config: KnowledgeReaderConfig) -> KnowledgeReader:
    return reader_for_profile(profile_for_filename(filename), config, filename)


def pipeline_status(
    *,
    search_type: str,
    vector_score_weight: float,
    prefix_match: bool,
    content_language: str,
    semantic_threshold: float,
    code_chunk_size: int,
) -> dict[str, Any]:
    return {
        "search_type": search_type,
        "vector_score_weight": vector_score_weight,
        "prefix_match": prefix_match,
        "content_language": content_language,
        "supported_suffixes": sorted(SUPPORTED_FILE_SUFFIXES),
        "chunk_profiles": [
            {
                "label": profile.label,
                "strategy": profile.strategy,
                "reader": profile.reader,
                "suffixes": list(profile.suffixes),
                "description": profile.description,
            }
            for profile in INGEST_PROFILES
        ],
        "semantic_threshold": semantic_threshold,
        "code_chunk_size": code_chunk_size,
    }
