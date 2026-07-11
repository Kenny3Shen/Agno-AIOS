from __future__ import annotations

from collections.abc import Mapping
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
    markdown_split_on_headings: int | None
    csv_skip_header: bool
    csv_clean_rows: bool
    code_chunk_size: int
    code_tokenizer: str
    code_include_nodes: bool
    semantic_threshold: float
    semantic_similarity_window: int | None
    semantic_min_sentences_per_chunk: int | None
    semantic_min_characters_per_sentence: int | None


@dataclass(frozen=True)
class KnowledgeIngestOverrides:
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    markdown_split_on_headings: int | None = None
    csv_skip_header: bool | None = None
    csv_clean_rows: bool | None = None
    code_chunk_size: int | None = None
    code_tokenizer: str | None = None
    code_include_nodes: bool | None = None
    semantic_threshold: float | None = None
    semantic_similarity_window: int | None = None
    semantic_min_sentences_per_chunk: int | None = None
    semantic_min_characters_per_sentence: int | None = None
    reader_strategy: str | None = None


KnowledgeReader = TextReader | MarkdownReader | CSVReader | JSONReader | PDFReader | DocxReader

MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")
CSV_SUFFIXES = (".csv", ".tsv")
JSON_SUFFIXES = (".json", ".jsonl")
CODE_SUFFIXES = (
    ".py",
    ".js",
    ".mjs",
    ".cjs",
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
SUPPORTED_READER_STRATEGIES = tuple(profile.strategy for profile in INGEST_PROFILES)
SUPPORTED_CODE_TOKENIZERS = ("character", "gpt2")

CODE_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".php": "php",
    ".rb": "ruby",
    ".sh": "bash",
    ".sql": "sql",
}


def profile_for_filename(filename: str | None) -> KnowledgeIngestProfile:
    suffix = Path(filename or "").suffix.lower()
    for profile in INGEST_PROFILES:
        if suffix in profile.suffixes:
            return profile
    return PROFILE_TEXT


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, str | int | float):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if not isinstance(value, str | int | float):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def profile_for_strategy(strategy: str | None) -> KnowledgeIngestProfile | None:
    clean_strategy = (strategy or "").strip().lower()
    if not clean_strategy:
        return None
    for profile in INGEST_PROFILES:
        if profile.strategy == clean_strategy:
            return profile
    return None


def profile_for_filename_or_strategy(
    filename: str | None,
    strategy: str | None,
) -> KnowledgeIngestProfile:
    return profile_for_strategy(strategy) or profile_for_filename(filename)


def code_language_for_filename(filename: str | None) -> str | None:
    return CODE_LANGUAGE_BY_SUFFIX.get(Path(filename or "").suffix.lower())


def coerce_ingest_overrides(values: Mapping[str, object] | None) -> KnowledgeIngestOverrides:
    source = values or {}
    reader_strategy = _optional_string(source.get("reader_strategy"))
    if reader_strategy is not None and reader_strategy not in SUPPORTED_READER_STRATEGIES:
        allowed = ", ".join(SUPPORTED_READER_STRATEGIES)
        raise ValueError(f"reader_strategy must be one of: {allowed}")
    markdown_split_on_headings = _optional_int(source.get("markdown_split_on_headings"))
    if markdown_split_on_headings is not None and not 0 <= markdown_split_on_headings <= 6:
        raise ValueError("markdown_split_on_headings must be between 0 and 6")
    code_tokenizer = _optional_string(source.get("code_tokenizer"))
    if code_tokenizer is not None and code_tokenizer not in SUPPORTED_CODE_TOKENIZERS:
        allowed = ", ".join(SUPPORTED_CODE_TOKENIZERS)
        raise ValueError(f"code_tokenizer must be one of: {allowed}")
    return KnowledgeIngestOverrides(
        chunk_size=_optional_int(source.get("chunk_size")),
        chunk_overlap=_optional_int(source.get("chunk_overlap")),
        markdown_split_on_headings=markdown_split_on_headings,
        csv_skip_header=_optional_bool(source.get("csv_skip_header")),
        csv_clean_rows=_optional_bool(source.get("csv_clean_rows")),
        code_chunk_size=_optional_int(source.get("code_chunk_size")),
        code_tokenizer=code_tokenizer,
        code_include_nodes=_optional_bool(source.get("code_include_nodes")),
        semantic_threshold=_optional_float(source.get("semantic_threshold")),
        semantic_similarity_window=_optional_int(source.get("semantic_similarity_window")),
        semantic_min_sentences_per_chunk=_optional_int(source.get("semantic_min_sentences_per_chunk")),
        semantic_min_characters_per_sentence=_optional_int(source.get("semantic_min_characters_per_sentence")),
        reader_strategy=reader_strategy,
    )


def _semantic_chunking(config: KnowledgeReaderConfig) -> SemanticChunking:
    if config.embedder is None:
        raise RuntimeError("semantic knowledge reader requires an embedder")
    return SemanticChunking(
        embedder=config.embedder,
        chunk_size=config.chunk_size,
        similarity_threshold=config.semantic_threshold,
        similarity_window=(
            config.semantic_similarity_window
            if config.semantic_similarity_window is not None
            else 3
        ),
        min_sentences_per_chunk=(
            config.semantic_min_sentences_per_chunk
            if config.semantic_min_sentences_per_chunk is not None
            else 1
        ),
        min_characters_per_sentence=(
            config.semantic_min_characters_per_sentence
            if config.semantic_min_characters_per_sentence is not None
            else 24
        ),
    )


def _validate_overlap(config: KnowledgeReaderConfig) -> None:
    if config.chunk_overlap >= config.chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")


def _document_chunking(config: KnowledgeReaderConfig) -> DocumentChunking:
    _validate_overlap(config)
    return DocumentChunking(chunk_size=config.chunk_size, overlap=config.chunk_overlap)


def _recursive_chunking(config: KnowledgeReaderConfig) -> RecursiveChunking:
    _validate_overlap(config)
    return RecursiveChunking(chunk_size=config.chunk_size, overlap=config.chunk_overlap)


def reader_for_profile(
    profile: KnowledgeIngestProfile,
    config: KnowledgeReaderConfig,
    filename: str | None = None,
) -> KnowledgeReader:
    suffix = Path(filename or "").suffix.lower()
    if profile.strategy == "markdown":
        _validate_overlap(config)
        split_on_headings: bool | int = (
            True
            if config.markdown_split_on_headings is None
            else config.markdown_split_on_headings
        )
        if split_on_headings == 0:
            split_on_headings = False
        return MarkdownReader(
            chunking_strategy=MarkdownChunking(
                chunk_size=config.chunk_size,
                overlap=config.chunk_overlap,
                split_on_headings=split_on_headings,
            )
        )
    if profile.strategy == "csv_row":
        return CSVReader(
            chunking_strategy=RowChunking(
                skip_header=config.csv_skip_header,
                clean_rows=config.csv_clean_rows,
            )
        )
    if profile.strategy == "json":
        return JSONReader(chunking_strategy=_recursive_chunking(config))
    if profile.strategy == "code":
        language = code_language_for_filename(filename)
        if language is None:
            return TextReader(chunking_strategy=_recursive_chunking(config))
        return TextReader(
            chunking_strategy=CodeChunking(
                tokenizer=config.code_tokenizer,
                chunk_size=config.code_chunk_size,
                language=language,
                include_nodes=config.code_include_nodes,
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
