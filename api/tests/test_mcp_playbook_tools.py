from unittest.mock import patch
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from api.mcp.tools import playbook


class ClosingAdapter:
    def __init__(self) -> None:
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        self.closed = True

    async def list_workflows(self) -> dict:
        return {"code": 0, "msg": "ok", "data": []}

    async def get_method_params(self, _method_id: str) -> dict:
        return {"code": 0, "msg": "ok", "data": []}

    async def invoke_method(self, _method_id: str, _params: dict | None = None) -> dict:
        return {"code": 0, "msg": "ok", "data": {"exec_id": "exec-1"}}

    async def get_exec_result(self, _exec_id: str) -> dict:
        return {"code": 0, "msg": "ok", "data": {"status": "SUCCESS"}}


@pytest.mark.asyncio
async def test_playbook_tool_loads_runtime_env_before_adapter_creation() -> None:
    calls: list[str] = []

    async def fake_load_runtime_env_async() -> None:
        calls.append("loaded")

    fake_settings = SimpleNamespace(
        w5_soar_token=SecretStr(""),
        w5_api_base="",
        octomation_token=SecretStr(""),
        octomation_api_base="",
    )

    with (
        patch.object(playbook, "load_runtime_env_async", fake_load_runtime_env_async),
        patch.object(playbook, "get_settings", return_value=fake_settings),
    ):
        result = await playbook.list_workflows("w5-soar")

    assert calls == ["loaded"]
    assert result["code"] == -4


@pytest.mark.parametrize(
    ("tool_call", "args"),
    [
        (playbook.list_workflows, ("w5-soar",)),
        (playbook.get_method_params, ("w5-soar", "method-1")),
        (playbook.invoke_method, ("w5-soar", "method-1", {"host": "example"})),
        (playbook.get_exec_result, ("w5-soar", "exec-1")),
    ],
)
@pytest.mark.asyncio
async def test_playbook_tools_close_adapter_after_call(tool_call, args) -> None:
    adapter = ClosingAdapter()

    async def fake_get_adapter(_platform: str):
        return adapter

    with patch.object(playbook, "get_adapter", fake_get_adapter):
        result = await tool_call(*args)

    assert result["code"] == 0
    assert adapter.closed
