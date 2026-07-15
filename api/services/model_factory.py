from __future__ import annotations

from typing import Any, cast

from agno.models.base import Model
from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat, OpenAILike, OpenAIResponses

# App-private attribute on Agno Model instances. Must NOT use model.metadata:
# OpenAIResponses/OpenAIChat put model.metadata into the HTTP request body, and
# many OpenAI-compatible gateways (e.g. Grok Responses) reject `metadata`.
STRUCTURED_OUTPUT_MODE_ATTR = "_tais_structured_output_mode"


def _retry_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Agno Model + OpenAI client retry settings from model config."""
    retries = config.get("retries", 4)
    try:
        retries_i = max(0, min(10, int(retries)))
    except (TypeError, ValueError):
        retries_i = 4
    delay = config.get("delay_between_retries", 1)
    try:
        delay_i = max(0, min(60, int(delay)))
    except (TypeError, ValueError):
        delay_i = 1
    backoff = config.get("exponential_backoff", True)
    if not isinstance(backoff, bool):
        backoff = str(backoff).strip().lower() in {"1", "true", "yes", "on"}
    params: dict[str, Any] = {
        "retries": retries_i,
        "delay_between_retries": delay_i,
        "exponential_backoff": backoff,
    }
    http_max = config.get("http_max_retries")
    if http_max is not None and http_max != "":
        try:
            params["max_retries"] = max(0, min(10, int(http_max)))
        except (TypeError, ValueError):
            pass
    return params


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
        kwargs: dict[str, Any] = {"id": model_id, "api_key": api_key, **_retry_kwargs(config)}
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
            **_retry_kwargs(config),
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
                **_retry_kwargs(config),
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
            **_retry_kwargs(config),
        }
        if parallel_tool_calls is not None:
            kwargs["request_params"] = {
                "parallel_tool_calls": parallel_tool_calls,
            }
        return _with_output_mode(OpenAILike(**kwargs), output_mode)

    raise ValueError(f"Unsupported model provider: {provider}")


def get_structured_output_mode(model: Model) -> str | None:
    """Read T.A.I.S structured-output mode stored on a built model instance."""
    value = getattr(model, STRUCTURED_OUTPUT_MODE_ATTR, None)
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


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
    # Private attr only — never model.metadata (leaks into Responses/Chat API body).
    setattr(runtime_model, STRUCTURED_OUTPUT_MODE_ATTR, output_mode)
    return model
