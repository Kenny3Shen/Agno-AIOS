from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

CHROMA_PATH = Path(os.getenv("AGNO_KNOWLEDGE_CHROMA_PATH", "tmp/chroma"))
INDEX_FILE = Path(os.getenv("AGNO_KNOWLEDGE_INDEX_FILE", "tmp/knowledge_docs.json"))
COLLECTION_NAME = os.getenv("AGNO_KNOWLEDGE_COLLECTION", "security_knowledge")
EMBEDDING_DIMENSIONS = 256


class HashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Local lexical embeddings so the basic RAG path works without external keys."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: list[list[float]] = []
        for text in input:
            vector = [0.0] * self.dimensions
            for token in _tokens(str(text)):
                digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                bucket = int(digest[:8], 16) % self.dimensions
                vector[bucket] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            embeddings.append([value / norm for value in vector])
        return cast(Embeddings, embeddings)


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9._:/+-]{1,}|cve-\d{4}-\d{4,}", normalized)
    cjk = re.findall(r"[\u4e00-\u9fff]", normalized)
    cjk_bigrams = [normalized[i : i + 2] for i in range(max(len(normalized) - 1, 0))]
    return (
        tokens
        + cjk
        + [item for item in cjk_bigrams if re.search(r"[\u4e00-\u9fff]", item)]
    )


def _client() -> chromadb.ClientAPI:
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def _collection():
    return _client().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=cast(Any, HashEmbeddingFunction()),
        metadata={"description": "Agno AIOS security knowledge base"},
    )


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

    n_results = max(1, min(limit, count))
    result = collection.query(query_texts=[clean_query], n_results=n_results)
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
    return hits


def agno_knowledge_retriever(
    query: str,
    num_documents: int | None = None,
    **_: Any,
) -> list[dict[Any, Any] | str] | None:
    limit = num_documents or int(os.getenv("AGNO_KNOWLEDGE_TOP_K", "5"))
    return cast(list[dict[Any, Any] | str], search_documents(query, limit=limit))


def knowledge_status() -> dict[str, Any]:
    collection = _collection()
    docs = list_documents()
    return {
        "collection": COLLECTION_NAME,
        "storage": "chromadb",
        "path": str(CHROMA_PATH),
        "index_file": str(INDEX_FILE),
        "documents": len(docs),
        "chunks": collection.count(),
        "embedding": f"local-hash-{EMBEDDING_DIMENSIONS}",
    }
