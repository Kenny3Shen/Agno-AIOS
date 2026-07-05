import inspect
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from api.routes import settings
from api.services import model_config_service
import pytest


class FakeResponse:
    def __init__(
        self, status_code: int, *, payload: dict | None = None, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = (
            {"content-type": "application/json"} if payload is not None else {}
        )

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse, captured: dict) -> None:
        self.response = response
        self.captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return None

    async def post(self, url: str, *, headers: dict, json: dict):
        self.captured.update({"url": url, "headers": headers, "json": json})
        return self.response


def test_route_requires_write_permission():
    source = inspect.getsource(settings.test_model_connectivity)
    assert 'require_permission("settings:write")' in source


def test_settings_route_reuses_model_config_service_schema():
    assert settings.ModelConfig is model_config_service.ModelConfig
    assert settings.ModelConfigUpdate is model_config_service.ModelConfigUpdate


def test_model_config_store_preserves_saved_secret_for_masked_update():
    existing = model_config_service.ModelConfigStore.from_raw(
        {
            "active_model_id": "custom",
            "models": [
                {
                    "id": "custom",
                    "name": "Custom",
                    "model_id": "model-name",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "saved-secret",
                    "enabled": True,
                }
            ],
        }
    )
    submitted = model_config_service.ModelConfig(
        id="custom",
        name="Custom",
        model_id="model-name",
        base_url="https://api.example.com/v1",
        api_key="save****cret",
    )

    saved = model_config_service.ModelConfigStore.from_submitted(
        [submitted],
        active_model_id="custom",
        existing=existing,
    )
    saved_custom = next(model for model in saved.models if model.id == "custom")
    public_custom = next(
        model for model in saved.to_public_dict()["models"] if model["id"] == "custom"
    )

    assert saved_custom.api_key == "saved-secret"
    assert next(
        model for model in saved.to_storage_dict()["models"] if model["id"] == "custom"
    )["api_key"] == "saved-secret"
    assert public_custom["api_key"] == "save****cret"
    assert public_custom["configured"] is True


@pytest.mark.asyncio
async def test_success_posts_openai_compatible_probe():
    captured: dict = {}
    model = settings.ModelConfig(
        id="m1",
        name="Model",
        model_id="model-name",
        base_url="https://api.example.com/v1",
        api_key="secret-key",
    )
    with patch.object(
        settings.httpx,
        "AsyncClient",
        return_value=FakeClient(FakeResponse(200, payload={"id": "ok"}), captured),
    ):
        result = await settings.run_model_connectivity_test(model)
    assert result.success
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["json"]["model"] == "model-name"
    assert "安全防御助手" in captured["json"]["messages"][0]["content"]
    assert "OK" in captured["json"]["messages"][1]["content"]
    assert not captured["json"]["stream"]


@pytest.mark.asyncio
async def test_masked_api_key_uses_saved_secret():
    captured: dict = {}
    model = settings.ModelConfig(
        id="m1",
        name="Model",
        model_id="model-name",
        base_url="https://api.example.com/v1",
        api_key="real********mask",
    )
    with (
        patch.object(
            settings,
            "load_model_config_async",
            new_callable=AsyncMock,
            return_value={"models": [{"id": "m1", "api_key": "saved-secret"}]},
        ),
        patch.object(
            settings.httpx,
            "AsyncClient",
            return_value=FakeClient(FakeResponse(200, payload={"id": "ok"}), captured),
        ),
    ):
        result = await settings.run_model_connectivity_test(model)
    assert result.success
    assert captured["headers"]["Authorization"] == "Bearer saved-secret"


@pytest.mark.asyncio
async def test_upstream_error_returns_message_without_raising():
    captured: dict = {}
    model = settings.ModelConfig(
        id="m1",
        name="Model",
        model_id="model-name",
        base_url="https://api.example.com/v1",
        api_key="secret-key",
    )
    with patch.object(
        settings.httpx,
        "AsyncClient",
        return_value=FakeClient(
            FakeResponse(401, payload={"error": {"message": "bad key"}}), captured
        ),
    ):
        result = await settings.run_model_connectivity_test(model)
    assert not result.success
    assert result.status_code == 401
    assert result.message == "bad key"


@pytest.mark.asyncio
async def test_missing_required_model_fields_raise_400():
    model = settings.ModelConfig(
        id="m1",
        name="Model",
        model_id="",
        base_url="https://api.example.com/v1",
        api_key="secret-key",
    )
    with pytest.raises(HTTPException) as context:
        await settings.run_model_connectivity_test(model)
    assert context.value.status_code == 400
