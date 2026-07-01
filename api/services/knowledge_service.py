from __future__ import annotations

import importlib
import os
import threading
import warnings
from datetime import UTC, datetime
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agno.knowledge.chunking.code import CodeChunking
from agno.knowledge.chunking.document import DocumentChunking
from agno.knowledge.chunking.markdown import MarkdownChunking
from agno.knowledge.chunking.row import RowChunking
from agno.knowledge.chunking.recursive import RecursiveChunking
from agno.knowledge.chunking.semantic import SemanticChunking
from agno.knowledge.document import Document
from agno.knowledge.embedder import Embedder
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.reader.csv_reader import CSVReader
from agno.knowledge.reader.docx_reader import DocxReader
from agno.knowledge.reader.json_reader import JSONReader
from agno.knowledge.reader.markdown_reader import MarkdownReader
from agno.knowledge.reader.pdf_reader import PDFReader
from agno.knowledge.reader.text_reader import TextReader
from agno.knowledge.reranker.base import Reranker
from agno.vectordb.distance import Distance
from agno.vectordb.pgvector import PgVector
from agno.vectordb.search import SearchType
from pydantic import ConfigDict
from sqlalchemy import func, select

from api.services.postgres_store import (
    get_knowledge_postgres_db,
    knowledge_schema,
    postgres_label,
    postgres_sqlalchemy_url,
)

if TYPE_CHECKING:
    from FlagEmbedding import FlagReranker
    from sentence_transformers import SentenceTransformer
else:
    FlagReranker = Any
    SentenceTransformer = Any


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


