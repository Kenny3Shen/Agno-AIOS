from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

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


CHROMA_PATH = Path(os.getenv("AGNO_KNOWLEDGE_CHROMA_PATH", "tmp/chroma"))
INDEX_FILE = Path(os.getenv("AGNO_KNOWLEDGE_INDEX_FILE", "tmp/knowledge_docs.json"))
COLLECTION_NAME = os.getenv("AGNO_KNOWLEDGE_COLLECTION", "security_knowledge_bge")
EMBEDDING_DIMENSIONS = 512
EMBEDDING_MODEL = os.getenv("AGNO_KNOWLEDGE_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
RERANK_MODEL = os.getenv("AGNO_KNOWLEDGE_RERANK_MODEL", "BAAI/bge-reranker-base")
BGE_QUERY_PROMPT = os.getenv(
    "AGNO_KNOWLEDGE_QUERY_PROMPT", "为这个句子生成表示以用于检索相关文章："
)
RERANK_ENABLED = os.getenv("AGNO_KNOWLEDGE_RERANK_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
RERANK_CANDIDATE_MULTIPLIER = max(
    1,
    _env_int("AGNO_KNOWLEDGE_RERANK_CANDIDATE_MULTIPLIER", 3),
)
RERANK_MIN_CANDIDATES = max(
    1,
    _env_int("AGNO_KNOWLEDGE_RERANK_MIN_CANDIDATES", 10),
)
MODEL_DEVICE = os.getenv("AGNO_KNOWLEDGE_DEVICE", "auto").strip().lower() or "auto"

# ── lazy-loaded model singletons ──────────────────────────────────────────

_embedding_model: SentenceTransformer | None = None
_reranker_model: FlagReranker | None = None
_torch_module: Any | None = None
_torch_import_error: Exception | None = None


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
        raise _torch_runtime_error() from exc
    return cast(type[SentenceTransformer], module.SentenceTransformer)


def _flag_reranker_cls() -> type[FlagReranker]:
    try:
        module = importlib.import_module("FlagEmbedding")
    except Exception as exc:
        raise _torch_runtime_error() from exc
    return cast(type[FlagReranker], module.FlagReranker)


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        if _load_torch() is None:
            raise _torch_runtime_error()
        sentence_transformer_cls = _sentence_transformer_cls()
        _embedding_model = sentence_transformer_cls(
            EMBEDDING_MODEL,
            device=_model_device(),
        )
    return _embedding_model


def _patch_tokenizer_prepare_for_model(
    tokenizer: Any,
    type_vocab_size: int = 1,
) -> None:
    """Monkey-patch ``prepare_for_model`` onto the tokenizer when it is missing.

    ``transformers`` >= 5.0 removed ``prepare_for_model``,
    ``build_inputs_with_special_tokens`` and
    ``create_token_type_ids_from_sequences`` from the tokenizer API, but
    ``FlagEmbedding`` (<= 1.4.0) still calls ``prepare_for_model`` internally.
    This shim reconstructs the packed sequence manually so the reranker works
    without downgrading transformers.

    .. seealso:: :gh-issue:`FlagOpen/FlagEmbedding#1561`
    """
    if hasattr(tokenizer, "prepare_for_model"):
        return

    import types

    try:
        from transformers.tokenization_utils_base import BatchEncoding
    except ImportError:
        return  # fallback – the call will still fail with the original error

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
        ids_list: list[int] = list(ids)
        pair_list: list[int] = list(pair_ids) if pair_ids else []
        len_ids = len(ids_list)
        len_pair = len(pair_list)
        num_special = self.num_special_tokens_to_add(pair=pair)

        # ── truncation ──────────────────────────────────────────────
        if max_length is not None and (len_ids + len_pair + num_special) > max_length:
            if truncation == "only_second":
                max_pair = max_length - len_ids - num_special
                if max_pair <= 0:
                    pair_list = []
                elif max_pair < len_pair:
                    pair_list = pair_list[:max_pair]
            elif truncation == "only_first":
                max_first = max_length - len_pair - num_special
                if max_first <= 0:
                    ids_list = []
                elif max_first < len_ids:
                    ids_list = ids_list[:max_first]
            elif truncation == "longest_first":
                while (len(ids_list) + len(pair_list) + num_special) > max_length:
                    if len(ids_list) > len(pair_list):
                        ids_list.pop()
                    elif pair_list:
                        pair_list.pop()
                    else:
                        ids_list.pop()

        # ── build packed sequence ───────────────────────────────────
        bos = int(self.cls_token_id or self.bos_token_id)
        eos = int(self.sep_token_id or self.eos_token_id)
        sep = int(self.sep_token_id)

        # number of <sep> tokens inserted *between* the two sequences
        between_seps = num_special - 2  # 1 for BERT, 2 for XLMRoberta

        if pair:
            sequence = [bos, *ids_list, *([sep] * between_seps), *pair_list, eos]
        else:
            sequence = [bos, *ids_list, eos]

        result: dict[str, list[int]] = {"input_ids": sequence}

        # ── token type ids ──────────────────────────────────────────
        # Only include segment-aware token_type_ids when the embedding
        # table actually supports it (type_vocab_size > 1).  For
        # RoBERTa / XLMRoberta models type_vocab_size == 1 and passing
        # any non-zero id would trigger an IndexError.
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
    if _reranker_model is None:
        if _load_torch() is None:
            raise _torch_runtime_error()
        use_fp16 = os.getenv("AGNO_KNOWLEDGE_RERANK_USE_FP16", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
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
        _patch_tokenizer_prepare_for_model(_reranker_model.tokenizer, type_vocab_size=tv_size)
    return _reranker_model


class BGEZhEmbeddingFunction(EmbeddingFunction[Documents]):
    """BGE-small-zh-v1.5 semantic embeddings for ChromaDB documents.

    Sentences are encoded *without* the query instruction prefix \u2014 the prefix
    is added only when encoding queries at search time via ``search_documents``.
    """

    def __call__(self, input: Documents) -> Embeddings:
        model = _get_embedding_model()
        embeddings = model.encode(
            list(input),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return cast(Embeddings, embeddings.tolist())


def _client() -> chromadb.ClientAPI:
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def _collection():
    return _client().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=cast(Any, BGEZhEmbeddingFunction()),
        metadata={"description": "Agno AIOS security knowledge base"},
    )


def _encode_query(query: str) -> list[float]:
    model = _get_embedding_model()
    query_text = f"{BGE_QUERY_PROMPT}{query}"
    embedding = model.encode(
        [query_text],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return cast(list[float], embedding[0].tolist())


def _load_index() -> dict[str, dict[str, Any]]:
    if not INDEX_FILE.exists():
        return {}
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_index(index: dict[str, dict[str, Any]]) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in (metadata or {}).items()
        if value is not None and isinstance(key, str)
    }


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 160) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text.strip()]:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max_chars - overlap :]
    if current:
        chunks.append(current)
    return chunks


