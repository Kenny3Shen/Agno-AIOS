"""Knowledge ingest/update stage progress protocol."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

KnowledgeProgressStage = Literal["upload", "parse", "vectorize", "cleanup"]
KnowledgeProgressStatus = Literal["pending", "running", "completed", "failed", "skipped"]

KNOWLEDGE_PROGRESS_STAGES: tuple[KnowledgeProgressStage, ...] = (
    "upload",
    "parse",
    "vectorize",
    "cleanup",
)

STAGE_LABELS: dict[KnowledgeProgressStage, str] = {
    "upload": "上传",
    "parse": "解析",
    "vectorize": "向量化",
    "cleanup": "清理",
}

ProgressCallback = Callable[[Mapping[str, object]], Awaitable[None] | None]


def knowledge_progress_event(
    stage: KnowledgeProgressStage,
    status: KnowledgeProgressStatus,
    *,
    message: str | None = None,
    document: Mapping[str, object] | None = None,
    detail: Mapping[str, object] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "stage": stage,
        "status": status,
        "label": STAGE_LABELS[stage],
        "message": message or STAGE_LABELS[stage],
    }
    if document is not None:
        payload["document"] = dict(document)
    if detail is not None:
        payload["detail"] = dict(detail)
    if error is not None:
        payload["error"] = error
    return payload


def initial_progress_stages(
    *,
    include_upload: bool,
) -> list[dict[str, object]]:
    stages: list[dict[str, object]] = []
    for stage in KNOWLEDGE_PROGRESS_STAGES:
        if stage == "upload" and not include_upload:
            stages.append(
                knowledge_progress_event(
                    stage,
                    "skipped",
                    message="跳过",
                )
            )
            continue
        stages.append(
            knowledge_progress_event(
                stage,
                "pending",
            )
        )
    return stages


async def emit_progress(
    callback: ProgressCallback | None,
    stage: KnowledgeProgressStage,
    status: KnowledgeProgressStatus,
    *,
    message: str | None = None,
    document: Mapping[str, object] | None = None,
    detail: Mapping[str, object] | None = None,
    error: str | None = None,
) -> None:
    if callback is None:
        return
    event = knowledge_progress_event(
        stage,
        status,
        message=message,
        document=document,
        detail=detail,
        error=error,
    )
    result = callback(event)
    if isinstance(result, Awaitable):
        await result
