from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import time
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loguru import logger

from api.config import get_settings
from api.persistence.model_configs import list_model_config_rows, replace_model_config_rows
from api.services.runtime_paths import CONFIG_DIR, resolve_project_path
from api.utils.json import loads
from api.services.model_capabilities import (
    apply_optimal_model_defaults,
    capabilities_for,
    provider_defaults as _capability_provider_defaults,
    resolve_reasoning_effort,
)

# Short-lived process cache for hot chat/settings reads; cleared on save/seed rewrite.
_STORE_CACHE: ModelConfigStore | None = None
_STORE_CACHE_AT: float = 0.0
_STORE_CACHE_TTL_SEC = 5.0


def _invalidate_model_config_cache() -> None:
    global _STORE_CACHE, _STORE_CACHE_AT
    _STORE_CACHE = None
    _STORE_CACHE_AT = 0.0


def _cache_model_config_store(store: ModelConfigStore) -> ModelConfigStore:
    global _STORE_CACHE, _STORE_CACHE_AT
    _STORE_CACHE = store
    _STORE_CACHE_AT = time.time()
    return store




def _optional_int(
    value: Any,
    *,
    default: int | None,
    minimum: int,
    maximum: int,
    allow_none: bool = False,
) -> int | None:
    if value is None or value == "":
        if allow_none:
            return default
        return 0 if default is None else default
    try:
        number = int(value)
    except (TypeError, ValueError):
        if allow_none:
            return default
        return 0 if default is None else default
    return max(minimum, min(maximum, number))


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text_value = str(value).strip().lower()
    if text_value in {"1", "true", "yes", "on"}:
        return True
    if text_value in {"0", "false", "no", "off"}:
        return False
    return default


ModelProvider = Literal["deepseek", "openai", "openai-compatible", "xai"]
ModelApiProtocol = Literal["chat-completions", "responses"]
StructuredOutputMode = Literal["native", "json"]
ReasoningEffort = Literal["minimal", "low", "medium", "high", "max"]


def _provider_defaults(provider: str) -> tuple[str, str, str | None]:
    return _capability_provider_defaults(provider)


