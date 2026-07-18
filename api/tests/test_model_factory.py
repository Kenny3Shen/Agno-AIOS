from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat, OpenAILike, OpenAIResponses

from api.services.model_factory import build_agno_model, get_structured_output_mode
from api.services.model_config_service import ModelConfigStore


def config(**updates):
    return {
        "provider": "openai-compatible",
        "api_protocol": "responses",
        "model_id": "model-1",
        "api_key": "secret",
        "base_url": "https://api.example.com/v1",
        "structured_output_mode": "json",
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


def test_builds_native_models_with_default_or_override_reasoning_effort():
    deepseek = build_agno_model(
        config(provider="deepseek", default_reasoning_effort="max")
    )
    openai = build_agno_model(
        config(provider="openai", default_reasoning_effort="high"),
        reasoning_effort="low",
    )
    compatible = build_agno_model(config(default_reasoning_effort="high"))

    assert getattr(deepseek, "reasoning_effort", None) == "max"
    assert getattr(openai, "reasoning_effort", None) == "low"
    assert not hasattr(compatible, "reasoning_effort") or compatible.reasoning_effort is None


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


def test_responses_models_use_configured_parallel_tool_calls():
    native_responses = build_agno_model(
        config(
            provider="openai",
            api_protocol="responses",
            base_url="",
            parallel_tool_calls=False,
        )
    )
    compatible_responses = build_agno_model(
        config(
            provider="openai-compatible",
            api_protocol="responses",
            parallel_tool_calls=True,
        )
    )

    assert isinstance(native_responses, OpenAIResponses)
    assert native_responses.parallel_tool_calls is False
    assert isinstance(compatible_responses, OpenAIResponses)
    assert compatible_responses.parallel_tool_calls is True


def test_chat_completions_models_use_configured_parallel_tool_calls():
    native_chat = build_agno_model(
        config(
            provider="openai",
            api_protocol="chat-completions",
            base_url="",
            parallel_tool_calls=False,
        )
    )
    compatible_chat = build_agno_model(
        config(
            provider="openai-compatible",
            api_protocol="chat-completions",
            parallel_tool_calls=False,
        )
    )

    assert isinstance(native_chat, OpenAIChat)
    assert native_chat.get_request_params()["parallel_tool_calls"] is False
    assert isinstance(compatible_chat, OpenAILike)
    assert compatible_chat.get_request_params()["parallel_tool_calls"] is False


def test_builds_openai_compatible_protocol_models():
    chat = build_agno_model(config(api_protocol="chat-completions"))
    responses = build_agno_model(config(api_protocol="responses"))
    assert isinstance(chat, OpenAILike)
    assert chat.supports_native_structured_outputs is False
    assert isinstance(responses, OpenAIResponses)
    assert responses.supports_native_structured_outputs is False


def test_missing_protocol_defaults_to_chat_completions():
    model = build_agno_model({key: value for key, value in config().items() if key != "api_protocol"})

    assert isinstance(model, OpenAILike)


def test_deepseek_forces_json_chat_capabilities():
    model = build_agno_model(
        config(
            provider="deepseek",
            api_protocol="responses",
            structured_output_mode="native",
            base_url="https://api.deepseek.com",
        )
    )

    assert isinstance(model, DeepSeek)
    assert get_structured_output_mode(model) == "json"
    assert getattr(model, "metadata", None) in (None, {})
    assert model.supports_native_structured_outputs is False


def test_none_output_mode_normalizes_to_json_mode():
    model = build_agno_model(config(structured_output_mode="none"))

    assert get_structured_output_mode(model) == "json"
    assert getattr(model, "metadata", None) in (None, {})
    assert model.supports_native_structured_outputs is False


def test_structured_output_mode_does_not_pollute_request_metadata():
    """Grok/xAI Responses rejects HTTP body field ``metadata``."""
    responses = build_agno_model(
        config(
            provider="openai-compatible",
            api_protocol="responses",
            structured_output_mode="native",
        )
    )
    chat = build_agno_model(
        config(
            provider="openai-compatible",
            api_protocol="chat-completions",
            structured_output_mode="json",
        )
    )

    assert isinstance(responses, OpenAIResponses)
    assert isinstance(chat, OpenAILike)
    assert get_structured_output_mode(responses) == "native"
    assert get_structured_output_mode(chat) == "json"
    assert "metadata" not in responses.get_request_params()
    assert "metadata" not in chat.get_request_params()
    assert getattr(responses, "metadata", None) in (None, {})
    assert getattr(chat, "metadata", None) in (None, {})


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


def test_applies_retry_settings_to_responses_and_chat():
    responses = build_agno_model(
        config(
            api_protocol="responses",
            retries=4,
            delay_between_retries=2,
            exponential_backoff=True,
            http_max_retries=1,
        )
    )
    chat = build_agno_model(
        config(
            api_protocol="chat-completions",
            retries=0,
            delay_between_retries=5,
            exponential_backoff=False,
            http_max_retries=3,
        )
    )
    assert isinstance(responses, OpenAIResponses)
    assert isinstance(chat, OpenAILike)
    assert responses.retries == 4
    assert responses.delay_between_retries == 2
    assert responses.exponential_backoff is True
    assert responses.max_retries == 1
    assert chat.retries == 0
    assert chat.delay_between_retries == 5
    assert chat.exponential_backoff is False
    assert chat.max_retries == 3


def test_default_retries_when_config_omits_retry_fields():
    model = build_agno_model(config())
    assert model.retries == 4
    assert model.delay_between_retries == 1
    assert model.exponential_backoff is True
    assert getattr(model, "max_retries", None) is None


def test_invalid_retry_fields_fall_back_without_max_retries():
    model = build_agno_model(
        config(
            retries="nope",
            delay_between_retries="slow",
            http_max_retries="many",
        )
    )
    assert model.retries == 4
    assert model.delay_between_retries == 1
    assert getattr(model, "max_retries", None) is None


def test_xai_provider_uses_official_agno_class():
    from agno.models.xai import xAI

    model = build_agno_model(
        config(
            provider="xai",
            model_id="grok-4.5",
            base_url="",
            api_protocol="responses",  # ignored; xAI is Chat Completions
            structured_output_mode="json",
        )
    )
    assert isinstance(model, xAI)
    assert model.id == "grok-4.5"
    assert str(model.base_url).rstrip("/") == "https://api.x.ai/v1"
    assert model.retries == 4
    assert get_structured_output_mode(model) == "json"
    assert getattr(model, "metadata", None) in (None, {})


def test_xai_respects_custom_base_url_and_parallel_tools():
    from agno.models.xai import xAI

    model = build_agno_model(
        config(
            provider="xai",
            model_id="grok-4.5",
            base_url="https://api.x.ai/v1",
            parallel_tool_calls=False,
        )
    )
    assert isinstance(model, xAI)
    assert model.request_params == {"parallel_tool_calls": False}



def test_xai_live_search_sets_search_parameters():
    from agno.models.xai import xAI

    model = build_agno_model(
        config(
            provider="xai",
            model_id="grok-4.5",
            live_search_enabled=True,
        )
    )
    assert isinstance(model, xAI)
    assert model.search_parameters == {
        "mode": "on",
        "max_search_results": 20,
        "return_citations": True,
    }


def test_compatible_live_search_uses_extra_body():
    model = build_agno_model(
        config(
            provider="openai-compatible",
            api_protocol="chat-completions",
            live_search_enabled=True,
        )
    )
    assert isinstance(model, OpenAILike)
    assert model.request_params is not None
    assert model.request_params["extra_body"]["search_parameters"]["mode"] == "on"



def test_resolve_reasoning_effort_falls_back_for_invalid_override():
    model = build_agno_model(
        config(provider="deepseek", default_reasoning_effort="max"),
        reasoning_effort="low",  # not supported by deepseek
    )
    from agno.models.deepseek import DeepSeek

    assert isinstance(model, DeepSeek)
    assert model.reasoning_effort == "max"  # invalid override skipped; configured max used
