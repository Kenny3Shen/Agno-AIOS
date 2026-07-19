from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import MetaData

from api.mcp import config as mcp_config
from api.persistence import mcp as mcp_store
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
    delete_retired = AsyncMock(return_value=True)
    retire = AsyncMock()

    with (
        patch.object(mcp_config, "ensure_mcp_tables", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
        patch.object(mcp_config, "upsert_server_row", upsert),
        patch.object(
            mcp_config,
            "delete_retired_builtin_server_row",
            delete_retired,
        ),
        patch.object(mcp_config, "_retire_legacy_mcp_config_file", retire),
    ):
        await mcp_config.bootstrap_mcp_config()
        await mcp_config.bootstrap_mcp_config()

    assert list_rows.await_count == 1
    retire.assert_awaited_once()
    delete_retired.assert_awaited_once_with("playbook")
    # Only explicitly retired services are migrated.  Unknown built-ins may
    # belong to a newer deployment and must not be removed at startup.
    assert "future-built-in" not in {
        call.args[0] for call in delete_retired.await_args_list
    }
    # ``basic`` survived, and the only missing supported service was seeded once.
    upsert.assert_awaited_once()
    upsert_call = upsert.await_args
    assert upsert_call is not None
    assert upsert_call.args[0]["name"] == "hitl"


def test_retired_builtin_component_overrides_cascade_with_server_row() -> None:
    table = mcp_store.mcp_component_overrides_table(MetaData())
    foreign_key = next(iter(table.c.server_id.foreign_keys))

    assert foreign_key.ondelete == "CASCADE"


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
    list_rows = AsyncMock(return_value=[{"name": "basic", "enabled": True}])
    with (
        patch.object(mcp_config, "bootstrap_mcp_config", AsyncMock()),
        patch.object(mcp_config, "list_server_rows", list_rows),
    ):
        rows = await mcp_config.enabled_mcp_servers()

    assert rows == [{"name": "basic", "enabled": True}]
    list_rows.assert_awaited_once_with(enabled=True)