def import_knowledge_document(
    doc: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Import an existing document and chunks into ChromaDB, preserving IDs."""
    doc_id = str(doc["id"])
    title = str(doc.get("title") or "未命名知识")
    source = str(doc.get("source") or "manual")
    created_at = str(doc.get("created_at") or datetime.now(UTC).isoformat())
    metadata = _safe_metadata(cast(dict[str, Any], doc.get("metadata") or {}))
    ordered_chunks = sorted(chunks, key=lambda item: int(item.get("chunk_index") or 0))

    existing = _load_index()
    collection = _collection()
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception:
        pass
    existing.pop(doc_id, None)

    if ordered_chunks:
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for index, chunk in enumerate(ordered_chunks):
            content = str(chunk.get("content") or "")
            chunk_index = int(chunk.get("chunk_index") or index)
            chunk_id = str(chunk.get("id") or f"{doc_id}:{chunk_index}")
            chunk_metadata = _safe_metadata(
                cast(dict[str, Any], chunk.get("metadata") or {})
            )
            ids.append(chunk_id)
            documents.append(content)
            metadatas.append(
                {
                    **metadata,
                    **chunk_metadata,
                    "doc_id": doc_id,
                    "title": title,
                    "source": source,
                    "chunk_index": chunk_index,
                    "created_at": str(chunk.get("created_at") or created_at),
                }
            )
        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    imported_doc = {
        "id": doc_id,
        "title": title,
        "source": source,
        "chunks": len(ordered_chunks),
        "created_at": created_at,
        "metadata": metadata,
    }
    existing[doc_id] = imported_doc
    _save_index(existing)
    return imported_doc


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

    doc_id = hashlib.sha256(
        f"{clean_title}\n{source}\n{clean_content}".encode("utf-8")
    ).hexdigest()[:16]
    chunks = _chunk_text(clean_content)
    now = datetime.now(UTC).isoformat()
    safe_metadata = _safe_metadata(metadata)
    chunk_rows = [
        {
            "id": f"{doc_id}:{index}",
            "content": chunk,
            "chunk_index": index,
            "metadata": {
                "doc_id": doc_id,
                "title": clean_title,
                "source": source,
                "chunk_index": str(index),
                "created_at": now,
                **safe_metadata,
            },
            "created_at": now,
        }
        for index, chunk in enumerate(chunks)
    ]
    return import_knowledge_document(
        {
            "id": doc_id,
            "title": clean_title,
            "source": source,
            "created_at": now,
            "metadata": safe_metadata,
        },
        chunk_rows,
    )


def add_file_document(path: str, title: str | None = None) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    if file_path.suffix.lower() not in {".txt", ".md", ".markdown", ".log"}:
        raise ValueError("当前基础知识库仅支持 txt/md/markdown/log 文本文件")
    content = file_path.read_text(encoding="utf-8")
    return add_text_document(
        title=title or file_path.stem,
        content=content,
        source=str(file_path),
        metadata={"file_name": file_path.name},
    )


def list_documents() -> list[dict[str, Any]]:
    docs = list(_load_index().values())
    return sorted(docs, key=lambda item: item.get("created_at", ""), reverse=True)


def delete_document(doc_id: str) -> bool:
    index = _load_index()
    if doc_id not in index:
        return False
    _collection().delete(where={"doc_id": doc_id})
    index.pop(doc_id, None)
    _save_index(index)
    return True


def clear_knowledge_base() -> dict[str, Any]:
    client = _client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    _save_index({})
    _collection()
    return {"documents": 0, "chunks": 0}


def search_documents(query: str, limit: int = 5) -> list[dict[str, Any]]:
    clean_query = query.strip()
    if not clean_query:
        return []
    collection = _collection()
    count = collection.count()
    if count == 0:
        return []

    # First stage: retrieve more semantic candidates than the final answer needs.
    retrieval_limit = max(limit * RERANK_CANDIDATE_MULTIPLIER, RERANK_MIN_CANDIDATES)
    n_results = max(1, min(retrieval_limit, count))

    result = collection.query(
        query_embeddings=[_encode_query(clean_query)],
        n_results=n_results,
    )
    documents = result.get("documents") or [[]]
    metadatas = result.get("metadatas") or [[]]
    distances = result.get("distances") or [[]]

    hits: list[dict[str, Any]] = []
    for content, metadata, distance in zip(
        documents[0], metadatas[0], distances[0], strict=False
    ):
        distance_value = float(distance)
        metadata = metadata or {}
        hits.append(
            {
                "content": content,
                "score": round(1 / (1 + distance_value), 4),
                "distance": round(distance_value, 4),
                "doc_id": metadata.get("doc_id", ""),
                "title": metadata.get("title", ""),
                "source": metadata.get("source", ""),
                "chunk_index": metadata.get("chunk_index", 0),
            }
        )

    # Second stage: rerank retrieved candidates before returning Agent context.
    if RERANK_ENABLED and len(hits) > limit:
        reranker = _get_reranker_model()
        pairs: list[tuple[str, str]] = [
            (clean_query, str(hit["content"])) for hit in hits
        ]
        raw_scores = reranker.compute_score(
            pairs,
            normalize=True,
        )
        rerank_scores = (
            [float(raw_scores)]
            if isinstance(raw_scores, int | float)
            else [float(score) for score in raw_scores]
        )
        for hit, rerank_score in zip(hits, rerank_scores, strict=False):
            hit["rerank_score"] = round(float(rerank_score), 4)
        hits.sort(key=lambda h: h.get("rerank_score", 0.0), reverse=True)

    return hits[:limit]


def agno_knowledge_retriever(
    agent: Any = None,
    query: str | None = None,
    num_documents: int | None = None,
    **_: Any,
) -> list[dict[Any, Any] | str] | None:
    if query is None and isinstance(agent, str):
        query = agent
    if not query:
        return []
    limit = num_documents or _env_int("AGNO_KNOWLEDGE_TOP_K", 5)
    return cast(list[dict[Any, Any] | str], search_documents(query, limit=limit))


def knowledge_status() -> dict[str, Any]:
    collection = _collection()
    docs = list_documents()
    device = _model_device()
    return {
        "collection": COLLECTION_NAME,
        "storage": "chromadb",
        "path": str(CHROMA_PATH),
        "index_file": str(INDEX_FILE),
        "documents": len(docs),
        "chunks": collection.count(),
        "embedding": EMBEDDING_MODEL,
        "rerank": RERANK_MODEL,
        "device": device,
        "rerank_enabled": RERANK_ENABLED,
        "retrieval_candidates": max(
            _env_int("AGNO_KNOWLEDGE_TOP_K", 5) * RERANK_CANDIDATE_MULTIPLIER,
            RERANK_MIN_CANDIDATES,
        ),
    }