KNOWLEDGE_NAME = os.getenv("AGNO_KNOWLEDGE_NAME", "security_knowledge")
PGVECTOR_TABLE = os.getenv("AGNO_KNOWLEDGE_PGVECTOR_TABLE", "security_knowledge_vectors")
POSTGRES_SCHEMA = os.getenv("AGNO_KNOWLEDGE_SCHEMA", knowledge_schema())
POSTGRES_KNOWLEDGE_TABLE = os.getenv(
    "AGNO_POSTGRES_KNOWLEDGE_TABLE", "agno_knowledge"
)
EMBEDDING_MODEL = os.getenv("AGNO_KNOWLEDGE_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
EMBEDDING_DIMENSIONS = max(1, _env_int("AGNO_KNOWLEDGE_EMBEDDING_DIMENSIONS", 512))
RERANK_MODEL = os.getenv("AGNO_KNOWLEDGE_RERANK_MODEL", "BAAI/bge-reranker-base")
BGE_QUERY_PROMPT = os.getenv(
    "AGNO_KNOWLEDGE_QUERY_PROMPT", "为这个句子生成表示以用于检索相关文章："
)
TOP_K = max(1, _env_int("AGNO_KNOWLEDGE_TOP_K", 5))
CHUNK_SIZE = max(200, _env_int("AGNO_KNOWLEDGE_CHUNK_SIZE", 1200))
CHUNK_OVERLAP = max(0, _env_int("AGNO_KNOWLEDGE_CHUNK_OVERLAP", 160))
CODE_CHUNK_SIZE = max(256, _env_int("AGNO_KNOWLEDGE_CODE_CHUNK_SIZE", 1800))
SEMANTIC_THRESHOLD = _env_float("AGNO_KNOWLEDGE_SEMANTIC_THRESHOLD", 0.52)
VECTOR_SCORE_WEIGHT = _env_float("AGNO_KNOWLEDGE_VECTOR_SCORE_WEIGHT", 0.55)
CONTENT_LANGUAGE = os.getenv("AGNO_KNOWLEDGE_CONTENT_LANGUAGE", "english")
PREFIX_MATCH = _env_bool("AGNO_KNOWLEDGE_PREFIX_MATCH", False)
RERANK_ENABLED = _env_bool("AGNO_KNOWLEDGE_RERANK_ENABLED", True)
RERANK_CANDIDATE_MULTIPLIER = max(
    1,
    _env_int("AGNO_KNOWLEDGE_RERANK_CANDIDATE_MULTIPLIER", 3),
)
RERANK_MIN_CANDIDATES = max(
    1,
    _env_int("AGNO_KNOWLEDGE_RERANK_MIN_CANDIDATES", 10),
)
MODEL_DEVICE = os.getenv("AGNO_KNOWLEDGE_DEVICE", "auto").strip().lower() or "auto"
COLD_START_NOTE = (
    "首次触发知识写入、向量检索或重排时会同步加载/下载本地模型，"
    "冷启动可能阻塞 30-120 秒，取决于网络、磁盘和 CPU。"
)
DOCUMENT_METADATA_KEYS = (
    "title",
    "source",
    "file_path",
    "file_name",
    "file_type",
    "chunk_strategy",
    "reader",
    "file_size",
    "mime_type",
    "input_mode",
    "upload_mode",
    "chunks",
)
DOCUMENT_METADATA_MAX_ITEMS = 12
DOCUMENT_METADATA_VALUE_MAX_LENGTH = 160

_embedding_model: SentenceTransformer | None = None
_embedding_dimensions: int | None = None
_reranker_model: FlagReranker | None = None
_torch_module: Any | None = None
_torch_import_error: Exception | None = None
_embedding_model_lock = threading.Lock()
_reranker_model_lock = threading.Lock()
_knowledge_lock = threading.Lock()


@dataclass(frozen=True)
class KnowledgeIngestProfile:
    suffixes: tuple[str, ...]
    strategy: str
    reader: str
    label: str
    description: str


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

_PROFILE_MARKDOWN = KnowledgeIngestProfile(
    suffixes=MARKDOWN_SUFFIXES,
    strategy="markdown",
    reader="MarkdownReader",
    label="Markdown",
    description="按标题结构保留层级，适合 runbook、设计文档和知识手册。",
)
_PROFILE_CSV = KnowledgeIngestProfile(
    suffixes=CSV_SUFFIXES,
    strategy="csv_row",
    reader="CSVReader",
    label="CSV Row",
    description="每行一个逻辑 chunk，适合资产、告警和漏洞清单。",
)
_PROFILE_JSON = KnowledgeIngestProfile(
    suffixes=JSON_SUFFIXES,
    strategy="json",
    reader="JSONReader",
    label="JSON",
    description="对象和数组元素先结构化读取，再按递归策略切分长字段。",
)
_PROFILE_CODE = KnowledgeIngestProfile(
    suffixes=CODE_SUFFIXES,
    strategy="code",
    reader="TextReader",
    label="Code",
    description="按函数、类和语法节点边界切分，适合脚本和源码。",
)
_PROFILE_STRUCTURED = KnowledgeIngestProfile(
    suffixes=STRUCTURED_DOC_SUFFIXES,
    strategy="document",
    reader="DocumentReader",
    label="Document",
    description="按段落、页和章节保留文档结构，适合 PDF/DOCX。",
)
_PROFILE_TEXT = KnowledgeIngestProfile(
    suffixes=TEXT_SUFFIXES,
    strategy="semantic",
    reader="TextReader",
    label="Semantic",
    description="按语义边界切分通用文本，提升自然语言检索命中质量。",
)


def _load_torch() -> Any | None:
    global _torch_module, _torch_import_error
    if _torch_module is not None:
        return _torch_module
    if _torch_import_error is not None:
        return None
    try:
        _torch_module = importlib.import_module("torch")
    except Exception as exc:
        _torch_import_error = exc
        return None
    return _torch_module


def _torch_runtime_error() -> RuntimeError:
    detail = str(_torch_import_error) if _torch_import_error else "unknown error"
    return RuntimeError(
        "PyTorch runtime is unavailable for the knowledge models. "
        "Install a CPU PyTorch build or a CUDA build compatible with the local GPU. "
        f"Original error: {detail}"
    )


def _dependency_runtime_error(package_name: str, exc: Exception) -> RuntimeError:
    return RuntimeError(
        f"{package_name} is unavailable for the knowledge pipeline. "
        f"Install the dependency and its PyTorch runtime before using Agentic RAG. Original error: {exc}"
    )


def _auto_device() -> str:
    torch = _load_torch()
    if torch is None:
        return "cpu"

    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return "mps"

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Found GPU\d+ .* compute capability .*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*is not compatible with the current PyTorch installation.*",
            category=UserWarning,
        )
        try:
            if not torch.cuda.is_available():
                return "cpu"
            capability = torch.cuda.get_device_capability(0)
            arch_list = torch.cuda.get_arch_list()
        except Exception:
            return "cpu"

    current_arch = f"sm_{capability[0]}{capability[1]}"
    if arch_list and current_arch not in set(arch_list):
        return "cpu"
    return "cuda:0"


