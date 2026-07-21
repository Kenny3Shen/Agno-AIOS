from time import perf_counter
from typing import Any, cast

from agno.models.message import Message
from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel

from api.auth.models import User
from api.auth.claims import ADMIN_SCOPE
from api.auth.scopes import require_scope
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.model_config_service import (
    ModelConfig,
    ModelConfigUpdate,
    load_model_config,
    public_model_config,
    save_model_config,
)
from api.services.model_factory import build_agno_model
from api.auth.claims import actor_id
from api.services.chat_settings_service import get_chat_settings, update_chat_settings
from api.services.knowledge_rag_settings_service import (
    get_knowledge_rag_settings,
    update_knowledge_rag_settings,
)
from api.services.guardrail_settings_service import (
    get_guardrail_settings,
    update_guardrail_settings,
)
from api.services.user_notification_settings_service import (
    read_user_notification_settings,
    update_user_feishu_webhook,
)

router = APIRouter(prefix="/api", tags=["Settings"])

class ChatSettingsUpdate(BaseModel):
    show_raw_reasoning: bool | None = None
    show_raw_tool_io: bool | None = None
    show_thought_chain: bool | None = None
    memory_enabled: bool | None = None
    # Agno runtime knobs (history / session summary / tools / memory mode)
    num_history_runs: int | None = None
    session_summaries_enabled: bool | None = None
    add_datetime_to_context: bool | None = None
    max_tool_calls_from_history: int | None = None
    default_tool_call_limit: int | None = None
    enable_agentic_memory: bool | None = None
    markdown: bool | None = None
    # Memory P0: tool-content capture + automatic prune job knobs
    memory_tool_content_enabled: bool | None = None
    memory_prune_enabled: bool | None = None
    memory_prune_retention_days: int | None = None
    memory_prune_top_k: int | None = None
    # Memory P1: inject-side ranking before Agno system-prompt dump
    memory_inject_enabled: bool | None = None
    memory_inject_top_k: int | None = None
    memory_inject_max_chars: int | None = None
    memory_inject_window_days: int | None = None
    memory_inject_dedupe_topics: bool | None = None



class KnowledgeRagSettingsUpdate(BaseModel):
    search_type: str | None = None
    top_k: int | None = None
    vector_score_weight: float | None = None
    similarity_threshold: float | None = None
    content_language: str | None = None
    prefix_match: bool | None = None
    rerank_enabled: bool | None = None
    rerank_candidate_multiplier: int | None = None
    rerank_min_candidates: int | None = None


class GuardrailSettingsUpdate(BaseModel):
    """Global Agno input guardrails (no OpenAI Moderation)."""

    enabled: bool | None = None
    pii_enabled: bool | None = None
    pii_mask: bool | None = None
    pii_check_email: bool | None = None
    pii_check_phone: bool | None = None
    prompt_injection_enabled: bool | None = None


class UserNotificationSettingsUpdate(BaseModel):
    """Per-user notification prefs. Omit field to leave unchanged; empty string clears."""

    feishu_webhook_url: str | None = None


class ModelConnectivityTestResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    message: str
    status_code: int | None = None


async def _resolve_model_secret(model: ModelConfig) -> dict[str, Any]:
    data = model.model_dump()
    if "*" not in data.get("api_key", ""):
        return data

    data["api_key"] = ""
    saved_config = await load_model_config()
    for saved in saved_config.get("models", []):
        if isinstance(saved, dict) and saved.get("id") == model.id:
            data["api_key"] = str(saved.get("api_key") or "")
            break
    return data


def _validate_test_model(model: dict[str, Any]) -> None:
    required = [("API Key", "api_key"), ("Model ID", "model_id")]
    if model.get("provider") == "openai-compatible":
        required.append(("Base URL", "base_url"))
    missing = [label for label, key in required if not str(model.get(key) or "").strip()]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"模型配置不完整，缺少 {', '.join(missing)}",
        )


async def run_model_connectivity_test(
    model: ModelConfig,
) -> ModelConnectivityTestResponse:
    resolved = await _resolve_model_secret(model)
    _validate_test_model(resolved)

    started = perf_counter()
    try:
        runtime_model = build_agno_model(resolved)
        cast(Any, runtime_model).timeout = 15
        await runtime_model.aresponse(
            messages=[
                Message(
                    role="system",
                    content="你是授权环境中的安全防御助手，只回答防御和排查问题。",
                ),
                Message(role="user", content="请只回复 OK，用于验证模型调用链路。"),
            ]
        )
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        detail = str(getattr(exc, "message", None) or exc)
        logger.warning(
            "model connectivity test failed status_code={} detail={}",
            status_code if isinstance(status_code, int) else None,
            detail,
        )
        return ModelConnectivityTestResponse(
            success=False,
            latency_ms=int((perf_counter() - started) * 1000),
            message=detail,
            status_code=status_code if isinstance(status_code, int) else None,
        )

    latency_ms = int((perf_counter() - started) * 1000)
    return ModelConnectivityTestResponse(
        success=True,
        latency_ms=latency_ms,
        message="模型连通性正常",
        status_code=200,
    )


