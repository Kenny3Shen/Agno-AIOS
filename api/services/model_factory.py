from __future__ import annotations

from typing import Any, cast

from agno.models.base import Model
from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat, OpenAILike, OpenAIResponses


def build_agno_model(config: dict[str, Any]) -> Model:
    provider = str(config.get("provider") or "openai-compatible")
    protocol = str(config.get("api_protocol") or "chat-completions")
    model_id = str(config.get("model_id") or "").strip()
    api_key = str(config.get("api_key") or "").strip() or None
    base_url = str(config.get("base_url") or "").strip() or None
    output_mode = str(config.get("structured_output_mode") or "none")
    native_outputs = output_mode == "native"

    if provider == "deepseek":
        if protocol != "chat-completions":
            raise ValueError("DeepSeek native model only supports chat-completions")
        kwargs: dict[str, Any] = {"id": model_id, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return _with_output_mode(DeepSeek(**kwargs), output_mode)

    if provider == "openai":
        model_class = OpenAIResponses if protocol == "responses" else OpenAIChat
        return _with_output_mode(
            model_class(id=model_id, api_key=api_key, base_url=base_url),
            output_mode,
        )

    if provider == "openai-compatible":
        if not base_url:
            raise ValueError("OpenAI-compatible model requires base_url")
        if protocol == "responses":
            return _with_output_mode(
                OpenAIResponses(
                    id=model_id,
                    api_key=api_key,
                    base_url=base_url,
                    supports_native_structured_outputs=native_outputs,
                ),
                output_mode,
            )
        return _with_output_mode(
            OpenAILike(
                id=model_id,
                api_key=api_key,
                base_url=base_url,
                supports_native_structured_outputs=native_outputs,
            ),
            output_mode,
        )

    raise ValueError(f"Unsupported model provider: {provider}")


def _with_output_mode(model: Model, output_mode: str) -> Model:
    runtime_model = cast(Any, model)
    metadata = dict(runtime_model.metadata or {})
    metadata["agno_aios.structured_output_mode"] = output_mode
    runtime_model.metadata = metadata
    return model
