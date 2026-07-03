import json
import os
from typing import Any, cast

from api.services.runtime_paths import CONFIG_DIR, resolve_project_path

MODEL_CONFIG_FILE = resolve_project_path(
    os.getenv("AGNO_MODEL_CONFIG_FILE") or CONFIG_DIR / "model_config.json"
)

DEFAULT_MODELS: list[dict[str, Any]] = [
    {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "model_id": "deepseek-v4-flash",
        "base_url": "",
        "api_key": "",
        "description": "低延迟安全分析模型",
        "enabled": True,
        "builtin": True,
    },
    {
        "id": "deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "model_id": "deepseek-v4-pro",
        "base_url": "",
        "api_key": "",
        "description": "复杂推理与深度研判模型",
        "enabled": True,
        "builtin": True,
    },
]


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _normalize_model(entry: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    model_id = str(entry.get("id") or fallback_id).strip() or fallback_id
    return {
        "id": model_id,
        "name": str(entry.get("name") or "自定义模型").strip(),
        "model_id": str(entry.get("model_id") or "").strip(),
        "base_url": str(entry.get("base_url") or "").strip(),
        "api_key": str(entry.get("api_key") or "").strip(),
        "description": str(entry.get("description") or "").strip(),
        "enabled": bool(entry.get("enabled", True)),
        "builtin": bool(entry.get("builtin", False)),
    }


def _default_config() -> dict[str, Any]:
    return {
        "active_model_id": DEFAULT_MODELS[0]["id"],
        "models": DEFAULT_MODELS,
    }


def load_model_config() -> dict[str, Any]:
    if not MODEL_CONFIG_FILE.exists():
        return _default_config()

    try:
        raw = json.loads(MODEL_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_config()

    models_raw = raw.get("models", [])
    models: list[dict[str, Any]] = []
    if isinstance(models_raw, list):
        for index, entry in enumerate(models_raw):
            if isinstance(entry, dict):
                models.append(
                    _normalize_model(cast(dict[str, Any], entry), f"model-{index + 1}")
                )

    by_id = {model["id"]: model for model in models}
    for default_model in DEFAULT_MODELS:
        if default_model["id"] not in by_id:
            models.insert(
                len([m for m in models if m.get("builtin")]), default_model.copy()
            )

    active_model_id = str(raw.get("active_model_id") or "").strip()
    if not active_model_id or active_model_id not in {model["id"] for model in models}:
        active_model_id = models[0]["id"] if models else DEFAULT_MODELS[0]["id"]

    return {
        "active_model_id": active_model_id,
        "models": models or DEFAULT_MODELS,
    }


def public_model_config() -> dict[str, Any]:
    config = load_model_config()
    public_models = []
    for model in config["models"]:
        public_models.append(
            {
                **model,
                "api_key": _mask_secret(model.get("api_key", "")),
                "configured": bool(
                    model.get("api_key")
                    and model.get("base_url")
                    and model.get("model_id")
                ),
            }
        )
    return {
        "active_model_id": config["active_model_id"],
        "models": public_models,
    }


def save_model_config(
    models: list[dict[str, Any]], active_model_id: str | None
) -> dict[str, Any]:
    existing = {model["id"]: model for model in load_model_config()["models"]}
    normalized: list[dict[str, Any]] = []

    for index, entry in enumerate(models):
        model = _normalize_model(entry, f"model-{index + 1}")
        previous = existing.get(model["id"])
        if previous and "*" in model["api_key"]:
            model["api_key"] = previous.get("api_key", "")
        normalized.append(model)

    if not normalized:
        normalized = [model.copy() for model in DEFAULT_MODELS]

    model_ids = {model["id"] for model in normalized}
    next_active = (active_model_id or "").strip()
    if next_active not in model_ids:
        next_active = normalized[0]["id"]

    config = {
        "active_model_id": next_active,
        "models": normalized,
    }
    MODEL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return public_model_config()


def get_model_for_run(model_id: str | None = None) -> dict[str, Any]:
    config = load_model_config()
    selected_id = model_id or config["active_model_id"]
    models = {model["id"]: model for model in config["models"]}
    model = models.get(selected_id) or models.get(config["active_model_id"])

    if not model:
        raise ValueError("未找到可用模型配置")
    if not model.get("enabled", True):
        raise ValueError(f"模型已禁用: {model.get('name')}")

    missing = [
        label
        for label, key in (
            ("API Key", "api_key"),
            ("Base URL", "base_url"),
            ("Model ID", "model_id"),
        )
        if not model.get(key)
    ]
    if missing:
        raise ValueError(
            f"模型配置不完整: {model.get('name')} 缺少 {', '.join(missing)}。请在系统配置中补全。"
        )
    return model