@router.get("/settings/chat")
async def read_chat_settings(
    _user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, Any]:
    """Read chat privacy toggles and Agno runtime knobs (history, memory, tools)."""
    return await get_chat_settings()


@router.patch("/settings/chat")
async def patch_chat_settings(
    request: Request,
    body: ChatSettingsUpdate,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    result = await update_chat_settings(values)
    await record_audit_event_async(
        user,
        action="settings.chat.update",
        resource_type="chat_settings",
        metadata={"keys": sorted(values)},
        **audit_request_context(request),
    )
    return result


@router.get("/settings/notifications")
async def read_notification_settings(
    user: User = Depends(require_scope("sessions:read")),
) -> dict[str, Any]:
    """Read the current user's notification preferences (webhook never returned in full)."""
    return await read_user_notification_settings(actor_id(user))


@router.patch("/settings/notifications")
async def patch_notification_settings(
    request: Request,
    body: UserNotificationSettingsUpdate,
    user: User = Depends(require_scope("sessions:read")),
) -> dict[str, Any]:
    """Update the current user's Feishu webhook (or clear with empty string)."""
    try:
        result = await update_user_feishu_webhook(
            actor_id(user),
            body.feishu_webhook_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await record_audit_event_async(
        user,
        action="settings.notifications.update",
        resource_type="user_notification_settings",
        resource_id=actor_id(user),
        metadata={
            "feishu_webhook_configured": result.get("feishu_webhook_configured"),
            "cleared": body.feishu_webhook_url == "",
        },
        **audit_request_context(request),
    )
    return result


@router.get("/settings/knowledge")
async def read_knowledge_rag_settings(
    _user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, Any]:
    """Read globally enforced PgVector / knowledge retrieval settings."""
    return await get_knowledge_rag_settings()


@router.patch("/settings/knowledge")
async def patch_knowledge_rag_settings(
    request: Request,
    body: KnowledgeRagSettingsUpdate,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    try:
        result = await update_knowledge_rag_settings(values)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_audit_event_async(
        user,
        action="settings.knowledge.update",
        resource_type="knowledge_rag_settings",
        metadata={"keys": sorted(values)},
        **audit_request_context(request),
    )
    return result


@router.get("/settings/guardrails")
async def read_guardrail_settings(
    _user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, Any]:
    """Read global Agno input-guardrail settings (PII + prompt injection)."""
    return await get_guardrail_settings()


@router.patch("/settings/guardrails")
async def patch_guardrail_settings(
    request: Request,
    body: GuardrailSettingsUpdate,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    result = await update_guardrail_settings(values)
    await record_audit_event_async(
        user,
        action="settings.guardrails.update",
        resource_type="guardrail_settings",
        metadata={"keys": sorted(values)},
        **audit_request_context(request),
    )
    return result


@router.get("/models")
async def get_models(_user: User = Depends(require_scope("config:read"))) -> dict:
    """获取可选模型配置（敏感值已脱敏）"""
    return await public_model_config()


@router.put("/models")
async def update_models(
    request: Request,
    body: ModelConfigUpdate,
    user: User = Depends(require_scope("config:write")),
) -> dict:
    """保存模型配置和默认选择"""
    logger.info("模型配置已更新")
    result = await save_model_config(body.models, body.active_model_id)
    await record_audit_event_async(
        user,
        action="settings.update",
        resource_type="models",
        metadata={"active_model_id": body.active_model_id},
        **audit_request_context(request),
    )
    return result


@router.post("/models/test")
async def test_model_connectivity(
    request: Request,
    body: ModelConfig,
    user: User = Depends(require_scope("config:write")),
) -> ModelConnectivityTestResponse:
    """测试 OpenAI-compatible 模型配置连通性。"""
    result = await run_model_connectivity_test(body)
    await record_audit_event_async(
        user,
        action="settings.test_model",
        resource_type="models",
        resource_id=body.id,
        metadata={
            "model_id": body.model_id,
            "success": result.success,
            "status_code": result.status_code,
        },
        **audit_request_context(request),
    )
    return result
