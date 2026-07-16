from unittest.mock import AsyncMock, patch

import pytest

from api.mcp import config as mcp_config


@pytest.fixture(autouse=True)
def _reset_bootstrap_flag():
    mcp_config._BOOTSTRAP_DONE = False
    yield
    mcp_config._BOOTSTRAP_DONE = False


@pytest.mark.asyncio
async def test_bootstrap_mcp_config_runs_seed_once():
    list_rows = AsyncMock(return_value=[{"name": "playbook", "server_type": "builtin"}])
    upsert = AsyncMock()
    migrate = AsyncMock()

    with (
        patch.object(mcp_config, "ensure_mcp_tables", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
        patch.object(mcp_config, "upsert_server_row", upsert),
        patch.object(mcp_config, "_migrate_legacy_file_if_needed", migrate),
    ):
        await mcp_config.bootstrap_mcp_config()
        await mcp_config.bootstrap_mcp_config()

    assert list_rows.await_count == 1
    migrate.assert_awaited_once()
    # builtin playbook already present; basic/hitl still seeded once
    assert upsert.await_count == 2


@pytest.mark.asyncio
async def test_migrate_archives_leftover_file_when_externals_exist(tmp_path, monkeypatch):
    legacy = tmp_path / "mcp_config.json"
    legacy.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mcp_config, "MCP_CONFIG_FILE", legacy)

    with patch.object(
        mcp_config,
        "list_server_rows",
        AsyncMock(return_value=[{"name": "ext", "server_type": "external"}]),
    ):
        await mcp_config._migrate_legacy_file_if_needed()

    assert not legacy.exists()
    assert (tmp_path / "mcp_config.json.migrated").exists()
