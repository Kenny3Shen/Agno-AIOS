from unittest.mock import AsyncMock, patch

import pytest

from api.services import model_config_service


@pytest.mark.asyncio
async def test_load_model_config_store_imports_legacy_json_when_postgres_is_empty(tmp_path):
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

    assert store.active_model_id == "custom"
    custom = next(model for model in store.models if model.id == "custom")
    assert custom.structured_output_mode == "json"
    replace.assert_awaited_once()
    await_args = replace.await_args
    assert await_args is not None
    rows = await_args.args[0]
    assert any(row["id"] == "custom" and row["active"] for row in rows)
    assert {row["structured_output_mode"] for row in rows} <= {"native", "json"}


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


def test_model_config_normalizes_new_compatible_models_to_responses_json():
    model = model_config_service.ModelConfig.normalized(
        {
            "id": "custom",
            "model_id": "model-name",
            "base_url": "https://api.example.com/v1",
        },
        "fallback",
    )

    assert model.provider == "openai-compatible"
    assert model.api_protocol == "responses"
    assert model.structured_output_mode == "json"


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
