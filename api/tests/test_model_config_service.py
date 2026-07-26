from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from api.services import model_config_service


@pytest.fixture(autouse=True)
def _clear_model_config_cache():
    model_config_service._invalidate_model_config_cache()
    yield
    model_config_service._invalidate_model_config_cache()


@pytest.mark.asyncio
async def test_load_model_config_store_returns_empty_store_without_persisting():
    replace = AsyncMock()

    with (
        patch.object(model_config_service, "list_model_config_rows", AsyncMock(return_value=[])),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        store = await model_config_service.load_model_config_store()

    assert store.models == []
    assert store.active_model_id == ""
    replace.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_model_config_writes_postgres_rows_and_preserves_masked_secret():
    existing_store = model_config_service.ModelConfigStore(
        active_model_id="custom",
        models=[
            model_config_service.ModelConfig(
                id="custom",
                name="Custom",
                model_id="model-name",
                base_url="https://api.example.com/v1",
                api_key="saved-secret",
            )
        ],
    )
    existing_rows = model_config_service._store_to_rows(existing_store)
    replace = AsyncMock()

    submitted = model_config_service.ModelConfig(
        id="custom",
        name="Custom",
        model_id="model-name",
        base_url="https://api.example.com/v1",
        api_key="save****cret",
    )

    with (
        patch.object(
            model_config_service,
            "list_model_config_rows",
            AsyncMock(side_effect=[existing_rows, existing_rows]),
        ),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        public = await model_config_service.save_model_config([submitted], "custom")

    replace.assert_awaited_once()
    await_args = replace.await_args
    assert await_args is not None
    rows = await_args.args[0]
    custom_row = next(row for row in rows if row["id"] == "custom")
    assert custom_row["api_key"] == "saved-secret"
    assert custom_row["active"] is True
    assert custom_row.get("memory_manager") is False
    public_custom = next(model for model in public["models"] if model["id"] == "custom")
    assert public_custom["api_key"] == "save****cret"
    assert public.get("memory_model_id") in (None, "")


@pytest.mark.asyncio
async def test_save_model_config_sets_memory_manager_flag():
    model = model_config_service.ModelConfig(
        id="memory-model",
        name="Memory model",
        model_id="model-name",
        base_url="https://api.example.com/v1",
        api_key="saved-secret",
    )
    existing_store = model_config_service.ModelConfigStore(
        active_model_id=model.id,
        memory_model_id="",
        models=[model],
    )
    existing_rows = model_config_service._store_to_rows(existing_store)
    replace = AsyncMock()

    with (
        patch.object(
            model_config_service,
            "list_model_config_rows",
            AsyncMock(side_effect=[existing_rows, existing_rows]),
        ),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        public = await model_config_service.save_model_config(
            [model],
            model.id,
            memory_model_id=model.id,
        )

    replace.assert_awaited_once()
    assert replace.await_args is not None
    rows = replace.await_args.args[0]
    mm_rows = [row for row in rows if row.get("memory_manager")]
    assert len(mm_rows) == 1
    assert mm_rows[0]["id"] == model.id
    assert public["memory_model_id"] == model.id


def test_model_config_normalizes_new_compatible_models_to_chat_completions_json():
    model = model_config_service.ModelConfig.from_row(
        {
            "id": "custom",
            "model_id": "model-name",
            "base_url": "https://api.example.com/v1",
        },
    )

    assert model.provider == "openai-compatible"
    assert model.api_protocol == "chat-completions"
    assert model.structured_output_mode == "json"
    assert model.default_reasoning_effort is None


def test_model_config_requires_explicit_id():
    with pytest.raises(ValueError, match="model config id is required"):
        model_config_service.ModelConfig.from_row({"model_id": "model-name"})


def test_model_config_rejects_the_retired_builtin_field():
    with pytest.raises(ValidationError, match="builtin"):
        model_config_service.ModelConfig.model_validate(
            {
                "id": "custom",
                "model_id": "model-name",
                "base_url": "https://api.example.com/v1",
                "builtin": True,
            }
        )


def test_model_config_store_rejects_retired_fields() -> None:
    with pytest.raises(ValidationError, match="builtin"):
        model_config_service.ModelConfigStore.model_validate(
            {"models": [], "builtin": False}
        )


def test_model_config_rejects_retired_structured_output_mode():
    with pytest.raises(ValidationError, match="structured_output_mode"):
        model_config_service.ModelConfig.from_row(
            {
                "id": "custom",
                "model_id": "model-name",
                "provider": "openai-compatible",
                "structured_output_mode": "none",
                "base_url": "https://api.example.com/v1",
            }
        )


def test_model_config_does_not_guess_native_provider_from_model_identity():
    model = model_config_service.ModelConfig.from_row(
        {
            "id": "unclassified-deepseek",
            "model_id": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
        },
    )

    assert model.provider == "openai-compatible"
    assert model.api_protocol == "chat-completions"


def test_model_config_uses_native_provider_defaults_without_rewriting_explicit_values():
    deepseek = model_config_service.ModelConfig.from_row(
        {"id": "deepseek", "provider": "deepseek"}
    )
    openai = model_config_service.ModelConfig.from_row(
        {"id": "openai", "provider": "openai"}
    )
    submitted_openai = model_config_service.ModelConfig(
        id="submitted-openai",
        provider="openai",
        model_id="gpt-5-mini",
    )
    existing_openai = model_config_service.ModelConfig.from_row(
        {
            "id": "existing-openai",
            "provider": "openai",
            "api_protocol": "chat-completions",
            "structured_output_mode": "json",
            "default_reasoning_effort": "low",
        },
    )

    assert (deepseek.api_protocol, deepseek.structured_output_mode, deepseek.default_reasoning_effort) == (
        "chat-completions",
        "json",
        "max",
    )
    assert (openai.api_protocol, openai.structured_output_mode, openai.default_reasoning_effort) == (
        "responses",
        "native",
        "high",
    )
    assert (
        submitted_openai.api_protocol,
        submitted_openai.structured_output_mode,
        submitted_openai.default_reasoning_effort,
        submitted_openai.retries,
        submitted_openai.delay_between_retries,
        submitted_openai.exponential_backoff,
    ) == ("responses", "native", "high", 4, 1, True)
    assert (existing_openai.api_protocol, existing_openai.structured_output_mode, existing_openai.default_reasoning_effort) == (
        "chat-completions",
        "json",
        "low",
    )


def test_model_config_preserves_parallel_tool_calls_setting():
    model = model_config_service.ModelConfig.from_row(
        {
            "id": "terra",
            "provider": "openai",
            "model_id": "gpt-5.6-terra-responses-lite",
            "parallel_tool_calls": False,
        },
    )
    store = model_config_service.ModelConfigStore(
        active_model_id=model.id,
        models=[model],
    )

    assert model.parallel_tool_calls is False
    assert model_config_service._store_to_rows(store)[0]["parallel_tool_calls"] is False


def test_model_config_strips_reasoning_effort_for_unsupported_providers():
    model = model_config_service.ModelConfig(
        id="compatible",
        provider="openai-compatible",
        base_url="https://api.example.com/v1",
        default_reasoning_effort="high",
    )
    assert model.default_reasoning_effort is None

    xai = model_config_service.ModelConfig(
        id="xai-bad",
        provider="xai",
        model_id="grok-4.5",
        default_reasoning_effort="high",
    )
    assert xai.default_reasoning_effort is None


@pytest.mark.asyncio
async def test_load_model_config_store_rewrites_multiple_active_rows():
    store = model_config_service.ModelConfigStore(
        active_model_id="first",
        models=[
            model_config_service.ModelConfig(
                id="first",
                model_id="first-model",
                base_url="https://api.example.com/v1",
            ),
            model_config_service.ModelConfig(
                id="second",
                model_id="second-model",
                base_url="https://api.example.com/v1",
            ),
        ],
    )
    rows = model_config_service._store_to_rows(store)
    rows[1]["active"] = True
    replace = AsyncMock()

    with (
        patch.object(model_config_service, "list_model_config_rows", AsyncMock(return_value=rows)),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        loaded = await model_config_service.load_model_config_store()

    assert loaded.active_model_id == rows[0]["id"]
    replace.assert_awaited_once()
    await_args = replace.await_args
    assert await_args is not None
    saved_rows = await_args.args[0]
    assert sum(1 for row in saved_rows if row["active"]) == 1


def test_model_config_normalizes_retry_fields():
    model = model_config_service.ModelConfig.from_row(
        {
            "id": "custom",
            "name": "Custom",
            "model_id": "m1",
            "provider": "openai-compatible",
            "base_url": "https://api.example.com/v1",
            "retries": "5",
            "delay_between_retries": "2",
            "exponential_backoff": "false",
            "http_max_retries": "1",
        },
    )
    assert model.retries == 5
    assert model.delay_between_retries == 2
    assert model.exponential_backoff is False
    assert model.http_max_retries == 1

    defaults = model_config_service.ModelConfig.from_row(
        {
            "id": "custom2",
            "name": "Custom2",
            "model_id": "m2",
            "provider": "openai-compatible",
            "base_url": "https://api.example.com/v1",
        },
    )
    assert defaults.retries == 4
    assert defaults.delay_between_retries == 1
    assert defaults.exponential_backoff is True
    assert defaults.http_max_retries is None



def test_model_config_does_not_guess_xai_from_compatible_input():
    model = model_config_service.ModelConfig.from_row(
        {
            "id": "grok",
            "name": "Grok",
            "model_id": "grok-4.5",
            "provider": "openai-compatible",
            "api_protocol": "responses",
            "structured_output_mode": "native",
            "default_reasoning_effort": "high",
            "base_url": "https://api.x.ai/v1",
            "api_key": "xai-key",
        },
    )
    assert model.provider == "openai-compatible"
    assert model.api_protocol == "responses"
    assert model.structured_output_mode == "native"
    assert model.default_reasoning_effort is None
    assert model.base_url == "https://api.x.ai/v1"


def test_xai_provider_defaults_and_strips_reasoning_effort():
    model = model_config_service.ModelConfig.from_row(
        {"id": "xai", "provider": "xai", "model_id": "grok-4.5"},
    )
    assert model.api_protocol == "chat-completions"
    assert model.structured_output_mode == "json"
    assert model.default_reasoning_effort is None
    assert model.base_url == "https://api.x.ai/v1"

    # xAI does not support reasoning_effort; explicit values are dropped.
    stripped = model_config_service.ModelConfig(
        id="xai-bad",
        provider="xai",
        model_id="grok-4.5",
        default_reasoning_effort="high",
    )
    assert stripped.default_reasoning_effort is None


def test_default_model_store_is_intentionally_empty():
    store = model_config_service.ModelConfigStore.default()
    assert store.models == []
    assert store.active_model_id == ""


def test_empty_submitted_models_stay_empty_and_clear_stale_selection():
    existing = model_config_service.ModelConfigStore(
        active_model_id="configured",
        memory_model_id="configured",
        eval_judge_model_id="configured",
        models=[
            model_config_service.ModelConfig(
                id="configured",
                model_id="model-name",
                base_url="https://api.example.com/v1",
                api_key="saved-secret",
            )
        ],
    )

    store = model_config_service.ModelConfigStore.from_submitted(
        [],
        active_model_id="configured",
        memory_model_id="configured",
        eval_judge_model_id="configured",
        existing=existing,
    )

    assert store.models == []
    assert store.active_model_id == ""
    assert store.memory_model_id == ""
    assert store.eval_judge_model_id == ""


def test_model_for_run_explains_when_administrator_has_not_configured_any_model():
    with pytest.raises(ValueError, match="请先在设置中添加并启用模型"):
        model_config_service.ModelConfigStore.default().model_for_run()


@pytest.mark.asyncio
async def test_eval_judge_uses_active_model_when_no_dedicated_model_is_pinned():
    store = model_config_service.ModelConfigStore(
        active_model_id="active",
        models=[
            model_config_service.ModelConfig(
                id="active",
                model_id="model-name",
                base_url="https://api.example.com/v1",
                api_key="configured-secret",
            )
        ],
    )
    with patch.object(
        model_config_service,
        "load_model_config_store",
        AsyncMock(return_value=store),
    ):
        assert await model_config_service.get_eval_judge_model_id() == "active"



def test_live_search_enabled_normalized():
    model = model_config_service.ModelConfig.from_row(
        {
            "id": "xai",
            "provider": "xai",
            "model_id": "grok-4.5",
            "live_search_enabled": "true",
            "structured_output_mode": "native",
        },
    )
    assert model.live_search_enabled is True
    assert model.structured_output_mode == "native"



def test_capability_profiles_resolve_optimal_and_fallback():
    from api.services.model_capabilities import (
        capabilities_for,
        resolve_reasoning_effort,
        apply_optimal_model_defaults,
    )

    assert capabilities_for("xai").supports_reasoning_effort is False
    assert capabilities_for("xai").supports_live_search is True
    assert capabilities_for("xai").reasoning_via_model_id is True

    assert resolve_reasoning_effort(provider="deepseek", override="bogus") == "max"
    assert resolve_reasoning_effort(provider="deepseek", override="max") == "max"
    assert resolve_reasoning_effort(provider="openai", api_protocol="responses", configured="minimal") == "minimal"
    assert resolve_reasoning_effort(provider="xai", override="high") is None

    filled = apply_optimal_model_defaults({"provider": "openai", "id": "o"})
    assert filled["api_protocol"] == "responses"
    assert filled["structured_output_mode"] == "native"
    assert filled["default_reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_load_model_config_store_uses_short_ttl_cache():
    model_config_service._invalidate_model_config_cache()
    rows = model_config_service._store_to_rows(
        model_config_service.ModelConfigStore(
            active_model_id="custom",
            models=[
                model_config_service.ModelConfig(
                    id="custom",
                    model_id="model-name",
                    base_url="https://api.example.com/v1",
                )
            ],
        )
    )
    list_rows = AsyncMock(return_value=rows)

    with (
        patch.object(model_config_service, "list_model_config_rows", list_rows),
        patch.object(model_config_service, "replace_model_config_rows", AsyncMock()),
    ):
        first = await model_config_service.load_model_config_store()
        second = await model_config_service.load_model_config_store()

    assert first is second
    assert list_rows.await_count == 1
    model_config_service._invalidate_model_config_cache()