def _model_device() -> str:
    return _auto_device() if MODEL_DEVICE == "auto" else MODEL_DEVICE


def _sentence_transformer_cls() -> type[SentenceTransformer]:
    try:
        module = importlib.import_module("sentence_transformers")
    except Exception as exc:
        raise _dependency_runtime_error("sentence-transformers", exc) from exc
    return cast(type[SentenceTransformer], module.SentenceTransformer)


def _flag_reranker_cls() -> type[FlagReranker]:
    try:
        module = importlib.import_module("FlagEmbedding")
    except Exception as exc:
        raise _dependency_runtime_error("FlagEmbedding", exc) from exc
    return cast(type[FlagReranker], module.FlagReranker)


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model, _embedding_dimensions
    if _embedding_model is not None:
        return _embedding_model
    with _embedding_model_lock:
        if _embedding_model is None:
            if _load_torch() is None:
                raise _torch_runtime_error()
            sentence_transformer_cls = _sentence_transformer_cls()
            model = sentence_transformer_cls(
                EMBEDDING_MODEL,
                device=_model_device(),
            )
            embedding_dimensions = model.get_embedding_dimension()
            if not isinstance(embedding_dimensions, int) or embedding_dimensions <= 0:
                raise RuntimeError(
                    f"Failed to detect embedding dimension for model {EMBEDDING_MODEL}"
                )
            if embedding_dimensions != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    f"Embedding model {EMBEDDING_MODEL} produces {embedding_dimensions} dimensions, "
                    f"but AGNO_KNOWLEDGE_EMBEDDING_DIMENSIONS is {EMBEDDING_DIMENSIONS}. "
                    "Set the correct dimension or rebuild the PgVector table."
                )
            _embedding_model = model
            _embedding_dimensions = embedding_dimensions
    return _embedding_model


def _get_embedding_dimensions() -> int:
    global _embedding_dimensions
    if _embedding_dimensions is None:
        _get_embedding_model()
    if _embedding_dimensions is None:
        raise RuntimeError(
            f"Embedding dimension is unavailable for model {EMBEDDING_MODEL}"
        )
    return _embedding_dimensions


