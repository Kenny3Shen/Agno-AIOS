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
from api.services.chat_settings_service import get_chat_settings, update_chat_settings

router = APIRouter(prefix="/api", tags=["Settings"])

class ChatSettingsUpdate(BaseModel):
    show_raw_reasoning: bool | None = None
    show_raw_tool_io: bool | None = None
    show_thought_chain: bool | None = None
    memory_enabled: bool | None = None


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
) -> dict[str, bool]:
    """Read globally enforced chat privacy and memory settings."""
    return await get_chat_settings()


@router.patch("/settings/chat")
async def patch_chat_settings(
    request: Request,
    body: ChatSettingsUpdate,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict[str, bool]:
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
