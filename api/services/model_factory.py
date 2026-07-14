from __future__ import annotations

from typing import Any, cast

from agno.models.base import Model
from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat, OpenAILike, OpenAIResponses


def build_agno_model(
    config: dict[str, Any], *, reasoning_effort: str | None = None
) -> Model:
    provider = str(config.get("provider") or "openai-compatible")
    protocol = str(config.get("api_protocol") or "chat-completions")
    model_id = str(config.get("model_id") or "").strip()
    api_key = str(config.get("api_key") or "").strip() or None
    base_url = str(config.get("base_url") or "").strip() or None
    output_mode = _output_mode(config.get("structured_output_mode"))
    native_outputs = output_mode == "native"
    parallel_tool_calls = _parallel_tool_calls(config.get("parallel_tool_calls"))
    effective_reasoning_effort = (
        reasoning_effort
        if reasoning_effort is not None
        else _reasoning_effort(config.get("default_reasoning_effort"))
    )

    if provider == "deepseek":
        kwargs: dict[str, Any] = {"id": model_id, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if effective_reasoning_effort:
            kwargs["reasoning_effort"] = effective_reasoning_effort
        return _with_output_mode(DeepSeek(**kwargs), "json")

    if provider == "openai":
        kwargs: dict[str, Any] = {
            "id": model_id,
            "api_key": api_key,
            "base_url": base_url,
            "supports_native_structured_outputs": native_outputs,
        }
        if effective_reasoning_effort:
            kwargs["reasoning_effort"] = effective_reasoning_effort
        if protocol == "responses":
            if parallel_tool_calls is not None:
                kwargs["parallel_tool_calls"] = parallel_tool_calls
            return _with_output_mode(OpenAIResponses(**kwargs), output_mode)
        if parallel_tool_calls is not None:
            kwargs["request_params"] = {
                "parallel_tool_calls": parallel_tool_calls,
            }
        return _with_output_mode(OpenAIChat(**kwargs), output_mode)

    if provider == "openai-compatible":
        if not base_url:
            raise ValueError("OpenAI-compatible model requires base_url")
        if protocol == "responses":
            kwargs: dict[str, Any] = {
                "id": model_id,
                "api_key": api_key,
                "base_url": base_url,
                "supports_native_structured_outputs": native_outputs,
            }
            if parallel_tool_calls is not None:
                kwargs["parallel_tool_calls"] = parallel_tool_calls
            return _with_output_mode(
                OpenAIResponses(**kwargs),
                output_mode,
            )
        kwargs: dict[str, Any] = {
            "id": model_id,
            "api_key": api_key,
            "base_url": base_url,
            "supports_native_structured_outputs": native_outputs,
        }
        if parallel_tool_calls is not None:
            kwargs["request_params"] = {
                "parallel_tool_calls": parallel_tool_calls,
            }
        return _with_output_mode(OpenAILike(**kwargs), output_mode)

    raise ValueError(f"Unsupported model provider: {provider}")


def _output_mode(value: Any) -> str:
    output_mode = str(value or "").strip().lower()
    if output_mode in {"", "none"}:
        return "json"
    if output_mode not in {"native", "json"}:
        return "json"
    return output_mode


def _reasoning_effort(value: Any) -> str | None:
    effort = str(value or "").strip().lower()
    return effort or None


def _parallel_tool_calls(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _with_output_mode(model: Model, output_mode: str) -> Model:
    runtime_model = cast(Any, model)
    metadata = dict(runtime_model.metadata or {})
    metadata["agno_aios.structured_output_mode"] = output_mode
    runtime_model.metadata = metadata
    return model
