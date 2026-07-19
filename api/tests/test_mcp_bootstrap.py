from unittest.mock import AsyncMock, patch

import pytest

from api.mcp import config as mcp_config
from api.utils.async_once import AsyncOnce


@pytest.fixture(autouse=True)
def _bootstrap_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_config, "_mcp_bootstrap_once", AsyncOnce())


@pytest.mark.asyncio
async def test_bootstrap_mcp_config_runs_seed_once():
    list_rows = AsyncMock(return_value=[{"name": "playbook", "server_type": "builtin"}])
    upsert = AsyncMock()
    retire = AsyncMock()

    with (
        patch.object(mcp_config, "ensure_mcp_tables", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
        patch.object(mcp_config, "upsert_server_row", upsert),
        patch.object(mcp_config, "_retire_legacy_mcp_config_file", retire),
    ):
        await mcp_config.bootstrap_mcp_config()
        await mcp_config.bootstrap_mcp_config()

    assert list_rows.await_count == 1
    retire.assert_awaited_once()
    # builtin playbook already present; basic/hitl still seeded once
    assert upsert.await_count == 2


@pytest.mark.asyncio
async def test_retire_archives_leftover_file_without_importing_it(tmp_path, monkeypatch):
    legacy = tmp_path / "mcp_config.json"
    legacy.write_text('{"mcp_servers": [{"name": "legacy-external"}]}', encoding="utf-8")
    monkeypatch.setattr(mcp_config, "MCP_CONFIG_FILE", legacy)

    await mcp_config._retire_legacy_mcp_config_file()

    assert not legacy.exists()
    assert (tmp_path / "mcp_config.json.migrated").exists()


@pytest.mark.asyncio
async def test_enabled_mcp_servers_filters_in_sql():
    list_rows = AsyncMock(return_value=[{"name": "playbook", "enabled": True}])
    with (
        patch.object(mcp_config, "bootstrap_mcp_config", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
    ):
        rows = await mcp_config.enabled_mcp_servers()

    assert rows == [{"name": "playbook", "enabled": True}]
    list_rows.assert_awaited_once_with(enabled=True)
