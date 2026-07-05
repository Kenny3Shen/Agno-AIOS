from fastapi import HTTPException, Request

from api.config import Settings, get_settings


def get_app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return get_settings()
    if not isinstance(settings, Settings):
        raise HTTPException(503, "应用配置未正确初始化。")
    return settings
