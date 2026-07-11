from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat, OpenAILike, OpenAIResponses
import pytest

from api.services.model_factory import build_agno_model
from api.services.model_config_service import ModelConfigStore


def config(**updates):
    return {
        "provider": "openai-compatible",
        "api_protocol": "chat-completions",
        "model_id": "model-1",
        "api_key": "secret",
        "base_url": "https://api.example.com/v1",
        "structured_output_mode": "none",
        **updates,
    }


def test_builds_native_deepseek_with_correct_capabilities():
    model = build_agno_model(
        config(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            structured_output_mode="json",
        )
    )
    assert isinstance(model, DeepSeek)
    assert model.supports_native_structured_outputs is False


def test_builds_openai_chat_and_responses_models():
    assert isinstance(
        build_agno_model(
            config(
                provider="openai",
                api_protocol="chat-completions",
                base_url="",
                structured_output_mode="native",
            )
        ),
        OpenAIChat,
    )
    assert isinstance(
        build_agno_model(
            config(
                provider="openai",
                api_protocol="responses",
                base_url="",
                structured_output_mode="native",
            )
        ),
        OpenAIResponses,
    )


def test_builds_openai_compatible_protocol_models():
    chat = build_agno_model(config())
    responses = build_agno_model(config(api_protocol="responses"))
    assert isinstance(chat, OpenAILike)
    assert chat.supports_native_structured_outputs is False
    assert isinstance(responses, OpenAIResponses)


def test_rejects_unsupported_deepseek_protocol():
    with pytest.raises(ValueError, match="chat-completions"):
        build_agno_model(config(provider="deepseek", api_protocol="responses"))


def test_native_provider_does_not_require_custom_base_url():
    store = ModelConfigStore.from_raw(
        {
            "active_model_id": "openai",
            "models": [
                config(
                    id="openai",
                    name="OpenAI",
                    provider="openai",
                    base_url="",
                )
            ],
        }
    )

    assert store.model_for_run().provider == "openai"
