from unittest.mock import AsyncMock, patch

import pytest

from api.services import model_config_service


@pytest.fixture(autouse=True)
def _clear_model_config_cache(tmp_path, monkeypatch):
    """Isolate legacy JSON path so load never archives the developer config file."""
    model_config_service._invalidate_model_config_cache()
    monkeypatch.setattr(
        model_config_service,
        "model_config_file",
        lambda: tmp_path / "model_config.json",
    )
    yield
    model_config_service._invalidate_model_config_cache()



@pytest.mark.asyncio
async def test_load_model_config_store_archives_leftover_json_without_import_when_empty(tmp_path):
    """Empty table seeds builtins only; leftover JSON is archived, never imported."""
    legacy_file = tmp_path / "model_config.json"
    legacy_file.write_text(
        """
        {
          "active_model_id": "custom",
          "models": [
            {
              "id": "custom",
              "name": "Custom",
              "model_id": "model-name",
              "base_url": "https://api.example.com/v1",
              "api_key": "secret-key",
              "structured_output_mode": "none"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    replace = AsyncMock()

    with (
        patch.object(model_config_service, "model_config_file", return_value=legacy_file),
        patch.object(model_config_service, "list_model_config_rows", AsyncMock(return_value=[])),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        store = await model_config_service.load_model_config_store()

    assert store.active_model_id == model_config_service.DEFAULT_MODELS[0].id
    assert all(model.id != "custom" for model in store.models)
    replace.assert_awaited_once()
    await_args = replace.await_args
    assert await_args is not None
    rows = await_args.args[0]
    assert all(row["id"] != "custom" for row in rows)
    assert not legacy_file.exists()
    assert (tmp_path / "model_config.json.imported").exists()


@pytest.mark.asyncio
async def test_load_model_config_store_seeds_defaults_when_empty_without_legacy_file(tmp_path):
    missing = tmp_path / "missing-model-config.json"
    replace = AsyncMock()

    with (
        patch.object(model_config_service, "model_config_file", return_value=missing),
        patch.object(model_config_service, "list_model_config_rows", AsyncMock(return_value=[])),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        store = await model_config_service.load_model_config_store()

    assert store.models
    replace.assert_awaited_once()
    assert not missing.exists()


@pytest.mark.asyncio
async def test_save_model_config_writes_postgres_rows_and_preserves_masked_secret():
    existing_store = model_config_service.ModelConfigStore.from_raw(
        {
            "active_model_id": "custom",
            "models": [
                {
                    "id": "custom",
                    "name": "Custom",
                    "model_id": "model-name",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "saved-secret",
                }
            ],
        }
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
    public_custom = next(model for model in public["models"] if model["id"] == "custom")
    assert public_custom["api_key"] == "save****cret"


def test_model_config_normalizes_new_compatible_models_to_chat_completions_json():
    model = model_config_service.ModelConfig.normalized(
        {
            "id": "custom",
            "model_id": "model-name",
            "base_url": "https://api.example.com/v1",
        },
        "fallback",
    )

    assert model.provider == "openai-compatible"
    assert model.api_protocol == "chat-completions"
    assert model.structured_output_mode == "json"
    assert model.default_reasoning_effort is None


def test_model_config_uses_native_provider_defaults_without_rewriting_explicit_values():
    deepseek = model_config_service.ModelConfig.normalized(
        {"id": "deepseek", "provider": "deepseek"}, "fallback"
    )
    openai = model_config_service.ModelConfig.normalized(
        {"id": "openai", "provider": "openai"}, "fallback"
    )
    existing_openai = model_config_service.ModelConfig.normalized(
        {
            "id": "existing-openai",
            "provider": "openai",
            "api_protocol": "chat-completions",
            "structured_output_mode": "json",
            "default_reasoning_effort": "low",
        },
        "fallback",
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
    assert (existing_openai.api_protocol, existing_openai.structured_output_mode, existing_openai.default_reasoning_effort) == (
        "chat-completions",
        "json",
        "low",
    )


def test_model_config_preserves_parallel_tool_calls_setting():
    model = model_config_service.ModelConfig.normalized(
        {
            "id": "terra",
            "provider": "openai",
            "model_id": "gpt-5.6-terra-responses-lite",
            "parallel_tool_calls": False,
        },
        "fallback",
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
async def test_load_model_config_store_does_not_rewrite_for_provider_heuristic_only():
    """Grok→xai stays on the read path; load must not rewrite rows for provider alone."""
    store = model_config_service.ModelConfigStore.default()
    rows = model_config_service._store_to_rows(store)
    # Simulate pre-migration row still stored as openai-compatible + grok id.
    for row in rows:
        if row["id"] == "xai-grok-4.5":
            row["provider"] = "openai-compatible"
            row["api_protocol"] = "responses"
            row["default_reasoning_effort"] = "high"
            break
    else:
        raise AssertionError("expected default xai-grok-4.5 row")
    replace = AsyncMock()

    with (
        patch.object(model_config_service, "list_model_config_rows", AsyncMock(return_value=rows)),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        loaded = await model_config_service.load_model_config_store()

    grok = next(model for model in loaded.models if model.id == "xai-grok-4.5")
    assert grok.provider == "xai"
    replace.assert_not_awaited()
    model_config_service._invalidate_model_config_cache()


@pytest.mark.asyncio
async def test_load_model_config_store_archives_leftover_json_when_postgres_has_rows(tmp_path):
    """Non-empty table: retire leftover model_config.json without re-importing it."""
    leftover = tmp_path / "model_config.json"
    leftover.write_text(
        '{"active_model_id":"stale","models":[{"id":"stale","name":"Stale","model_id":"m","api_key":"k"}]}',
        encoding="utf-8",
    )
    store = model_config_service.ModelConfigStore.default()
    rows = model_config_service._store_to_rows(store)
    replace = AsyncMock()

    with (
        patch.object(model_config_service, "model_config_file", return_value=leftover),
        patch.object(model_config_service, "list_model_config_rows", AsyncMock(return_value=rows)),
        patch.object(model_config_service, "replace_model_config_rows", replace),
    ):
        loaded = await model_config_service.load_model_config_store()

    assert loaded.active_model_id == store.active_model_id
    assert all(model.id != "stale" for model in loaded.models)
    assert not leftover.exists()
    assert (tmp_path / "model_config.json.imported").exists()
    if replace.await_count:
        # Integrity rewrite is allowed; must not seed leftover "stale" model.
        call = replace.await_args
        assert call is not None
        saved = call.args[0]
        assert all(row["id"] != "stale" for row in saved)


@pytest.mark.asyncio
async def test_load_model_config_store_rewrites_multiple_active_rows():
    store = model_config_service.ModelConfigStore.default()
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
    model = model_config_service.ModelConfig.normalized(
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
        "custom",
    )
    assert model.retries == 5
    assert model.delay_between_retries == 2
    assert model.exponential_backoff is False
    assert model.http_max_retries == 1

    defaults = model_config_service.ModelConfig.normalized(
        {
            "id": "custom2",
            "name": "Custom2",
            "model_id": "m2",
            "provider": "openai-compatible",
            "base_url": "https://api.example.com/v1",
        },
        "custom2",
    )
    assert defaults.retries == 4
    assert defaults.delay_between_retries == 1
    assert defaults.exponential_backoff is True
    assert defaults.http_max_retries is None



def test_legacy_grok_openai_compatible_migrates_to_xai():
    model = model_config_service.ModelConfig.normalized(
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
        "fallback",
    )
    assert model.provider == "xai"
    assert model.api_protocol == "chat-completions"
    # Legacy structured mode is kept when present (xAI supports native + json)
    assert model.structured_output_mode == "native"
    assert model.default_reasoning_effort is None
    assert model.base_url == "https://api.x.ai/v1"


def test_xai_provider_defaults_and_strips_reasoning_effort():
    model = model_config_service.ModelConfig.normalized(
        {"id": "xai", "provider": "xai", "model_id": "grok-4.5"},
        "fallback",
    )
    assert model.api_protocol == "chat-completions"
    assert model.structured_output_mode == "json"
    assert model.default_reasoning_effort is None
    assert model.base_url == "https://api.x.ai/v1"

    # xAI does not support reasoning_effort; explicit values are dropped (legacy Grok Responses).
    stripped = model_config_service.ModelConfig(
        id="xai-bad",
        provider="xai",
        model_id="grok-4.5",
        default_reasoning_effort="high",
    )
    assert stripped.default_reasoning_effort is None


def test_default_models_include_xai_grok():
    store = model_config_service.ModelConfigStore.default()
    ids = {model.id for model in store.models}
    assert "xai-grok-4.5" in ids
    grok = next(model for model in store.models if model.id == "xai-grok-4.5")
    assert grok.provider == "xai"
    assert grok.builtin is True



def test_live_search_enabled_normalized():
    model = model_config_service.ModelConfig.normalized(
        {
            "id": "xai",
            "provider": "xai",
            "model_id": "grok-4.5",
            "live_search_enabled": "true",
            "structured_output_mode": "native",
        },
        "fallback",
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
        model_config_service.ModelConfigStore.default()
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
