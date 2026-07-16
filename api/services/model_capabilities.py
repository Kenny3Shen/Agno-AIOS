"""Provider capability profiles: optimal defaults + safe fallbacks.

Resolution order for most knobs:
  request override → explicit model config → provider optimal → safe omit/fallback
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Provider = Literal["deepseek", "openai", "openai-compatible", "xai"]
ApiProtocol = Literal["chat-completions", "responses"]
StructuredOutputMode = Literal["native", "json"]
ReasoningEffort = Literal["minimal", "low", "medium", "high", "max"]


@dataclass(frozen=True)
class ModelCapabilities:
    provider: str
    supports_reasoning_effort: bool
    reasoning_efforts: tuple[str, ...]
    optimal_reasoning_effort: str | None
    fallback_reasoning_effort: str | None
    supports_live_search: bool
    optimal_api_protocol: str
    optimal_structured_output: str
    locks_api_protocol: bool
    # xAI: reasoning is selected by model id (…-non-reasoning…), not effort param
    reasoning_via_model_id: bool
    notes: str = ""


def _is_xai_non_reasoning_model(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return "non-reasoning" in mid or mid.endswith("-fast") and "reasoning" not in mid


def capabilities_for(
    provider: str,
    *,
    api_protocol: str | None = None,
    model_id: str = "",
) -> ModelCapabilities:
    provider = (provider or "openai-compatible").strip().lower()
    protocol = (api_protocol or "").strip().lower() or None

    if provider == "deepseek":
        return ModelCapabilities(
            provider=provider,
            supports_reasoning_effort=True,
            reasoning_efforts=("high", "max"),
            optimal_reasoning_effort="max",
            fallback_reasoning_effort="high",
            supports_live_search=False,
            optimal_api_protocol="chat-completions",
            optimal_structured_output="json",
            locks_api_protocol=True,
            reasoning_via_model_id=False,
            notes="DeepSeek 使用 high/max；structured output 固定 json。",
        )

    if provider == "openai":
        if protocol == "chat-completions":
            efforts = ("low", "medium", "high")
            optimal = "high"
        else:
            # responses default
            efforts = ("minimal", "low", "medium", "high")
            optimal = "high"
            protocol = protocol or "responses"
        return ModelCapabilities(
            provider=provider,
            supports_reasoning_effort=True,
            reasoning_efforts=efforts,
            optimal_reasoning_effort=optimal,
            fallback_reasoning_effort="medium" if "medium" in efforts else efforts[0],
            supports_live_search=False,
            optimal_api_protocol=protocol or "responses",
            optimal_structured_output="native",
            locks_api_protocol=False,
            reasoning_via_model_id=False,
            notes="OpenAI 推荐 Responses + native structured output。",
        )

    if provider == "xai":
        # Agno xAI is Chat Completions only. No reasoning_effort HTTP field in Agno/docs;
        # pick reasoning vs non-reasoning via model id.
        return ModelCapabilities(
            provider=provider,
            supports_reasoning_effort=False,
            reasoning_efforts=(),
            optimal_reasoning_effort=None,
            fallback_reasoning_effort=None,
            supports_live_search=True,
            optimal_api_protocol="chat-completions",
            optimal_structured_output="json",
            locks_api_protocol=True,
            reasoning_via_model_id=True,
            notes=(
                "xAI 推理由 model_id 决定（如含 non-reasoning 为非推理型号）；"
                "不发送 reasoning_effort。支持 Live Search（search_parameters）。"
            ),
        )

    # openai-compatible
    return ModelCapabilities(
        provider="openai-compatible",
        supports_reasoning_effort=False,
        reasoning_efforts=(),
        optimal_reasoning_effort=None,
        fallback_reasoning_effort=None,
        supports_live_search=True,
        optimal_api_protocol="chat-completions",
        optimal_structured_output="json",
        locks_api_protocol=False,
        reasoning_via_model_id=False,
        notes="兼容网关默认 Chat Completions + JSON mode；Live Search 经 extra_body。",
    )


def provider_defaults(provider: str) -> tuple[str, str, str | None]:
    """Return (api_protocol, structured_output_mode, default_reasoning_effort)."""
    caps = capabilities_for(provider)
    return (
        caps.optimal_api_protocol,
        caps.optimal_structured_output,
        caps.optimal_reasoning_effort,
    )


def resolve_reasoning_effort(
    *,
    provider: str,
    api_protocol: str | None = None,
    model_id: str = "",
    configured: str | None = None,
    override: str | None = None,
) -> str | None:
    """Pick a supported effort or fall back; never return an unsupported value."""
    caps = capabilities_for(provider, api_protocol=api_protocol, model_id=model_id)
    if not caps.supports_reasoning_effort:
        return None
    allowed = set(caps.reasoning_efforts)
    for candidate in (override, configured, caps.optimal_reasoning_effort, caps.fallback_reasoning_effort):
        if not candidate:
            continue
        value = str(candidate).strip().lower()
        if value in allowed:
            return value
    return caps.fallback_reasoning_effort


def apply_optimal_model_defaults(raw: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Fill missing (or all when force) knobs from capability optimal profile."""
    out = dict(raw)
    provider = str(out.get("provider") or "openai-compatible").strip()
    model_id = str(out.get("model_id") or "").strip()
    protocol = str(out.get("api_protocol") or "").strip() or None
    caps = capabilities_for(provider, api_protocol=protocol, model_id=model_id)

    def set_if(key: str, value: Any) -> None:
        if force or out.get(key) in (None, ""):
            out[key] = value

    if caps.locks_api_protocol or force or not out.get("api_protocol"):
        out["api_protocol"] = caps.optimal_api_protocol
    else:
        set_if("api_protocol", caps.optimal_api_protocol)

    set_if("structured_output_mode", caps.optimal_structured_output)

    if caps.supports_reasoning_effort:
        set_if("default_reasoning_effort", caps.optimal_reasoning_effort)
    else:
        out["default_reasoning_effort"] = None

    # Safe operational defaults
    set_if("retries", 4)
    set_if("delay_between_retries", 1)
    if out.get("exponential_backoff") in (None, ""):
        out["exponential_backoff"] = True

    if provider == "xai" and not str(out.get("base_url") or "").strip():
        out["base_url"] = "https://api.x.ai/v1"
    if provider == "deepseek" and not str(out.get("base_url") or "").strip():
        out["base_url"] = "https://api.deepseek.com"

    return out


def public_capabilities(
    provider: str,
    *,
    api_protocol: str | None = None,
    model_id: str = "",
) -> dict[str, Any]:
    caps = capabilities_for(provider, api_protocol=api_protocol, model_id=model_id)
    return {
        "provider": caps.provider,
        "supports_reasoning_effort": caps.supports_reasoning_effort,
        "reasoning_efforts": list(caps.reasoning_efforts),
        "optimal_reasoning_effort": caps.optimal_reasoning_effort,
        "fallback_reasoning_effort": caps.fallback_reasoning_effort,
        "supports_live_search": caps.supports_live_search,
        "optimal_api_protocol": caps.optimal_api_protocol,
        "optimal_structured_output": caps.optimal_structured_output,
        "locks_api_protocol": caps.locks_api_protocol,
        "reasoning_via_model_id": caps.reasoning_via_model_id,
        "notes": caps.notes,
        "xai_non_reasoning_model": _is_xai_non_reasoning_model(model_id)
        if caps.reasoning_via_model_id
        else False,
    }
