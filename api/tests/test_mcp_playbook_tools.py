from unittest.mock import patch
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from api.mcp.tools import playbook


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
    assert "W5_SOAR_TOKEN" in result["msg"]
