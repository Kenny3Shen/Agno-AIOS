from datetime import UTC, datetime
from collections.abc import Mapping
from typing import Protocol, TypedDict

from api.auth.visibility import (
    metadata_visibility,
    normalize_visibility,
    visibility_metadata,
)

DOCUMENT_METADATA_KEYS = (
    "visibility",
    "owner_user_id",
    "user_id",
    "status",
    "status_message",
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
COMPLETED_STATUSES = {"completed", "complete", "ready", "done", "success", "succeeded"}


class SearchDocumentLike(Protocol):
    content: object
    content_id: object
    name: object
    meta_data: Mapping[str, object] | None


class KnowledgeDocumentPayload(TypedDict):
    id: str
    title: str
    source: str
    chunks: int
    created_at: str
    status: str
    status_message: str
    type: str
    size: object
    visibility: str
    owner_user_id: str
    metadata: dict[str, str]


class KnowledgeSearchResultPayload(TypedDict):
    content: str
    score: float
    distance: None
    doc_id: str
    title: str
    source: str
    chunk_index: int
    metadata: dict[str, object]


def safe_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if value is not None and isinstance(key, str)
    }


def metadata_value(metadata: Mapping[str, object], *keys: str, default: str = "") -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return str(value)
    return default


def compact_metadata_value(value: object) -> str:
    text = str(value)
    if len(text) <= DOCUMENT_METADATA_VALUE_MAX_LENGTH:
        return text
    return f"{text[: DOCUMENT_METADATA_VALUE_MAX_LENGTH - 3]}..."


def int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str | bytes | bytearray):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def float_value(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str | bytes | bytearray):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def document_metadata(metadata: Mapping[str, object]) -> dict[str, str]:
    compact_metadata: dict[str, str] = {}
    for key in DOCUMENT_METADATA_KEYS:
        value = metadata.get(key)
        if value is not None:
            compact_metadata[key] = compact_metadata_value(value)

    for key, value in metadata.items():
        if len(compact_metadata) >= DOCUMENT_METADATA_MAX_ITEMS:
            break
        if key not in compact_metadata:
            compact_metadata[key] = compact_metadata_value(value)

    return compact_metadata


def owner_metadata(
    owner_user_id: str | None,
    visibility: str = "private",
) -> dict[str, str]:
    clean_owner = (owner_user_id or "").strip()
    if not clean_owner:
        return {"visibility": normalize_visibility(visibility)}
    return visibility_metadata(visibility, clean_owner)


def metadata_owner_user_id(metadata: Mapping[str, object]) -> str:
    return str(metadata.get("owner_user_id") or metadata.get("user_id") or "").strip()


def content_visible_to_owner(content: object, owner_user_id: str | None) -> bool:
    clean_owner = (owner_user_id or "").strip()
    if not clean_owner:
        return True
    metadata = safe_metadata(getattr(content, "metadata", None))
    if metadata_visibility(metadata) == "public":
        return True
    return metadata_owner_user_id(metadata) == clean_owner


def format_timestamp(value: object) -> str:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).isoformat()
    return str(value or "")


def content_status(content: object, metadata: Mapping[str, object]) -> str:
    status = getattr(content, "status", None) or metadata.get("status") or metadata.get("embedding_status")
    value = getattr(status, "value", status)
    return str(value or "").strip().lower()


def content_chunk_count(content: object, metadata: Mapping[str, object]) -> int:
    chunks = int_value(metadata.get("chunks"), 0)
    if chunks > 0:
        return chunks
    if content_status(content, metadata) in COMPLETED_STATUSES:
        return 1
    return 0


def content_to_document(content: object) -> KnowledgeDocumentPayload:
    metadata = safe_metadata(getattr(content, "metadata", None))
    created_at = getattr(content, "created_at", None)
    status = content_status(content, metadata)
    status_message = str(getattr(content, "status_message", "") or metadata.get("status_message") or "")
    content_type = str(getattr(content, "type", "") or metadata.get("file_type") or "")
    size = getattr(content, "size", None) or metadata.get("file_size")
    return {
        "id": str(getattr(content, "id", "") or ""),
        "title": str(getattr(content, "name", "") or "未命名知识"),
        "source": metadata_value(metadata, "source", "file_path", default="manual"),
        "chunks": content_chunk_count(content, metadata),
        "created_at": format_timestamp(created_at),
        "status": status,
        "status_message": status_message,
        "type": content_type,
        "size": size,
        "visibility": metadata_visibility(metadata),
        "owner_user_id": metadata_owner_user_id(metadata),
        "metadata": document_metadata(metadata),
    }


def result_from_document(document: SearchDocumentLike) -> KnowledgeSearchResultPayload:
    metadata = safe_metadata(document.meta_data)
    score = metadata.get("rerank_score") or metadata.get("similarity_score")
    score_value = float_value(score)
    return {
        "content": str(document.content or ""),
        "score": round(score_value, 4),
        "distance": None,
        "doc_id": str(document.content_id or metadata.get("content_id") or ""),
        "title": str(document.name or metadata.get("title") or ""),
        "source": metadata_value(metadata, "source", "file_path", default=""),
        "chunk_index": int_value(metadata.get("chunk") or metadata.get("chunk_index")),
        "metadata": metadata,
    }
