from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Request
import pytest

from api.auth.models import User
from api.routes import settings
from api.services import model_config_service
from api.tests.route_fakes import route_dependency

FAKE_REQUEST = cast(Request, None)
FAKE_USER = cast(User, object())


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


class FakeModel:
    def __init__(self, captured: dict, error: Exception | None = None) -> None:
        self.captured = captured
        self.error = error
        self.timeout = None

    async def aresponse(self, *, messages):
        self.captured["messages"] = messages
        self.captured["timeout"] = self.timeout
        if self.error:
            raise self.error
        return SimpleNamespace(content="OK")


class FakeApiError(RuntimeError):
    status_code = 401


async def async_noop(*_args, **_kwargs) -> None:
    return None


def test_model_connectivity_route_rejects_user_without_write_permission():
    actor = SimpleNamespace(role="user", is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        route_dependency(settings.router, "test_model_connectivity")(user=actor)

    assert exc.value.status_code == 403


def test_model_config_store_preserves_saved_secret_for_masked_update():
    existing = model_config_service.ModelConfigStore(
        active_model_id="custom",
        models=[
            model_config_service.ModelConfig(
                id="custom",
                name="Custom",
                model_id="model-name",
                base_url="https://api.example.com/v1",
                api_key="saved-secret",
                enabled=True,
            )
        ],
    ).with_defaults()
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
    with patch.object(settings, "build_agno_model", return_value=FakeModel(captured)):
        result = await settings.run_model_connectivity_test(model)
    assert result.success
    assert captured["timeout"] == 15
    assert len(captured["messages"]) == 2
    assert all(message.content for message in captured["messages"])


@pytest.mark.asyncio
async def test_update_models_records_request_context_in_audit_log():
    current_actor = SimpleNamespace(id="u1", role="user", is_superuser=False)
    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/api/models",
            "headers": [(b"user-agent", b"settings-browser")],
            "client": ("10.0.0.9", 44321),
        }
    )
    body = settings.ModelConfigUpdate(
        models=[
            settings.ModelConfig(
                id="m1",
                name="Model",
                model_id="model-name",
                base_url="https://api.example.com/v1",
                api_key="secret-key",
            )
        ],
        active_model_id="m1",
    )

    with (
        patch.object(
            settings,
            "save_model_config",
            AsyncMock(return_value={"ok": True}),
        ),
        patch.object(settings, "record_audit_event_async", new_callable=AsyncMock) as mocked,
    ):
        result = await settings.update_models(request, body, user=cast(User, current_actor))

    assert result == {"ok": True}
    mocked.assert_awaited_once_with(
        current_actor,
        action="settings.update",
        resource_type="models",
        metadata={"active_model_id": "m1"},
        ip_address="10.0.0.9",
        user_agent="settings-browser",
    )


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

    async def fake_load_model_config():
        return {"models": [{"id": "m1", "api_key": "saved-secret"}]}

    with (
        patch.object(
            settings,
            "load_model_config",
            fake_load_model_config,
        ),
        patch.object(settings, "build_agno_model", return_value=FakeModel(captured)) as factory,
    ):
        result = await settings.run_model_connectivity_test(model)
    assert result.success
    assert factory.call_args.args[0]["api_key"] == "saved-secret"


@pytest.mark.asyncio
async def test_update_models_awaits_model_config_save():
    body = settings.ModelConfigUpdate(
        active_model_id="m1",
        models=[
            settings.ModelConfig(
                id="m1",
                name="Model",
                model_id="model-name",
                base_url="https://api.example.com/v1",
                api_key="secret-key",
            )
        ],
    )

    save = AsyncMock(return_value={"active_model_id": "m1", "models": []})

    with (
        patch.object(
            settings,
            "save_model_config",
            save,
        ),
        patch.object(
            settings,
            "record_audit_event_async",
            async_noop,
        ),
    ):
        result = await settings.update_models(
            request=FAKE_REQUEST,
            body=body,
            user=FAKE_USER,
        )

    assert result["active_model_id"] == "m1"
    save.assert_awaited_once()

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
    error = FakeApiError("bad key")
    with patch.object(
        settings,
        "build_agno_model",
        return_value=FakeModel(captured, error),
    ):
        result = await settings.run_model_connectivity_test(model)
    assert not result.success
    assert result.status_code == 401
    assert result.message


@pytest.mark.asyncio
async def test_missing_required_model_config_values_raise_400():
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
