import secrets
import time
from typing import Any

from api.auth.visibility import normalize_visibility
from api.persistence.mcp import (
    ensure_mcp_tables,
    find_token_row,
    list_token_rows,
    upsert_token_row,
    delete_token_row,
)
from api.services.runtime_paths import CONFIG_DIR
from api.services.postgres_store import mcp_schema, postgres_label
from api.utils.json import dumps, loads

SERVICE_IDS = ("playbook", "basic")
MCP_DATA_DIR = CONFIG_DIR / "mcp"
MCP_CONFIG_FILE = MCP_DATA_DIR / "mcp_config.json"
MCP_TOKENS_TABLE = "mcp_tokens"
MCP_TOKENS_DB = postgres_label(mcp_schema(), MCP_TOKENS_TABLE)


def _default_config() -> dict[str, Any]:
    return {
        "mcp": {service_id: True for service_id in SERVICE_IDS},
        "mcp_servers": [],
    }


def normalize_mcp_servers(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        manifest = entry.get("manifest")
        if not isinstance(manifest, dict):
            manifest = {}
        normalized.append(
            {
                "name": name,
                "description": str(entry.get("description") or "").strip(),
                "kind": str(entry.get("kind") or "unknown").strip(),
                "enabled": bool(entry.get("enabled", True)),
                "visibility": normalize_visibility(str(entry.get("visibility") or "")),
                "owner_user_id": str(
                    entry.get("owner_user_id") or entry.get("user_id") or ""
                ).strip(),
                "manifest": manifest,
            }
        )
    return normalized


def _normalize_mcp_flags(value: Any) -> dict[str, bool]:
    raw_mcp_cfg: dict[str, Any] = value if isinstance(value, dict) else {}
    return {
        service_id: bool(raw_mcp_cfg.get(service_id, True))
        for service_id in SERVICE_IDS
    }


def _normalize_mcp_config(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "mcp": _normalize_mcp_flags(data.get("mcp")),
        "mcp_servers": normalize_mcp_servers(data.get("mcp_servers", [])),
    }


def read_mcp_config() -> dict[str, Any]:
    MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MCP_CONFIG_FILE.exists():
        return _default_config()
    try:
        data = loads(MCP_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_config()
    if not isinstance(data, dict):
        return _default_config()
    return _normalize_mcp_config(data)


def write_mcp_config(data: dict[str, Any]) -> None:
    MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_mcp_config(data)
    MCP_CONFIG_FILE.write_text(
        dumps(normalized, indent=True, append_newline=True),
        encoding="utf-8",
    )


def services_from_config(data: dict[str, Any] | None = None) -> dict[str, bool]:
    cfg = read_mcp_config() if data is None else data
    return _normalize_mcp_flags(cfg.get("mcp"))


def enabled_service_ids() -> set[str]:
    return {
        service_id for service_id, enabled in services_from_config().items() if enabled
    }


async def init_mcp_postgres_tables() -> None:
    await ensure_mcp_tables()


async def init_tokens_db() -> None:
    await init_mcp_postgres_tables()


async def list_tokens() -> list[dict[str, Any]]:
    await init_tokens_db()
    return await list_token_rows()


async def insert_token(name: str, expires_in: int, token: str | None = None) -> str:
    await init_tokens_db()
    now = int(time.time())
    token_value = token or secrets.token_urlsafe(32)
    expires_at = 0 if expires_in == 0 else now + expires_in
    await upsert_token_row(
        {
            "id": None,
            "name": name,
            "token": token_value,
            "created_at": now,
            "expires_at": expires_at,
        }
    )
    return token_value


async def delete_token(token_id: int | None, token_value: str | None) -> bool:
    await init_tokens_db()
    return await delete_token_row(token_id, token_value)


async def find_token(token: str) -> dict[str, Any] | None:
    await init_tokens_db()
    return await find_token_row(token)


async def upsert_token_record(record: dict[str, Any]) -> None:
    await init_tokens_db()
    await upsert_token_row(record)


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
