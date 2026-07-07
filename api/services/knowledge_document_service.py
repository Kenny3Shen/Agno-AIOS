from datetime import UTC, datetime
from typing import Any

from api.auth.visibility import (
    metadata_visibility,
    normalize_visibility,
    visibility_metadata,
)

DOCUMENT_METADATA_KEYS = (
    "visibility",
    "owner_user_id",
    "user_id",
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


def safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if value is not None and isinstance(key, str)
    }


def metadata_value(metadata: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return str(value)
    return default


def compact_metadata_value(value: Any) -> str:
    text = str(value)
    if len(text) <= DOCUMENT_METADATA_VALUE_MAX_LENGTH:
        return text
    return f"{text[: DOCUMENT_METADATA_VALUE_MAX_LENGTH - 3]}..."


def document_metadata(metadata: dict[str, Any]) -> dict[str, str]:
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


def metadata_owner_user_id(metadata: dict[str, Any]) -> str:
    return str(metadata.get("owner_user_id") or metadata.get("user_id") or "").strip()


def content_visible_to_owner(content: Any, owner_user_id: str | None) -> bool:
    clean_owner = (owner_user_id or "").strip()
    if not clean_owner:
        return True
    metadata = safe_metadata(getattr(content, "metadata", None))
    if metadata_visibility(metadata) == "public":
        return True
    return metadata_owner_user_id(metadata) == clean_owner


def format_timestamp(value: Any) -> str:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).isoformat()
    return str(value or "")


def content_to_document(content: Any) -> dict[str, Any]:
    metadata = safe_metadata(getattr(content, "metadata", None))
    created_at = getattr(content, "created_at", None)
    return {
        "id": str(getattr(content, "id", "") or ""),
        "title": str(getattr(content, "name", "") or "未命名知识"),
        "source": metadata_value(metadata, "source", "file_path", default="manual"),
        "chunks": int(metadata.get("chunks") or 0),
        "created_at": format_timestamp(created_at),
        "visibility": metadata_visibility(metadata),
        "owner_user_id": metadata_owner_user_id(metadata),
        "metadata": document_metadata(metadata),
    }


def result_from_document(document: Any) -> dict[str, Any]:
    metadata = safe_metadata(document.meta_data)
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
        "source": metadata_value(metadata, "source", "file_path", default=""),
        "chunk_index": int(metadata.get("chunk") or metadata.get("chunk_index") or 0),
        "metadata": metadata,
    }
