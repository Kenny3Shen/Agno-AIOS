import os
from time import perf_counter
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel

from api.auth.models import User
from api.auth.permissions import require_permission
from api.config import Settings, get_settings
from api.dependencies import get_app_settings
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.model_config_service import (
    ModelConfig,
    ModelConfigUpdate,
    load_model_config,
    public_model_config,
    save_model_config,
)

router = APIRouter(prefix="/api", tags=["Settings"])

# 可配置的环境变量白名单
CONFIGURABLE_KEYS = [
    "MCP_SERVER_URL",
    "MCP_TOKEN",
    "FEISHU_WEBHOOK_URL",
    "NAV_TAGS",
]


def _mask_secret(key: str, value: str) -> str:
    """对敏感字段做掩码处理，只返回前4位和后4位"""
    if not value:
        return ""
    sensitive = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    if any(s in key.upper() for s in sensitive) and len(value) > 8:
        return value[:4] + "*" * (len(value) - 8) + value[-4:]
    return value


class SettingsResponse(BaseModel):
    settings: dict[str, str]


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


class ModelConnectivityTestResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    message: str
    status_code: int | None = None


def _setting_value(settings: Settings, key: str) -> str:
    runtime_value = os.environ.get(key)
    if runtime_value is not None:
        return runtime_value
    if key == "MCP_SERVER_URL":
        return settings.mcp_server_url
    if key == "MCP_TOKEN":
        return settings.mcp_token.get_secret_value()
    if key == "FEISHU_WEBHOOK_URL":
        return settings.feishu_webhook_url.get_secret_value()
    if key == "NAV_TAGS":
        return os.environ.get("NAV_TAGS", "{}")
    return ""


def _model_chat_completions_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_upstream_error(data: Any, fallback: str) -> str:
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        detail = data.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        message = data.get("message")
        if isinstance(message, str) and message:
            return message
    return fallback


def _resolve_model_secret(model: ModelConfig) -> dict[str, Any]:
    data = model.model_dump()
    if "*" not in data.get("api_key", ""):
        return data

    data["api_key"] = ""
    for saved in load_model_config().get("models", []):
        if isinstance(saved, dict) and saved.get("id") == model.id:
            data["api_key"] = str(saved.get("api_key") or "")
            break
    return data


def _validate_test_model(model: dict[str, Any]) -> None:
    missing = [
        label
        for label, key in (
            ("API Key", "api_key"),
            ("Base URL", "base_url"),
            ("Model ID", "model_id"),
        )
        if not str(model.get(key) or "").strip()
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"模型配置不完整，缺少 {', '.join(missing)}",
        )


async def run_model_connectivity_test(
    model: ModelConfig,
) -> ModelConnectivityTestResponse:
    resolved = _resolve_model_secret(model)
    _validate_test_model(resolved)

    started = perf_counter()
    url = _model_chat_completions_url(str(resolved["base_url"]))
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {resolved['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": resolved["model_id"],
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是授权环境中的安全防御助手，只回答防御和排查问题。",
                        },
                        {
                            "role": "user",
                            "content": "请只回复 OK，用于验证 Chat 模型调用链路。",
                        },
                    ],
                    "max_tokens": 8,
                    "temperature": 0,
                    "stream": False,
                },
            )
    except httpx.TimeoutException:
        return ModelConnectivityTestResponse(
            success=False,
            message="连接超时",
        )
    except httpx.RequestError as exc:
        return ModelConnectivityTestResponse(
            success=False,
            message=f"连接失败: {exc}",
        )

    latency_ms = int((perf_counter() - started) * 1000)
    if response.is_success:
        return ModelConnectivityTestResponse(
            success=True,
            latency_ms=latency_ms,
            message="模型连通性正常",
            status_code=response.status_code,
        )

    fallback = f"模型服务返回 HTTP {response.status_code}"
    data = None
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            data = response.json()
        except ValueError:
            data = None
    if data is None:
        text = response.text.strip()
        fallback = f"{fallback}: {text[:200]}" if text else fallback
    return ModelConnectivityTestResponse(
        success=False,
        latency_ms=latency_ms,
        message=_extract_upstream_error(data, fallback),
        status_code=response.status_code,
    )


@router.get("/settings")
def read_settings(
    _user: User = Depends(require_permission("settings:read")),
    settings: Settings = Depends(get_app_settings),
) -> SettingsResponse:
    """获取当前可配置项（敏感值已脱敏）"""
    result: dict[str, str] = {}
    for key in CONFIGURABLE_KEYS:
        raw = _setting_value(settings, key)
        result[key] = _mask_secret(key, raw)
    return SettingsResponse(settings=result)


@router.get("/models")
def get_models(_user: User = Depends(require_permission("settings:read"))) -> dict:
    """获取可选模型配置（敏感值已脱敏）"""
    return public_model_config()


@router.put("/models")
async def update_models(
    request: Request,
    body: ModelConfigUpdate,
    user: User = Depends(require_permission("settings:write")),
) -> dict:
    """保存模型配置和默认选择"""
    logger.info("模型配置已更新")
    result = save_model_config(
        body.models,
        body.active_model_id,
    )
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
    user: User = Depends(require_permission("settings:write")),
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


@router.put("/settings")
async def update_settings(
    request: Request,
    body: SettingsUpdate,
    user: User = Depends(require_permission("settings:write")),
) -> SettingsResponse:
    """更新配置项（运行时生效，写入 os.environ）"""
    updated: dict[str, str] = {}
    for key, value in body.settings.items():
        if key not in CONFIGURABLE_KEYS:
            continue
        # 跳过掩码值（用户未修改）
        if "*" in value:
            continue
        os.environ[key] = value
        get_settings.cache_clear()
        logger.info(f"配置已更新: {key}")
        updated[key] = _mask_secret(key, value)

    # 返回完整配置
    result: dict[str, str] = {}
    active_settings = get_settings()
    for key in CONFIGURABLE_KEYS:
        raw = _setting_value(active_settings, key)
        result[key] = _mask_secret(key, raw)
    await record_audit_event_async(
        user,
        action="settings.update",
        resource_type="settings",
        metadata={"keys": sorted(updated)},
        **audit_request_context(request),
    )
    return SettingsResponse(settings=result)
