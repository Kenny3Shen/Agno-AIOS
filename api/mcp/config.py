import secrets
import sqlite3
import time
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

SERVICE_IDS = ("playbook", "agent", "basic")
MCP_DATA_DIR = Path("tmp/mcp")
MCP_CONFIG_FILE = MCP_DATA_DIR / "mcp_config.toml"
MCP_TOKENS_DB = MCP_DATA_DIR / "mcp_tokens.db"
HIAGENT_CACHE_DB = MCP_DATA_DIR / "hiagent_cache.db"


def _ensure_data_dir() -> None:
    MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _default_config() -> dict[str, Any]:
    return {"mcp": {service_id: True for service_id in SERVICE_IDS}, "hiagent": []}


def normalize_hiagents(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        normalized.append(
            {
                "name": str(entry.get("name") or "未命名 Agent").strip(),
                "url": url,
                "description": str(entry.get("description") or "").strip(),
                "enabled": bool(entry.get("enabled", True)),
            }
        )
    return normalized


def read_mcp_config() -> dict[str, Any]:
    _ensure_data_dir()
    if not MCP_CONFIG_FILE.exists():
        return _default_config()

    try:
        with MCP_CONFIG_FILE.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return _default_config()

    if "mcp" not in data or not isinstance(data["mcp"], dict):
        data["mcp"] = {}
    if "hiagent" not in data or not isinstance(data["hiagent"], list):
        data["hiagent"] = []
    return data


def write_mcp_config(data: dict[str, Any]) -> None:
    _ensure_data_dir()
    mcp_cfg = data.setdefault("mcp", {})
    if not isinstance(mcp_cfg, dict):
        data["mcp"] = {}
    data["hiagent"] = normalize_hiagents(data.get("hiagent", []))
    with MCP_CONFIG_FILE.open("wb") as f:
        tomli_w.dump(data, f)


def services_from_config(data: dict[str, Any] | None = None) -> dict[str, bool]:
    cfg = read_mcp_config() if data is None else data
    raw_mcp_cfg = cfg.get("mcp")
    mcp_cfg: dict[str, Any] = raw_mcp_cfg if isinstance(raw_mcp_cfg, dict) else {}
    return {
        service_id: bool(mcp_cfg.get(service_id, True)) for service_id in SERVICE_IDS
    }


def enabled_service_ids() -> set[str]:
    return {
        service_id for service_id, enabled in services_from_config().items() if enabled
    }


def enabled_hiagent_urls() -> list[str]:
    data = read_mcp_config()
    return [
        entry["url"]
        for entry in normalize_hiagents(data.get("hiagent", []))
        if entry.get("enabled") and entry.get("url")
    ]


def init_tokens_db() -> None:
    _ensure_data_dir()
    conn = sqlite3.connect(MCP_TOKENS_DB)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def list_tokens() -> list[dict[str, Any]]:
    init_tokens_db()
    conn = sqlite3.connect(MCP_TOKENS_DB)
    try:
        rows = conn.execute(
            "SELECT id, name, token, created_at, expires_at FROM tokens ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "token": row[2],
                "created_at": row[3],
                "expires_at": row[4],
            }
            for row in rows
        ]
    finally:
        conn.close()


def insert_token(name: str, expires_in: int, token: str | None = None) -> str:
    init_tokens_db()
    now = int(time.time())
    token_value = token or secrets.token_urlsafe(32)
    expires_at = 0 if expires_in == 0 else now + expires_in
    conn = sqlite3.connect(MCP_TOKENS_DB)
    try:
        conn.execute(
            "INSERT INTO tokens (name, token, created_at, expires_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET name = excluded.name, expires_at = excluded.expires_at",
            (name, token_value, now, expires_at),
        )
        conn.commit()
        return token_value
    finally:
        conn.close()


def delete_token(token_id: int | None, token_value: str | None) -> bool:
    init_tokens_db()
    conn = sqlite3.connect(MCP_TOKENS_DB)
    try:
        if token_id is not None:
            cursor = conn.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
        elif token_value:
            cursor = conn.execute("DELETE FROM tokens WHERE token = ?", (token_value,))
        else:
            return False
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def find_token(token: str) -> dict[str, Any] | None:
    init_tokens_db()
    conn = sqlite3.connect(MCP_TOKENS_DB)
    try:
        row = conn.execute(
            "SELECT id, name, token, created_at, expires_at FROM tokens WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "token": row[2],
            "created_at": row[3],
            "expires_at": row[4],
        }
    finally:
        conn.close()


def is_valid_token(token: str) -> bool:
    record = find_token(token)
    if record is None:
        return False
    expires_at = int(record.get("expires_at") or 0)
    return expires_at == 0 or int(time.time()) < expires_at


def ensure_bootstrap_token(token: str | None) -> None:
    token_value = (token or "").strip()
    if token_value:
        insert_token("Agno AIOS Agent", 0, token_value)