class BGEKnowledgeEmbedder(Embedder):
    """SentenceTransformer embedder with BGE query-prompt semantics."""

    def __init__(self) -> None:
        super().__init__(dimensions=EMBEDDING_DIMENSIONS)

    def _encode(self, text: str, *, query: bool) -> list[float]:
        model = _get_embedding_model()
        encoded_text = f"{BGE_QUERY_PROMPT}{text}" if query else text
        embedding = model.encode(
            [encoded_text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return cast(list[float], embedding[0].tolist())

    def get_embedding(self, text: str) -> list[float]:
        return self._encode(text, query=True)

    def get_embedding_and_usage(self, text: str) -> tuple[list[float], None]:
        return self._encode(text, query=False), None

    async def async_get_embedding(self, text: str) -> list[float]:
        return self.get_embedding(text)

    async def async_get_embedding_and_usage(
        self, text: str
    ) -> tuple[list[float], None]:
        return self.get_embedding_and_usage(text)


def _patch_tokenizer_prepare_for_model(
    tokenizer: Any,
    type_vocab_size: int = 1,
) -> None:
    """Patch older FlagEmbedding rerankers for newer transformers runtimes."""
    if hasattr(tokenizer, "prepare_for_model"):
        return

    import types

    try:
        from transformers.tokenization_utils_base import BatchEncoding
    except ImportError:
        return

    _type_vocab_size = type_vocab_size

    def prepare_for_model(
        self: Any,
        ids: list[int],
        pair_ids: list[int] | None = None,
        max_length: int | None = None,
        truncation: str = "do_not_truncate",
        padding: bool = False,
        return_token_type_ids: bool = True,
        **_kwargs: Any,
    ) -> Any:
        pair = pair_ids is not None
        ids_list = list(ids)
        pair_list = list(pair_ids) if pair_ids else []
        len_ids = len(ids_list)
        len_pair = len(pair_list)
        num_special = self.num_special_tokens_to_add(pair=pair)

        if max_length is not None and (len_ids + len_pair + num_special) > max_length:
            if truncation == "only_second":
                max_pair = max_length - len_ids - num_special
                pair_list = [] if max_pair <= 0 else pair_list[:max_pair]
            elif truncation == "only_first":
                max_first = max_length - len_pair - num_special
                ids_list = [] if max_first <= 0 else ids_list[:max_first]
            elif truncation == "longest_first":
                while (len(ids_list) + len(pair_list) + num_special) > max_length:
                    if len(ids_list) > len(pair_list):
                        ids_list.pop()
                    elif pair_list:
                        pair_list.pop()
                    else:
                        ids_list.pop()

        bos = int(self.cls_token_id or self.bos_token_id)
        eos = int(self.sep_token_id or self.eos_token_id)
        sep = int(self.sep_token_id)
        between_seps = num_special - 2

        if pair:
            sequence = [bos, *ids_list, *([sep] * between_seps), *pair_list, eos]
        else:
            sequence = [bos, *ids_list, eos]

        result: dict[str, list[int]] = {"input_ids": sequence}
        if return_token_type_ids and _type_vocab_size > 1:
            if pair:
                seg_a_len = 1 + len(ids_list) + between_seps
                seg_b_len = len(pair_list) + 1
                result["token_type_ids"] = [0] * seg_a_len + [1] * seg_b_len
            else:
                result["token_type_ids"] = [0] * len(sequence)
        result["attention_mask"] = [1] * len(sequence)

        batch = BatchEncoding(result)
        if padding:
            batch = BatchEncoding(dict(batch.convert_to_tensors("pt")))
        return batch

    tokenizer.prepare_for_model = types.MethodType(prepare_for_model, tokenizer)


def _get_reranker_model() -> FlagReranker:
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model
    with _reranker_model_lock:
        if _reranker_model is None:
            if _load_torch() is None:
                raise _torch_runtime_error()
            use_fp16 = _env_bool("AGNO_KNOWLEDGE_RERANK_USE_FP16", False)
            device = _model_device()
            flag_reranker_cls = _flag_reranker_cls()
            _reranker_model = flag_reranker_cls(
                RERANK_MODEL,
                use_fp16=use_fp16 and device.startswith("cuda"),
                devices=device,
            )
            tv_size = 1
            model = getattr(_reranker_model, "model", None)
            config = getattr(model, "config", None)
            raw_type_vocab_size = getattr(config, "type_vocab_size", 1)
            if isinstance(raw_type_vocab_size, int) and raw_type_vocab_size > 0:
                tv_size = raw_type_vocab_size
            _patch_tokenizer_prepare_for_model(
                _reranker_model.tokenizer,
                type_vocab_size=tv_size,
            )
    return _reranker_model


class FlagEmbeddingReranker(Reranker):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def rerank(self, query: str, documents: list[Document]) -> list[Document]:
        if not documents:
            return []
        reranker = _get_reranker_model()
        pairs = [(query, document.content) for document in documents]
        raw_scores = reranker.compute_score(pairs, normalize=True)
        scores = (
            [float(raw_scores)]
            if isinstance(raw_scores, int | float)
            else [float(score) for score in raw_scores]
        )
        for document, score in zip(documents, scores, strict=False):
            document.reranking_score = score
            document.meta_data["rerank_score"] = score
        return sorted(
            documents,
            key=lambda doc: doc.reranking_score
            if doc.reranking_score is not None
            else float("-inf"),
            reverse=True,
        )


@lru_cache(maxsize=1)
def _get_embedder() -> BGEKnowledgeEmbedder:
    return BGEKnowledgeEmbedder()


@lru_cache(maxsize=1)
def _get_reranker() -> FlagEmbeddingReranker | None:
    if not RERANK_ENABLED:
        return None
    return FlagEmbeddingReranker()


def _search_type_from_name(value: str | None) -> SearchType:
    clean_value = (value or "").strip().lower()
    if not clean_value:
        return SearchType.hybrid
    try:
        return SearchType(clean_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SearchType)
        raise ValueError(f"不支持的 search_type: {value}. 可选值: {allowed}") from exc


def search_type_from_env() -> SearchType:
    return _search_type_from_name(os.getenv("AGNO_KNOWLEDGE_SEARCH_TYPE", "hybrid"))


def knowledge_profile_for_filename(filename: str | None) -> KnowledgeIngestProfile:
    suffix = Path(filename or "").suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return _PROFILE_MARKDOWN
    if suffix in CSV_SUFFIXES:
        return _PROFILE_CSV
    if suffix in JSON_SUFFIXES:
        return _PROFILE_JSON
    if suffix in CODE_SUFFIXES:
        return _PROFILE_CODE
    if suffix in STRUCTURED_DOC_SUFFIXES:
        return _PROFILE_STRUCTURED
    return _PROFILE_TEXT


def _semantic_chunking() -> SemanticChunking:
    return SemanticChunking(
        embedder=_get_embedder(),
        chunk_size=CHUNK_SIZE,
        similarity_threshold=SEMANTIC_THRESHOLD,
    )


def _document_chunking() -> DocumentChunking:
    return DocumentChunking(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)


def _recursive_chunking() -> RecursiveChunking:
    return RecursiveChunking(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)


def reader_for_profile(
    profile: KnowledgeIngestProfile,
    filename: str | None = None,
) -> TextReader | MarkdownReader | CSVReader | JSONReader | PDFReader | DocxReader:
    suffix = Path(filename or "").suffix.lower()
    if profile.strategy == "markdown":
        return MarkdownReader(
            chunking_strategy=MarkdownChunking(
                chunk_size=CHUNK_SIZE,
                overlap=CHUNK_OVERLAP,
                split_on_headings=True,
            )
        )
    if profile.strategy == "csv_row":
        return CSVReader(chunking_strategy=RowChunking(skip_header=False))
    if profile.strategy == "json":
        return JSONReader(chunking_strategy=_recursive_chunking())
    if profile.strategy == "code":
        return TextReader(
            chunking_strategy=CodeChunking(
                chunk_size=CODE_CHUNK_SIZE,
                language="auto",
            )
        )
    if profile.strategy == "document":
        if suffix == ".pdf":
            return PDFReader(chunking_strategy=_document_chunking())
        if suffix == ".docx":
            return DocxReader(chunking_strategy=_document_chunking())
        return TextReader(chunking_strategy=_document_chunking())
    return TextReader(chunking_strategy=_semantic_chunking())


def reader_for_filename(
    filename: str | None,
) -> TextReader | MarkdownReader | CSVReader | JSONReader | PDFReader | DocxReader:
    return reader_for_profile(knowledge_profile_for_filename(filename), filename)


def pipeline_status() -> dict[str, Any]:
    profiles = [
        _PROFILE_MARKDOWN,
        _PROFILE_CSV,
        _PROFILE_JSON,
        _PROFILE_CODE,
        _PROFILE_STRUCTURED,
        _PROFILE_TEXT,
    ]
    return {
        "search_type": search_type_from_env().value,
        "vector_score_weight": VECTOR_SCORE_WEIGHT,
        "prefix_match": PREFIX_MATCH,
        "content_language": CONTENT_LANGUAGE,
        "supported_suffixes": sorted(SUPPORTED_FILE_SUFFIXES),
        "chunk_profiles": [
            {
                "label": profile.label,
                "strategy": profile.strategy,
                "reader": profile.reader,
                "suffixes": list(profile.suffixes),
                "description": profile.description,
            }
            for profile in profiles
        ],
        "semantic_threshold": SEMANTIC_THRESHOLD,
        "code_chunk_size": CODE_CHUNK_SIZE,
    }


@lru_cache(maxsize=4)
def get_knowledge_base(search_type: SearchType | None = None) -> Knowledge:
    embedder = _get_embedder()
    effective_search_type = search_type or search_type_from_env()
    vector_db = PgVector(
        table_name=PGVECTOR_TABLE,
        schema=POSTGRES_SCHEMA,
        db_url=postgres_sqlalchemy_url(),
        embedder=embedder,
        search_type=effective_search_type,
        distance=Distance.cosine,
        prefix_match=PREFIX_MATCH,
        vector_score_weight=VECTOR_SCORE_WEIGHT,
        content_language=CONTENT_LANGUAGE,
        reranker=_get_reranker(),
    )
    contents_db = get_knowledge_postgres_db()
    return Knowledge(
        name=KNOWLEDGE_NAME,
        description="Agno AIOS security knowledge base",
        vector_db=vector_db,
        contents_db=contents_db,
        max_results=max(TOP_K * RERANK_CANDIDATE_MULTIPLIER, RERANK_MIN_CANDIDATES)
        if RERANK_ENABLED
        else TOP_K,
        readers={
            "text": reader_for_profile(_PROFILE_TEXT),
            "markdown": reader_for_profile(_PROFILE_MARKDOWN),
            "csv": reader_for_profile(_PROFILE_CSV),
            "json": reader_for_profile(_PROFILE_JSON),
        },
    )


def _ensure_knowledge_storage() -> None:
    knowledge = get_knowledge_base()
    vector_db = cast(PgVector, knowledge.vector_db)
    vector_db.create()
    contents_db = get_knowledge_postgres_db()
    contents_db._get_table(table_type="knowledge", create_table_if_not_found=True)


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if value is not None and isinstance(key, str)
    }


def _metadata_value(metadata: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return str(value)
    return default


def _compact_metadata_value(value: Any) -> str:
    text = str(value)
    if len(text) <= DOCUMENT_METADATA_VALUE_MAX_LENGTH:
        return text
    return f"{text[: DOCUMENT_METADATA_VALUE_MAX_LENGTH - 3]}..."


def _document_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    compact_metadata: dict[str, str] = {}
    for key in DOCUMENT_METADATA_KEYS:
        value = metadata.get(key)
        if value is not None:
            compact_metadata[key] = _compact_metadata_value(value)

    for key, value in metadata.items():
        if len(compact_metadata) >= DOCUMENT_METADATA_MAX_ITEMS:
            break
        if key not in compact_metadata:
            compact_metadata[key] = _compact_metadata_value(value)

    return compact_metadata


def _format_timestamp(value: Any) -> str:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).isoformat()
    return str(value or "")


def _content_to_document(content: Any) -> dict[str, Any]:
    metadata = _safe_metadata(getattr(content, "metadata", None))
    created_at = getattr(content, "created_at", None)
    return {
        "id": str(getattr(content, "id", "") or ""),
        "title": str(getattr(content, "name", "") or "未命名知识"),
        "source": _metadata_value(metadata, "source", "file_path", default="manual"),
        "chunks": int(metadata.get("chunks") or 0),
        "created_at": _format_timestamp(created_at),
        "metadata": _document_metadata(metadata),
    }


def _chunk_counts_by_content_id() -> dict[str, int]:
    knowledge = get_knowledge_base()
    vector_db = cast(PgVector, knowledge.vector_db)
    table = vector_db.table
    try:
        with vector_db.Session() as sess, sess.begin():
            rows = sess.execute(
                select(table.c.content_id, func.count())
                .where(table.c.content_id.is_not(None))
                .group_by(table.c.content_id)
            ).fetchall()
    except Exception:
        return {}
    return {str(content_id): int(count) for content_id, count in rows if content_id}


def _result_from_document(document: Document) -> dict[str, Any]:
    metadata = _safe_metadata(document.meta_data)
    score = metadata.get("rerank_score") or metadata.get("similarity_score")
    if score is None:
        score_value = 0.0
    else:
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0
    return {
        "content": document.content,
        "score": round(score_value, 4),
        "distance": None,
        "doc_id": str(document.content_id or metadata.get("content_id") or ""),
        "title": str(document.name or metadata.get("title") or ""),
        "source": _metadata_value(metadata, "source", "file_path", default=""),
        "chunk_index": int(metadata.get("chunk") or metadata.get("chunk_index") or 0),
        "metadata": metadata,
    }


def _hydrate_content_ids(documents: list[Document]) -> None:
    ids = [document.id for document in documents if document.id]
    if not ids:
        return
    knowledge = get_knowledge_base()
    vector_db = cast(PgVector, knowledge.vector_db)
    table = vector_db.table
    try:
        with vector_db.Session() as sess, sess.begin():
            rows = sess.execute(
                select(table.c.id, table.c.content_id).where(table.c.id.in_(ids))
            ).fetchall()
    except Exception:
        return
    content_ids = {str(row_id): str(content_id) for row_id, content_id in rows if content_id}
    for document in documents:
        if document.id and document.id in content_ids:
            document.content_id = content_ids[document.id]
            document.meta_data["content_id"] = content_ids[document.id]


def _document_status(content_id: str) -> dict[str, Any] | None:
    content = get_knowledge_base().get_content_by_id(content_id)
    if content is None:
        return None
    return _content_to_document(content)


def add_text_document(
    title: str,
    content: str,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_title = title.strip() or "未命名知识"
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("知识内容不能为空")

    base_metadata = _safe_metadata(metadata)
    filename = str(base_metadata.get("file_name") or clean_title)
    profile = knowledge_profile_for_filename(filename)
    safe_metadata = {
        **base_metadata,
        "title": clean_title,
        "source": source.strip() or "manual",
        "file_type": Path(filename).suffix.lower() or "text",
        "chunk_strategy": profile.strategy,
        "reader": profile.reader,
        "input_mode": base_metadata.get("input_mode", "manual"),
    }
    knowledge = get_knowledge_base()
    with _knowledge_lock:
        _ensure_knowledge_storage()
        knowledge.insert(
            name=clean_title,
            description=source.strip() or "manual",
            text_content=clean_content,
            metadata=safe_metadata,
            reader=reader_for_profile(profile, filename),
            upsert=True,
            skip_if_exists=False,
        )
    contents, _ = knowledge.get_content(limit=1, page=1, sort_by="updated_at", sort_order="desc")
    for content_row in contents:
        if content_row.name == clean_title:
            return _content_to_document(content_row)
    raise RuntimeError("知识写入完成但未能读取内容登记记录")


def add_file_document(path: str, title: str | None = None) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    if file_path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
        supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
        raise ValueError(f"当前知识库支持的文件后缀: {supported}")

    clean_title = (title or file_path.stem).strip() or file_path.stem
    profile = knowledge_profile_for_filename(file_path.name)
    metadata = {
        "title": clean_title,
        "source": str(file_path),
        "file_path": str(file_path),
        "file_name": file_path.name,
        "file_type": file_path.suffix.lower(),
        "chunk_strategy": profile.strategy,
        "reader": profile.reader,
        "input_mode": "path",
    }
    reader = reader_for_profile(profile, file_path.name)
    knowledge = get_knowledge_base()
    with _knowledge_lock:
        _ensure_knowledge_storage()
        knowledge.insert(
            name=clean_title,
            description=str(file_path),
            path=str(file_path),
            metadata=metadata,
            reader=reader,
            upsert=True,
            skip_if_exists=False,
        )
    contents, _ = knowledge.get_content(limit=1, page=1, sort_by="updated_at", sort_order="desc")
    for content_row in contents:
        if content_row.name == clean_title:
            return _content_to_document(content_row)
    raise RuntimeError("知识写入完成但未能读取内容登记记录")


def list_documents() -> list[dict[str, Any]]:
    _ensure_knowledge_storage()
    contents, _ = get_knowledge_base().get_content(
        limit=500,
        page=1,
        sort_by="updated_at",
        sort_order="desc",
    )
    chunk_counts = _chunk_counts_by_content_id()
    documents = []
    for content in contents:
        document = _content_to_document(content)
        document["chunks"] = chunk_counts.get(document["id"], document["chunks"])
        documents.append(document)
    return documents


def delete_document(doc_id: str) -> bool:
    _ensure_knowledge_storage()
    if not _document_status(doc_id):
        return False
    with _knowledge_lock:
        get_knowledge_base().remove_content_by_id(doc_id)
    return True


def clear_knowledge_base() -> dict[str, Any]:
    _ensure_knowledge_storage()
    knowledge = get_knowledge_base()
    with _knowledge_lock:
        knowledge.remove_all_content()
    return {"documents": 0, "chunks": 0}


def search_documents(
    query: str,
    limit: int = 5,
    search_type: str | None = None,
) -> list[dict[str, Any]]:
    clean_query = query.strip()
    if not clean_query:
        return []
    effective_search_type = _search_type_from_name(search_type) if search_type else search_type_from_env()
    _ensure_knowledge_storage()
    knowledge = get_knowledge_base()
    retrieval_limit = (
        max(limit * RERANK_CANDIDATE_MULTIPLIER, RERANK_MIN_CANDIDATES)
        if RERANK_ENABLED
        else limit
    )
    documents = knowledge.search(
        clean_query,
        max_results=retrieval_limit,
        search_type=effective_search_type.value,
    )
    _hydrate_content_ids(documents)
    return [_result_from_document(document) for document in documents[:limit]]


def knowledge_status() -> dict[str, Any]:
    _ensure_knowledge_storage()
    knowledge = get_knowledge_base()
    docs = list_documents()
    vector_db = cast(PgVector, knowledge.vector_db)
    chunk_count = vector_db.get_count()
    device = _model_device()
    return {
        **pipeline_status(),
        "collection": PGVECTOR_TABLE,
        "storage": "pgvector",
        "database": postgres_label(POSTGRES_SCHEMA, PGVECTOR_TABLE),
        "contents_db": postgres_label(POSTGRES_SCHEMA, POSTGRES_KNOWLEDGE_TABLE),
        "postgres_schema": POSTGRES_SCHEMA,
        "documents": len(docs),
        "chunks": chunk_count,
        "embedding": EMBEDDING_MODEL,
        "embedding_dimensions": _embedding_dimensions or EMBEDDING_DIMENSIONS,
        "rerank": RERANK_MODEL,
        "device": device,
        "rerank_enabled": RERANK_ENABLED,
        "top_k": TOP_K,
        "retrieval_candidates": max(
            TOP_K * RERANK_CANDIDATE_MULTIPLIER,
            RERANK_MIN_CANDIDATES,
        )
        if RERANK_ENABLED
        else TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "cold_start_note": COLD_START_NOTE,
        "torch_runtime_ok": _load_torch() is not None,
    }
