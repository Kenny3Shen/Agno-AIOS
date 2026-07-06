import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from api.config import get_settings
from api.services.runtime_paths import CONFIG_DIR, resolve_project_path


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str = "自定义模型"
    model_id: str = ""
    base_url: str = ""
    api_key: str = ""
    description: str = ""
    enabled: bool = True
    builtin: bool = False

    @classmethod
    def normalized(cls, entry: "ModelConfig | Mapping[Any, Any]", fallback_id: str) -> Self:
        raw = entry.model_dump() if isinstance(entry, ModelConfig) else dict(entry)
        model_id = str(raw.get("id") or fallback_id).strip() or fallback_id
        return cls(
            id=model_id,
            name=str(raw.get("name") or "自定义模型").strip(),
            model_id=str(raw.get("model_id") or "").strip(),
            base_url=str(raw.get("base_url") or "").strip(),
            api_key=str(raw.get("api_key") or "").strip(),
            description=str(raw.get("description") or "").strip(),
            enabled=bool(raw.get("enabled", True)),
            builtin=bool(raw.get("builtin", False)),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model_id)

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["api_key"] = _mask_secret(self.api_key)
        data["configured"] = self.configured
        return data


class ModelConfigUpdate(BaseModel):
    active_model_id: str | None = None
    models: list[ModelConfig]


DEFAULT_MODELS: tuple[ModelConfig, ...] = (
    ModelConfig(
        id="deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        model_id="deepseek-v4-flash",
        description="低延迟安全分析模型",
        builtin=True,
    ),
    ModelConfig(
        id="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        model_id="deepseek-v4-pro",
        description="复杂推理与深度研判模型",
        builtin=True,
    ),
)


class ModelConfigStore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active_model_id: str = ""
    models: list[ModelConfig] = Field(default_factory=list)

    @classmethod
    def default(cls) -> Self:
        return cls(
            active_model_id=DEFAULT_MODELS[0].id,
            models=_default_models(),
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any] | None) -> Self:
        if not isinstance(raw, Mapping):
            return cls.default()
        models: list[ModelConfig] = []
        models_raw = raw.get("models", [])
        if isinstance(models_raw, list):
            for index, entry in enumerate(models_raw):
                if isinstance(entry, ModelConfig | Mapping):
                    models.append(ModelConfig.normalized(entry, f"model-{index + 1}"))
        store = cls(
            active_model_id=str(raw.get("active_model_id") or "").strip(),
            models=models,
        )
        return store.with_defaults().with_valid_active_model()

    @classmethod
    def from_submitted(
        cls,
        models: Iterable[ModelConfig | Mapping[Any, Any]],
        *,
        active_model_id: str | None,
        existing: "ModelConfigStore",
    ) -> Self:
        existing_by_id = {model.id: model for model in existing.models}
        normalized: list[ModelConfig] = []
        for index, entry in enumerate(models):
            model = ModelConfig.normalized(entry, f"model-{index + 1}")
            previous = existing_by_id.get(model.id)
            if previous is not None and _is_masked_secret(model.api_key):
                model = model.model_copy(update={"api_key": previous.api_key})
            normalized.append(model)
        if not normalized:
            normalized = _default_models()
        store = cls(
            active_model_id=(active_model_id or "").strip(),
            models=normalized,
        )
        return store.with_defaults().with_valid_active_model()

    def with_defaults(self) -> Self:
        models = [model.model_copy(deep=True) for model in self.models]
        model_ids = {model.id for model in models}
        for default_model in DEFAULT_MODELS:
            if default_model.id in model_ids:
                continue
            insert_at = len([model for model in models if model.builtin])
            models.insert(insert_at, default_model.model_copy(deep=True))
            model_ids.add(default_model.id)
        return self.model_copy(update={"models": models})

    def with_valid_active_model(self) -> Self:
        if not self.models:
            return self.default()
        model_ids = {model.id for model in self.models}
        if self.active_model_id in model_ids:
            return self
        return self.model_copy(update={"active_model_id": self.models[0].id})

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "active_model_id": self.active_model_id,
            "models": [model.model_dump() for model in self.models],
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "active_model_id": self.active_model_id,
            "models": [model.to_public_dict() for model in self.models],
        }

    def model_for_run(self, model_id: str | None = None) -> ModelConfig:
        selected_id = model_id or self.active_model_id
        models = {model.id: model for model in self.models}
        model = models.get(selected_id) or models.get(self.active_model_id)
        if not model:
            raise ValueError("未找到可用模型配置")
        if not model.enabled:
            raise ValueError(f"模型已禁用: {model.name}")
        missing = [
            label
            for label, key in (
                ("API Key", "api_key"),
                ("Base URL", "base_url"),
                ("Model ID", "model_id"),
            )
            if not getattr(model, key)
        ]
        if missing:
            raise ValueError(
                f"模型配置不完整: {model.name} 缺少 {', '.join(missing)}。请在系统配置中补全。"
            )
        return model


def model_config_file() -> Path:
    return resolve_project_path(
        get_settings().agno_model_config_file or CONFIG_DIR / "model_config.json"
    )


def _default_models() -> list[ModelConfig]:
    return [model.model_copy(deep=True) for model in DEFAULT_MODELS]


def _is_masked_secret(value: str) -> bool:
    return "*" in value


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def load_model_config_store() -> ModelConfigStore:
    config_file = model_config_file()
    if not config_file.exists():
        return ModelConfigStore.default()
    try:
        raw = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return ModelConfigStore.default()
    return ModelConfigStore.from_raw(raw)


def load_model_config() -> dict[str, Any]:
    return load_model_config_store().to_storage_dict()


def public_model_config() -> dict[str, Any]:
    return load_model_config_store().to_public_dict()


def save_model_config(
    models: Iterable[ModelConfig | Mapping[Any, Any]], active_model_id: str | None
) -> dict[str, Any]:
    existing = load_model_config_store()
    store = ModelConfigStore.from_submitted(
        models,
        active_model_id=active_model_id,
        existing=existing,
    )
    config_file = model_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(store.to_storage_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return store.to_public_dict()


def get_model_for_run(model_id: str | None = None) -> dict[str, Any]:
    return load_model_config_store().model_for_run(model_id).model_dump()