def _looks_like_xai(base_url: str, model_id: str) -> bool:
    base = (base_url or "").strip().lower()
    mid = (model_id or "").strip().lower()
    if "api.x.ai" in base:
        return True
    return mid.startswith("grok")


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str = "自定义模型"
    model_id: str = ""
    provider: ModelProvider = "openai-compatible"
    api_protocol: ModelApiProtocol = "chat-completions"
    structured_output_mode: StructuredOutputMode = "json"
    default_reasoning_effort: ReasoningEffort | None = None
    parallel_tool_calls: bool | None = None
    live_search_enabled: bool = False
    retries: int = Field(default=4, ge=0, le=10)
    delay_between_retries: int = Field(default=1, ge=0, le=60)
    exponential_backoff: bool = True
    http_max_retries: int | None = Field(default=None, ge=0, le=10)
    base_url: str = ""
    api_key: str = ""
    description: str = ""
    enabled: bool = True
    builtin: bool = False

    @field_validator("structured_output_mode", mode="before")
    @classmethod
    def _normalize_structured_output_mode(cls, value: Any) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"", "none"}:
            return "json"
        return mode

    @field_validator("api_protocol", mode="before")
    @classmethod
    def _normalize_api_protocol(cls, value: Any) -> str:
        protocol = str(value or "").strip().lower()
        return protocol or "chat-completions"

    @field_validator("default_reasoning_effort", mode="before")
    @classmethod
    def _normalize_reasoning_effort(cls, value: Any) -> str | None:
        effort = str(value or "").strip().lower()
        return effort or None

    @model_validator(mode="before")
    @classmethod
    def _apply_provider_defaults(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        raw = dict(value)
        base_url = str(raw.get("base_url") or "").strip()
        model_id = str(raw.get("model_id") or "").strip()
        provider = str(raw.get("provider") or "").strip()
        # Migrate legacy Grok entries that used OpenAI-compatible + api.x.ai / Responses.
        if provider in {"", "openai-compatible"} and _looks_like_xai(base_url, model_id):
            provider = "xai"
            raw["provider"] = "xai"
        if not provider:
            provider = "openai-compatible"
            raw["provider"] = provider
        # Provider locks + optimal defaults (missing keys only)
        raw = apply_optimal_model_defaults(raw, force=False)
        caps = capabilities_for(provider, model_id=model_id)
        if caps.locks_api_protocol:
            raw["api_protocol"] = caps.optimal_api_protocol
        if provider == "deepseek":
            raw["structured_output_mode"] = caps.optimal_structured_output
        if not caps.supports_reasoning_effort:
            raw["default_reasoning_effort"] = None
        return raw

    @model_validator(mode="after")
    def _validate_reasoning_effort(self) -> Self:
        caps = capabilities_for(
            self.provider,
            api_protocol=self.api_protocol,
            model_id=self.model_id,
        )
        if not caps.supports_reasoning_effort:
            # Strip rather than hard-fail so legacy configs load cleanly.
            if self.default_reasoning_effort is not None:
                self.default_reasoning_effort = None
            return self
        if self.default_reasoning_effort is None:
            self.default_reasoning_effort = cast(
                ReasoningEffort | None, caps.optimal_reasoning_effort
            )
            return self
        resolved = resolve_reasoning_effort(
            provider=self.provider,
            api_protocol=self.api_protocol,
            model_id=self.model_id,
            configured=self.default_reasoning_effort,
        )
        if resolved != self.default_reasoning_effort:
            self.default_reasoning_effort = cast(ReasoningEffort | None, resolved)
        return self

    @classmethod
    def normalized(cls, entry: "ModelConfig | Mapping[Any, Any]", fallback_id: str) -> Self:
        raw = entry.model_dump() if isinstance(entry, ModelConfig) else dict(entry)
        config_id = str(raw.get("id") or fallback_id).strip() or fallback_id
        configured_model_id = str(raw.get("model_id") or "").strip()
        base_url = str(raw.get("base_url") or "").strip()
        provider = str(raw.get("provider") or "").strip()
        if not provider:
            if configured_model_id.startswith("deepseek-") or "api.deepseek.com" in base_url:
                provider = "deepseek"
            elif _looks_like_xai(base_url, configured_model_id):
                provider = "xai"
            else:
                provider = "openai-compatible"
        elif provider == "openai-compatible" and _looks_like_xai(base_url, configured_model_id):
            provider = "xai"

        default_protocol, default_output_mode, default_reasoning_effort = _provider_defaults(provider)
        api_protocol = str(raw.get("api_protocol") or default_protocol).strip()
        structured_output_mode = str(
            raw.get("structured_output_mode") or default_output_mode
        ).strip()
        if structured_output_mode == "none":
            structured_output_mode = "json"
        configured_reasoning_effort = raw.get("default_reasoning_effort")
        if configured_reasoning_effort is None:
            configured_reasoning_effort = default_reasoning_effort

        return cls(
            id=config_id,
            name=str(raw.get("name") or configured_model_id or "自定义模型").strip(),
            model_id=configured_model_id,
            provider=cast(ModelProvider, provider),
            api_protocol=cast(ModelApiProtocol, api_protocol),
            structured_output_mode=cast(StructuredOutputMode, structured_output_mode),
            default_reasoning_effort=cast(ReasoningEffort | None, configured_reasoning_effort),
            parallel_tool_calls=raw.get("parallel_tool_calls"),
            live_search_enabled=_optional_bool(raw.get("live_search_enabled"), default=False),
            retries=_optional_int(raw.get("retries"), default=4, minimum=0, maximum=10) or 0,
            delay_between_retries=_optional_int(
                raw.get("delay_between_retries"), default=1, minimum=0, maximum=60
            )
            or 0,
            exponential_backoff=_optional_bool(raw.get("exponential_backoff"), default=True),
            http_max_retries=_optional_int(
                raw.get("http_max_retries"),
                default=None,
                minimum=0,
                maximum=10,
                allow_none=True,
            ),
            base_url=base_url,
            api_key=str(raw.get("api_key") or "").strip(),
            description=str(raw.get("description") or "").strip(),
            enabled=bool(raw.get("enabled", True)),
            builtin=bool(raw.get("builtin", False)),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.api_key
            and self.model_id
            and (self.base_url or self.provider not in {"openai-compatible"})
        )

    def to_public_dict(self) -> dict[str, Any]:
        from api.services.model_capabilities import public_capabilities

        data = self.model_dump()
        data["api_key"] = _mask_secret(self.api_key)
        data["configured"] = self.configured
        data["capabilities"] = public_capabilities(
            self.provider,
            api_protocol=self.api_protocol,
            model_id=self.model_id,
        )
        return data


class ModelConfigUpdate(BaseModel):
    active_model_id: str | None = None
    models: list[ModelConfig]


DEFAULT_MODELS: tuple[ModelConfig, ...] = (
    ModelConfig(
        id="deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        model_id="deepseek-v4-flash",
        provider="deepseek",
        api_protocol="chat-completions",
        structured_output_mode="json",
        default_reasoning_effort="max",
        base_url="https://api.deepseek.com",
        description="低延迟安全分析模型",
        builtin=True,
    ),
    ModelConfig(
        id="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        model_id="deepseek-v4-pro",
        provider="deepseek",
        api_protocol="chat-completions",
        structured_output_mode="json",
        default_reasoning_effort="max",
        base_url="https://api.deepseek.com",
        description="复杂推理与深度研判模型",
        builtin=True,
    ),
    ModelConfig(
        id="xai-grok-4.5",
        name="Grok 4.5 (xAI)",
        model_id="grok-4.5",
        provider="xai",
        api_protocol="chat-completions",
        structured_output_mode="json",
        default_reasoning_effort=None,
        base_url="https://api.x.ai/v1",
        description="xAI 官方 Agno 接入（Chat Completions）",
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
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> Self:
        models: list[ModelConfig] = []
        active_model_id = ""
        for index, row in enumerate(rows):
            if row.get("active") and not active_model_id:
                active_model_id = str(row.get("id") or "").strip()
            models.append(ModelConfig.normalized(row, f"model-{index + 1}"))
        return cls(active_model_id=active_model_id, models=models)

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
        required = [("API Key", "api_key"), ("Model ID", "model_id")]
        if model.provider == "openai-compatible":
            required.append(("Base URL", "base_url"))
        # xAI uses official default base_url when empty.
        missing = [label for label, key in required if not getattr(model, key)]
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


def _archive_legacy_model_config_file(config_file: Path) -> None:
    """Rename one-shot JSON bootstrap so empty-table import is not re-applied."""
    try:
        archived = config_file.with_name(f"{config_file.name}.imported")
        # Avoid clobbering a previous archive; keep the first successful import.
        if archived.exists():
            config_file.unlink(missing_ok=True)
            return
        config_file.rename(archived)
        logger.info("archived legacy model config to {}", archived)
    except OSError:
        logger.warning(
            "unable to archive legacy model config at {}",
            config_file,
            exc_info=True,
        )


def _load_legacy_or_default_store() -> tuple[ModelConfigStore, Path | None]:
    """Bootstrap store from legacy JSON once, else built-in defaults.

    Returns ``(store, legacy_path_if_used)`` so callers can archive the file
    after a successful Postgres seed.
    """
    config_file = model_config_file()
    if not config_file.exists():
        return ModelConfigStore.default(), None
    try:
        raw = loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "legacy model config unreadable at {}; using defaults",
            config_file,
            exc_info=True,
        )
        return ModelConfigStore.default(), None
    return ModelConfigStore.from_raw(raw), config_file


def _rows_need_persist(rows: Iterable[Mapping[str, Any]]) -> bool:
    active_count = 0
    invalid_output_mode = False
    for row in rows:
        if row.get("active"):
            active_count += 1
        if str(row.get("structured_output_mode") or "").strip() not in {"native", "json"}:
            invalid_output_mode = True
    return active_count != 1 or invalid_output_mode


def _store_to_rows(
    store: ModelConfigStore,
    existing_rows: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    now = int(time.time())
    created_at_by_id = {
        str(row.get("id")): int(row.get("created_at") or now)
        for row in existing_rows
    }
    rows: list[dict[str, Any]] = []
    for index, model in enumerate(store.models):
        rows.append(
            {
                "id": model.id,
                "name": model.name,
                "model_id": model.model_id,
                "provider": model.provider,
                "api_protocol": model.api_protocol,
                "structured_output_mode": model.structured_output_mode,
                "default_reasoning_effort": model.default_reasoning_effort,
                "parallel_tool_calls": model.parallel_tool_calls,
                "live_search_enabled": model.live_search_enabled,
                "retries": model.retries,
                "delay_between_retries": model.delay_between_retries,
                "exponential_backoff": model.exponential_backoff,
                "http_max_retries": model.http_max_retries,
                "base_url": model.base_url,
                "api_key": model.api_key,
                "description": model.description,
                "enabled": model.enabled,
                "builtin": model.builtin,
                "active": model.id == store.active_model_id,
                "sort_order": index,
                "created_at": created_at_by_id.get(model.id, now),
                "updated_at": now,
            }
        )
    return rows


async def load_model_config_store() -> ModelConfigStore:
    global _STORE_CACHE, _STORE_CACHE_AT
    now = time.time()
    if _STORE_CACHE is not None and (now - _STORE_CACHE_AT) < _STORE_CACHE_TTL_SEC:
        return _STORE_CACHE

    rows = await list_model_config_rows()
    if not rows:
        store, legacy_path = _load_legacy_or_default_store()
        source = "legacy file" if legacy_path is not None else "defaults"
        logger.info(
            "model config table empty; seeding {} model(s) from {}",
            len(store.models),
            source,
        )
        await replace_model_config_rows(_store_to_rows(store))
        if legacy_path is not None:
            _archive_legacy_model_config_file(legacy_path)
        return _cache_model_config_store(store)

    base_store = ModelConfigStore.from_rows(rows)
    store = base_store.with_defaults().with_valid_active_model()
    # Integrity only: multi-active / invalid output mode / missing builtins / bad active.
    # Provider heuristics (e.g. Grok→xai) stay read-path via ModelConfig.normalized;
    # persist on explicit save, not every hot load.
    needs_rewrite = (
        store.to_storage_dict() != base_store.to_storage_dict()
        or _rows_need_persist(rows)
    )
    if needs_rewrite:
        logger.info(
            "rewriting model config rows (integrity normalize); count={}",
            len(store.models),
        )
        await replace_model_config_rows(_store_to_rows(store, rows))
    return _cache_model_config_store(store)


async def load_model_config() -> dict[str, Any]:
    return (await load_model_config_store()).to_storage_dict()


async def public_model_config() -> dict[str, Any]:
    return (await load_model_config_store()).to_public_dict()


async def save_model_config(
    models: Iterable[ModelConfig | Mapping[Any, Any]], active_model_id: str | None
) -> dict[str, Any]:
    existing = await load_model_config_store()
    store = ModelConfigStore.from_submitted(
        models,
        active_model_id=active_model_id,
        existing=existing,
    )
    existing_rows = await list_model_config_rows()
    await replace_model_config_rows(_store_to_rows(store, existing_rows))
    _invalidate_model_config_cache()
    return store.to_public_dict()


async def get_model_for_run(model_id: str | None = None) -> dict[str, Any]:
    return (await load_model_config_store()).model_for_run(model_id).model_dump()
