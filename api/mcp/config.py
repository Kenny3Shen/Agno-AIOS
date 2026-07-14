from __future__ import annotations

import re
import secrets
import time
from typing import Any

from anyio import Path as AsyncPath

from api.persistence.mcp import (
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
from api.utils.json import loads

SERVICE_IDS = ("playbook", "basic", "hitl")
MCP_CONFIG_FILE = CONFIG_DIR / "mcp" / "mcp_config.json"
MCP_TOKENS_TABLE = "mcp_tokens"


def normalize_namespace(value: str) -> str:
    namespace = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_")
    if not namespace:
        raise ValueError("namespace must contain letters or numbers")
    return namespace


async def init_mcp_postgres_tables() -> None:
    await ensure_mcp_tables()


async def bootstrap_mcp_config() -> None:
    await ensure_mcp_tables()
    now = int(time.time())
    existing_names = {row["name"] for row in await list_server_rows()}
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
    await _migrate_legacy_file_if_needed()


async def _migrate_legacy_file_if_needed() -> None:
    rows = await list_server_rows()
    if any(row["server_type"] == "external" for row in rows):
        return
    path = AsyncPath(MCP_CONFIG_FILE)
    if not await path.exists():
        return
    try:
        raw = loads(await path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(raw, dict):
        return
    now = int(time.time())
    flags = raw.get("mcp") if isinstance(raw.get("mcp"), dict) else {}
    by_name = {row["name"]: row for row in rows}
    for service_id in SERVICE_IDS:
        row = by_name.get(service_id)
        if row is not None and service_id in flags:
            await upsert_server_row({**row, "enabled": bool(flags[service_id]), "updated_at": now})
    entries = raw.get("mcp_servers") if isinstance(raw.get("mcp_servers"), list) else []
    for entry in entries:
        if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
            continue
        name = str(entry["name"]).strip()
        try:
            namespace = normalize_namespace(name)
        except ValueError:
            continue
        await upsert_server_row(
            {
                "name": name,
                "namespace": namespace,
                "description": str(entry.get("description") or ""),
                "server_type": "external",
                "transport": "mcp-config",
                "enabled": bool(entry.get("enabled", True)),
                "visibility": str(entry.get("visibility") or "private"),
                "owner_user_id": str(entry.get("owner_user_id") or ""),
                "config": entry.get("manifest") if isinstance(entry.get("manifest"), dict) else {},
                "created_at": now,
                "updated_at": now,
            }
        )
    migrated_path = AsyncPath(f"{MCP_CONFIG_FILE}.migrated")
    if not await migrated_path.exists():
        await path.rename(migrated_path)


async def list_mcp_servers() -> list[dict[str, Any]]:
    await bootstrap_mcp_config()
    return await list_server_rows()


async def enabled_mcp_servers() -> list[dict[str, Any]]:
    return [row for row in await list_mcp_servers() if row["enabled"]]


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
