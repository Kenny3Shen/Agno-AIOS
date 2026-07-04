from __future__ import annotations

import importlib
import os
import threading
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from agno.knowledge.document import Document
from agno.knowledge.embedder import Embedder
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.reranker.base import Reranker
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
from api.services.knowledge_document_service import (
    content_to_document as _content_to_document,
    content_visible_to_owner as _content_visible_to_owner,
    owner_metadata as _owner_metadata,
    result_from_document as _result_from_document,
    safe_metadata as _safe_metadata,
)
from api.services.knowledge_ingest_service import (
    PROFILE_CSV as _PROFILE_CSV,
    PROFILE_JSON as _PROFILE_JSON,
    PROFILE_MARKDOWN as _PROFILE_MARKDOWN,
    PROFILE_TEXT as _PROFILE_TEXT,
    SUPPORTED_FILE_SUFFIXES,
    KnowledgeIngestProfile,
    KnowledgeReader,
    KnowledgeReaderConfig,
    pipeline_status as _ingest_pipeline_status,
    profile_for_filename as _profile_for_filename,
    reader_for_profile as _reader_for_profile,
)
from api.services.knowledge_runtime_service import (
    KnowledgeRuntimeDependencies,
    KnowledgeRuntimeSettings,
    build_knowledge_base,
    retrieval_candidate_limit,
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
_embedding_model: SentenceTransformer | None = None
_embedding_dimensions: int | None = None
_reranker_model: FlagReranker | None = None
_torch_module: Any | None = None
_torch_import_error: Exception | None = None
_embedding_model_lock = threading.Lock()
_reranker_model_lock = threading.Lock()
_knowledge_lock = threading.Lock()


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


def _reader_config(needs_embedder: bool) -> KnowledgeReaderConfig:
    return KnowledgeReaderConfig(
        embedder=_get_embedder() if needs_embedder else None,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        code_chunk_size=CODE_CHUNK_SIZE,
        semantic_threshold=SEMANTIC_THRESHOLD,
    )


def knowledge_profile_for_filename(filename: str | None) -> KnowledgeIngestProfile:
    return _profile_for_filename(filename)


def reader_for_profile(
    profile: KnowledgeIngestProfile,
    filename: str | None = None,
) -> KnowledgeReader:
    return _reader_for_profile(
        profile,
        _reader_config(needs_embedder=profile.strategy == "semantic"),
        filename,
    )


def reader_for_filename(
    filename: str | None,
) -> KnowledgeReader:
    profile = knowledge_profile_for_filename(filename)
    return _reader_for_profile(
        profile,
        _reader_config(needs_embedder=profile.strategy == "semantic"),
        filename,
    )


def pipeline_status() -> dict[str, Any]:
    return _ingest_pipeline_status(
        search_type=search_type_from_env().value,
        vector_score_weight=VECTOR_SCORE_WEIGHT,
        prefix_match=PREFIX_MATCH,
        content_language=CONTENT_LANGUAGE,
        semantic_threshold=SEMANTIC_THRESHOLD,
        code_chunk_size=CODE_CHUNK_SIZE,
    )


@lru_cache(maxsize=4)
def get_knowledge_base(search_type: SearchType | None = None) -> Knowledge:
    embedder = _get_embedder()
    effective_search_type = search_type or search_type_from_env()
    return build_knowledge_base(
        KnowledgeRuntimeSettings(
            name=KNOWLEDGE_NAME,
            description="Agno AIOS security knowledge base",
            pgvector_table=PGVECTOR_TABLE,
            postgres_schema=POSTGRES_SCHEMA,
            db_url=postgres_sqlalchemy_url(),
            prefix_match=PREFIX_MATCH,
            vector_score_weight=VECTOR_SCORE_WEIGHT,
            content_language=CONTENT_LANGUAGE,
            top_k=TOP_K,
            rerank_enabled=RERANK_ENABLED,
            rerank_candidate_multiplier=RERANK_CANDIDATE_MULTIPLIER,
            rerank_min_candidates=RERANK_MIN_CANDIDATES,
        ),
        KnowledgeRuntimeDependencies(
            embedder=embedder,
            reranker=_get_reranker(),
            contents_db=get_knowledge_postgres_db(),
        ),
        search_type=effective_search_type,
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


def _chunk_counts_by_content_id(owner_user_id: str | None = None) -> dict[str, int]:
    knowledge = get_knowledge_base()
    vector_db = cast(PgVector, knowledge.vector_db)
    table = vector_db.table
    try:
        with vector_db.Session() as sess, sess.begin():
            stmt = (
                select(table.c.content_id, func.count())
                .where(table.c.content_id.is_not(None))
            )
            owner_filter = _owner_metadata(owner_user_id)
            if owner_filter:
                stmt = stmt.where(table.c.meta_data.contains(owner_filter))
            rows = sess.execute(stmt.group_by(table.c.content_id)).fetchall()
    except Exception:
        return {}
    return {str(content_id): int(count) for content_id, count in rows if content_id}


def _chunk_count(owner_user_id: str | None = None) -> int:
    knowledge = get_knowledge_base()
    vector_db = cast(PgVector, knowledge.vector_db)
    owner_filter = _owner_metadata(owner_user_id)
    if not owner_filter:
        return int(vector_db.get_count())

    table = vector_db.table
    try:
        with vector_db.Session() as sess, sess.begin():
            count = sess.execute(
                select(func.count()).where(table.c.meta_data.contains(owner_filter))
            ).scalar()
    except Exception:
        return 0
    return int(count or 0)


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


@dataclass(frozen=True)
class KnowledgeBaseLifecycleDependencies:
    get_knowledge_base: Callable[[SearchType | None], Any] | None = None
    ensure_storage: Callable[[], None] | None = None
    chunk_counts_by_content_id: Callable[[str | None], dict[str, int]] | None = None
    chunk_count: Callable[[str | None], int] | None = None
    hydrate_content_ids: Callable[[list[Document]], None] | None = None
    lock: Any = _knowledge_lock


class KnowledgeBaseLifecycle:
    """Knowledge Document lifecycle, retrieval and status behind one interface."""

    def __init__(
        self,
        dependencies: KnowledgeBaseLifecycleDependencies | None = None,
    ) -> None:
        self.dependencies = dependencies or KnowledgeBaseLifecycleDependencies()

    def _knowledge(self, search_type: SearchType | None = None) -> Any:
        if self.dependencies.get_knowledge_base is not None:
            return self.dependencies.get_knowledge_base(search_type)
        return get_knowledge_base(search_type)

    def _ensure_storage(self) -> None:
        if self.dependencies.ensure_storage is not None:
            self.dependencies.ensure_storage()
            return
        _ensure_knowledge_storage()

    def _chunk_counts_by_content_id(self, owner_user_id: str | None) -> dict[str, int]:
        if self.dependencies.chunk_counts_by_content_id is not None:
            return self.dependencies.chunk_counts_by_content_id(owner_user_id)
        return _chunk_counts_by_content_id(owner_user_id)

    def _chunk_count(self, owner_user_id: str | None) -> int:
        if self.dependencies.chunk_count is not None:
            return self.dependencies.chunk_count(owner_user_id)
        return _chunk_count(owner_user_id)

    def _hydrate_content_ids(self, documents: list[Document]) -> None:
        if self.dependencies.hydrate_content_ids is not None:
            self.dependencies.hydrate_content_ids(documents)
            return
        _hydrate_content_ids(documents)

    def add_text_document(
        self,
        title: str,
        content: str,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
        owner_user_id: str | None = None,
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
            **_owner_metadata(owner_user_id),
            "title": clean_title,
            "source": source.strip() or "manual",
            "file_type": Path(filename).suffix.lower() or "text",
            "chunk_strategy": profile.strategy,
            "reader": profile.reader,
            "input_mode": base_metadata.get("input_mode", "manual"),
        }
        knowledge = self._knowledge()
        with self.dependencies.lock:
            self._ensure_storage()
            knowledge.insert(
                name=clean_title,
                description=source.strip() or "manual",
                text_content=clean_content,
                metadata=safe_metadata,
                reader=reader_for_profile(profile, filename),
                upsert=True,
                skip_if_exists=False,
            )
        contents, _ = knowledge.get_content(
            limit=1,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        for content_row in contents:
            if content_row.name == clean_title:
                return _content_to_document(content_row)
        raise RuntimeError("知识写入完成但未能读取内容登记记录")

    def add_file_document(
        self,
        path: str,
        title: str | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        if file_path.suffix.lower() not in SUPPORTED_FILE_SUFFIXES:
            supported = ", ".join(SUPPORTED_FILE_SUFFIXES)
            raise ValueError(f"当前知识库支持的文件后缀: {supported}")

        clean_title = (title or file_path.stem).strip() or file_path.stem
        profile = knowledge_profile_for_filename(file_path.name)
        metadata = {
            **_owner_metadata(owner_user_id),
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
        knowledge = self._knowledge()
        with self.dependencies.lock:
            self._ensure_storage()
            knowledge.insert(
                name=clean_title,
                description=str(file_path),
                path=str(file_path),
                metadata=metadata,
                reader=reader,
                upsert=True,
                skip_if_exists=False,
            )
        contents, _ = knowledge.get_content(
            limit=1,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        for content_row in contents:
            if content_row.name == clean_title:
                return _content_to_document(content_row)
        raise RuntimeError("知识写入完成但未能读取内容登记记录")

    def list_documents(self, owner_user_id: str | None = None) -> list[dict[str, Any]]:
        self._ensure_storage()
        contents, _ = self._knowledge().get_content(
            limit=500,
            page=1,
            sort_by="updated_at",
            sort_order="desc",
        )
        chunk_counts = self._chunk_counts_by_content_id(owner_user_id)
        documents = []
        for content in contents:
            if not _content_visible_to_owner(content, owner_user_id):
                continue
            document = _content_to_document(content)
            document["chunks"] = chunk_counts.get(document["id"], document["chunks"])
            documents.append(document)
        return documents

    def delete_document(
        self,
        doc_id: str,
        owner_user_id: str | None = None,
    ) -> bool:
        self._ensure_storage()
        knowledge = self._knowledge()
        content = knowledge.get_content_by_id(doc_id)
        if content is None or not _content_visible_to_owner(content, owner_user_id):
            return False
        with self.dependencies.lock:
            knowledge.remove_content_by_id(doc_id)
        return True

    def clear_knowledge_base(
        self,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_storage()
        knowledge = self._knowledge()
        documents = self.list_documents(owner_user_id=owner_user_id)
        with self.dependencies.lock:
            if owner_user_id:
                for document in documents:
                    knowledge.remove_content_by_id(document["id"])
            else:
                knowledge.remove_all_content()
        return {"documents": 0, "chunks": 0}

    def search_documents(
        self,
        query: str,
        limit: int = 5,
        search_type: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clean_query = query.strip()
        if not clean_query:
            return []
        effective_search_type = (
            _search_type_from_name(search_type) if search_type else search_type_from_env()
        )
        self._ensure_storage()
        knowledge = self._knowledge()
        retrieval_limit = retrieval_candidate_limit(
            limit,
            rerank_enabled=RERANK_ENABLED,
            rerank_candidate_multiplier=RERANK_CANDIDATE_MULTIPLIER,
            rerank_min_candidates=RERANK_MIN_CANDIDATES,
        )
        documents = knowledge.search(
            clean_query,
            max_results=retrieval_limit,
            filters=_owner_metadata(owner_user_id) or None,
            search_type=effective_search_type.value,
        )
        self._hydrate_content_ids(documents)
        return [_result_from_document(document) for document in documents[:limit]]

    def knowledge_status(self, owner_user_id: str | None = None) -> dict[str, Any]:
        self._ensure_storage()
        docs = self.list_documents(owner_user_id=owner_user_id)
        chunk_count = self._chunk_count(owner_user_id)
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
            "retrieval_candidates": retrieval_candidate_limit(
                TOP_K,
                rerank_enabled=RERANK_ENABLED,
                rerank_candidate_multiplier=RERANK_CANDIDATE_MULTIPLIER,
                rerank_min_candidates=RERANK_MIN_CANDIDATES,
            ),
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "cold_start_note": COLD_START_NOTE,
            "torch_runtime_ok": _load_torch() is not None,
        }


DEFAULT_KNOWLEDGE_BASE_LIFECYCLE = KnowledgeBaseLifecycle()


def get_knowledge_base_lifecycle() -> KnowledgeBaseLifecycle:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE


def add_text_document(
    title: str,
    content: str,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.add_text_document(
        title,
        content,
        source=source,
        metadata=metadata,
        owner_user_id=owner_user_id,
    )


def add_file_document(
    path: str,
    title: str | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.add_file_document(
        path,
        title=title,
        owner_user_id=owner_user_id,
    )


def list_documents(owner_user_id: str | None = None) -> list[dict[str, Any]]:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.list_documents(owner_user_id=owner_user_id)


def delete_document(doc_id: str, owner_user_id: str | None = None) -> bool:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.delete_document(
        doc_id,
        owner_user_id=owner_user_id,
    )


def clear_knowledge_base(owner_user_id: str | None = None) -> dict[str, Any]:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.clear_knowledge_base(
        owner_user_id=owner_user_id,
    )


def search_documents(
    query: str,
    limit: int = 5,
    search_type: str | None = None,
    owner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.search_documents(
        query,
        limit=limit,
        search_type=search_type,
        owner_user_id=owner_user_id,
    )


def knowledge_status(owner_user_id: str | None = None) -> dict[str, Any]:
    return DEFAULT_KNOWLEDGE_BASE_LIFECYCLE.knowledge_status(
        owner_user_id=owner_user_id,
    )
