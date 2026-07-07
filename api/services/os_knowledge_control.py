from __future__ import annotations

from typing import Any

from api.services.knowledge_service import knowledge_status_async
from api.services.os_control_identity import owner_user_id
from api.services.os_control_payloads import OsPayload, metric, payload, record


async def get_knowledge_payload(actor: Any | None = None) -> OsPayload:
    status = await knowledge_status_async(owner_user_id=owner_user_id(actor))
    docs = int(status.get("documents") or 0)
    chunks = int(status.get("chunks") or 0)
    records = [
        record(
            record_id="knowledge:pgvector",
            title="PgVector Knowledge",
            subtitle=str(status.get("collection") or "vector collection"),
            status="ready" if chunks else "empty",
            meta={
                "chunks": chunks,
                "database": status.get("database"),
                "search_type": status.get("search_type"),
            },
        ),
        record(
            record_id="knowledge:contents",
            title="Knowledge Contents",
            subtitle=str(status.get("contents_db") or "contents catalog"),
            status="ready" if docs else "empty",
            meta={"documents": docs, "schema": status.get("postgres_schema")},
        ),
    ]
    return payload(
        module="knowledge",
        title="Knowledge",
        description="知识库内容表与向量表轻量状态。",
        metrics=[
            metric("Documents", docs, "content rows", "blue"),
            metric("Chunks", chunks, "vector rows", "green"),
        ],
        records=records,
    )
