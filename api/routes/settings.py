from fastapi import APIRouter
from pydantic import BaseModel
from loguru import logger
import os

from api.services.model_config_service import public_model_config, save_model_config

router = APIRouter(prefix="/api", tags=["Settings"])

# 可配置的环境变量白名单
CONFIGURABLE_KEYS = [
    "MCP_SERVER_URL",
    "MCP_TOKEN",
    "FEISHU_WEBHOOK_URL",
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


class ModelConfig(BaseModel):
    id: str
    name: str
    model_id: str
    base_url: str
    api_key: str = ""
    description: str = ""
    enabled: bool = True
    builtin: bool = False


class ModelConfigUpdate(BaseModel):
    active_model_id: str | None = None
    models: list[ModelConfig]


@router.get("/settings")
async def get_settings() -> SettingsResponse:
    """获取当前可配置项（敏感值已脱敏）"""
    result: dict[str, str] = {}
    for key in CONFIGURABLE_KEYS:
        raw = os.environ.get(key, "")
        result[key] = _mask_secret(key, raw)
    return SettingsResponse(settings=result)


@router.get("/models")
async def get_models() -> dict:
    """获取可选模型配置（敏感值已脱敏）"""
    return public_model_config()


@router.put("/models")
async def update_models(body: ModelConfigUpdate) -> dict:
    """保存模型配置和默认选择"""
    logger.info("模型配置已更新")
    return save_model_config(
        [model.model_dump() for model in body.models],
        body.active_model_id,
    )


@router.put("/settings")
async def update_settings(body: SettingsUpdate) -> SettingsResponse:
    """更新配置项（运行时生效，写入 os.environ）"""
    updated: dict[str, str] = {}
    for key, value in body.settings.items():
        if key not in CONFIGURABLE_KEYS:
            continue
        # 跳过掩码值（用户未修改）
        if "*" in value:
            continue
        os.environ[key] = value
        logger.info(f"配置已更新: {key}")
        updated[key] = _mask_secret(key, value)

    # 返回完整配置
    result: dict[str, str] = {}
    for key in CONFIGURABLE_KEYS:
        raw = os.environ.get(key, "")
        result[key] = _mask_secret(key, raw)
    return SettingsResponse(settings=result)
