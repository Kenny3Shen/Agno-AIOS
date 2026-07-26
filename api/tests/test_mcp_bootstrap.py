from unittest.mock import AsyncMock, patch

import pytest

from api.mcp import config as mcp_config
from api.utils.async_once import AsyncOnce


@pytest.fixture(autouse=True)
def _bootstrap_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_config, "_mcp_bootstrap_once", AsyncOnce())


@pytest.mark.asyncio
async def test_bootstrap_mcp_config_runs_seed_once():
    list_rows = AsyncMock(
        return_value=[
            {"name": "basic", "server_type": "builtin"},
            {"name": "playbook", "server_type": "builtin"},
            {"name": "future-built-in", "server_type": "builtin"},
            {"name": "external-scanner", "server_type": "external"},
        ]
    )
    upsert = AsyncMock()

    with (
        patch.object(mcp_config, "ensure_mcp_tables", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
        patch.object(mcp_config, "upsert_server_row", upsert),
    ):
        await mcp_config.bootstrap_mcp_config()
        await mcp_config.bootstrap_mcp_config()

    assert list_rows.await_count == 1
    # Startup only seeds current built-ins; it no longer mutates historic rows.
    upsert.assert_awaited_once()
    upsert_call = upsert.await_args
    assert upsert_call is not None
    assert upsert_call.args[0]["name"] == "hitl"

@pytest.mark.asyncio
async def test_enabled_mcp_servers_filters_in_sql():
    list_rows = AsyncMock(return_value=[{"name": "basic", "enabled": True}])
    with (
        patch.object(mcp_config, "bootstrap_mcp_config", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
    ):
        rows = await mcp_config.enabled_mcp_servers()

    assert rows == [{"name": "basic", "enabled": True}]
    list_rows.assert_awaited_once_with(enabled=True)
