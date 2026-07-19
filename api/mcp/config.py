from __future__ import annotations

import re
import secrets
import time
from typing import Any

from anyio import Path as AsyncPath
from loguru import logger

from api.persistence.mcp import (
    delete_retired_builtin_server_row,
    delete_token_row,
    ensure_mcp_tables,
    find_token_row,
    list_component_override_rows,
    list_server_rows,
    list_token_rows,
    upsert_component_override_row,
    upsert_server_row,
    upsert_token_row,
)
from api.services.runtime_paths import CONFIG_DIR
from api.utils.async_once import AsyncOnce

SERVICE_IDS = ("basic", "hitl")
# A migration must name only services deliberately removed by this release.
# Treating every unknown ``builtin`` row as retired would silently discard
# data from a newer deployment or an extension during a rolling downgrade.
RETIRED_SERVICE_IDS = frozenset({"playbook"})
MCP_CONFIG_FILE = CONFIG_DIR / "mcp" / "mcp_config.json"
MCP_TOKENS_TABLE = "mcp_tokens"


def normalize_namespace(value: str) -> str:
    namespace = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_")
    if not namespace:
        raise ValueError("namespace must contain letters or numbers")
    return namespace


async def init_mcp_postgres_tables() -> None:
    await ensure_mcp_tables()


_mcp_bootstrap_once = AsyncOnce()


async def _seed_mcp_bootstrap() -> None:
    await ensure_mcp_tables()
    now = int(time.time())
    rows = await list_server_rows()
    existing_names = {row["name"] for row in rows}
    retired_builtin_names = sorted(
        str(row.get("name") or "")
        for row in rows
        if str(row.get("server_type") or "") == "builtin"
        and str(row.get("name") or "") in RETIRED_SERVICE_IDS
    )
    for service_id in retired_builtin_names:
        if await delete_retired_builtin_server_row(service_id):
            logger.info("retired obsolete built-in MCP service {}", service_id)
            existing_names.discard(service_id)
    for service_id in SERVICE_IDS:
        if service_id in existing_names:
            continue
        await upsert_server_row(
            {
                "name": service_id,
                "namespace": service_id,
                "description": f"Built-in {service_id} tools",
                "server_type": "builtin",
                "transport": "inprocess",
                "enabled": True,
                "visibility": "public",
                "owner_user_id": "",
                "config": {},
                "created_at": now,
                "updated_at": now,
            }
        )
    await _retire_legacy_mcp_config_file()


async def bootstrap_mcp_config() -> None:
    """Idempotent startup seed; runs at most once per process."""
    await _mcp_bootstrap_once.run(_seed_mcp_bootstrap)


async def _archive_legacy_mcp_config_file(path: AsyncPath) -> None:
    migrated_path = AsyncPath(f"{MCP_CONFIG_FILE}.migrated")
    try:
        if await migrated_path.exists():
            if await path.exists():
                await path.unlink()
        else:
            await path.rename(migrated_path)
            logger.info("archived legacy MCP config to {}", migrated_path)
    except OSError:
        logger.warning("unable to archive legacy MCP config at {}", path, exc_info=True)


async def _retire_legacy_mcp_config_file() -> None:
    path = AsyncPath(MCP_CONFIG_FILE)
    if not await path.exists():
        return
    logger.warning(
        "retiring leftover MCP config file at {} (Postgres is source of truth)",
        path,
    )
    await _archive_legacy_mcp_config_file(path)


async def list_mcp_servers() -> list[dict[str, Any]]:
    await bootstrap_mcp_config()
    return await list_server_rows()


async def enabled_mcp_servers() -> list[dict[str, Any]]:
    await bootstrap_mcp_config()
    return await list_server_rows(enabled=True)


async def component_overrides() -> list[dict[str, Any]]:
    return await list_component_override_rows()


async def set_component_override(
    server_id: int, component_type: str, component_name: str, enabled: bool
) -> None:
    await upsert_component_override_row(
        {
            "server_id": server_id,
            "component_type": component_type,
            "component_name": component_name,
            "enabled": enabled,
            "updated_at": int(time.time()),
        }
    )


async def list_tokens() -> list[dict[str, Any]]:
    return await list_token_rows()


async def insert_token(name: str, expires_in: int, token: str | None = None) -> str:
    now = int(time.time())
    token_value = token or secrets.token_urlsafe(32)
    await upsert_token_row(
        {
            "id": None,
            "name": name,
            "token": token_value,
            "created_at": now,
            "expires_at": 0 if expires_in == 0 else now + expires_in,
        }
    )
    return token_value


async def delete_token(token_id: int | None, token_value: str | None) -> bool:
    return await delete_token_row(token_id, token_value)


async def find_token(token: str) -> dict[str, Any] | None:
    return await find_token_row(token)


async def is_valid_token(token: str) -> bool:
    record = await find_token(token)
    if record is None:
        return False
    expires_at = int(record.get("expires_at") or 0)
    return expires_at == 0 or int(time.time()) < expires_at


async def ensure_bootstrap_token(token: str | None) -> None:
    token_value = (token or "").strip()
    if token_value:
        await insert_token("T.A.I.S Agent", 0, token_value)
