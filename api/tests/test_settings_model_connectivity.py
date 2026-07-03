import inspect
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fastapi import HTTPException

from api.routes import settings


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        payload: dict | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = {"content-type": "application/json"} if payload is not None else {}

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


class SettingsModelConnectivityTest(IsolatedAsyncioTestCase):
    def test_route_requires_write_permission(self):
        source = inspect.getsource(settings.test_model_connectivity)

        self.assertIn('require_permission("settings:write")', source)

    async def test_success_posts_openai_compatible_probe(self):
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

        self.assertTrue(result.success)
        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-key")
        self.assertEqual(captured["json"]["model"], "model-name")
        self.assertIn("安全防御助手", captured["json"]["messages"][0]["content"])
        self.assertIn("OK", captured["json"]["messages"][1]["content"])
        self.assertFalse(captured["json"]["stream"])

    async def test_masked_api_key_uses_saved_secret(self):
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
                "load_model_config",
                return_value={"models": [{"id": "m1", "api_key": "saved-secret"}]},
            ),
            patch.object(
                settings.httpx,
                "AsyncClient",
                return_value=FakeClient(FakeResponse(200, payload={"id": "ok"}), captured),
            ),
        ):
            result = await settings.run_model_connectivity_test(model)

        self.assertTrue(result.success)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer saved-secret")

    async def test_upstream_error_returns_message_without_raising(self):
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
                FakeResponse(401, payload={"error": {"message": "bad key"}}),
                captured,
            ),
        ):
            result = await settings.run_model_connectivity_test(model)

        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.message, "bad key")

    async def test_missing_required_model_fields_raise_400(self):
        model = settings.ModelConfig(
            id="m1",
            name="Model",
            model_id="",
            base_url="https://api.example.com/v1",
            api_key="secret-key",
        )

        with self.assertRaises(HTTPException) as context:
            await settings.run_model_connectivity_test(model)

        self.assertEqual(context.exception.status_code, 400)
