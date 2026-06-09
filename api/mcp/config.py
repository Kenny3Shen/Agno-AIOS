import secrets
import time
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from api.services.mysql_store import mysql_connect, mysql_label

SERVICE_IDS = ("playbook", "agent", "basic")
MCP_DATA_DIR = Path("tmp/mcp")
MCP_CONFIG_FILE = MCP_DATA_DIR / "mcp_config.toml"
MCP_TOKENS_TABLE = "mcp_tokens"
HIAGENT_CACHE_TABLE = "hiagent_exec_cache"
MCP_TOKENS_DB = mysql_label(MCP_TOKENS_TABLE)
HIAGENT_CACHE_DB = mysql_label(HIAGENT_CACHE_TABLE)


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


def init_mcp_mysql_tables() -> None:
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {MCP_TOKENS_TABLE} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    created_at BIGINT NOT NULL,
                    expires_at BIGINT NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {HIAGENT_CACHE_TABLE} (
                    exec_id VARCHAR(128) PRIMARY KEY,
                    tool_name VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    result LONGTEXT,
                    error LONGTEXT,
                    created_at DOUBLE NOT NULL,
                    INDEX idx_hiagent_exec_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
    finally:
        conn.close()


def init_tokens_db() -> None:
    init_mcp_mysql_tables()


def list_tokens() -> list[dict[str, Any]]:
    init_tokens_db()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, name, token, created_at, expires_at
                FROM {MCP_TOKENS_TABLE}
                ORDER BY created_at DESC
                """
            )
            return list(cursor.fetchall())
    finally:
        conn.close()


def insert_token(name: str, expires_in: int, token: str | None = None) -> str:
    init_tokens_db()
    now = int(time.time())
    token_value = token or secrets.token_urlsafe(32)
    expires_at = 0 if expires_in == 0 else now + expires_in
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {MCP_TOKENS_TABLE}
                    (name, token, created_at, expires_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    expires_at = VALUES(expires_at)
                """,
                (name, token_value, now, expires_at),
            )
        return token_value
    finally:
        conn.close()


def delete_token(token_id: int | None, token_value: str | None) -> bool:
    init_tokens_db()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            if token_id is not None:
                cursor.execute(
                    f"DELETE FROM {MCP_TOKENS_TABLE} WHERE id = %s", (token_id,)
                )
            elif token_value:
                cursor.execute(
                    f"DELETE FROM {MCP_TOKENS_TABLE} WHERE token = %s",
                    (token_value,),
                )
            else:
                return False
            return cursor.rowcount > 0
    finally:
        conn.close()


def find_token(token: str) -> dict[str, Any] | None:
    init_tokens_db()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, name, token, created_at, expires_at
                FROM {MCP_TOKENS_TABLE}
                WHERE token = %s
                """,
                (token,),
            )
            return cursor.fetchone()
    finally:
        conn.close()


def save_hiagent_exec(
    exec_id: str,
    tool_name: str,
    status: str,
    result: str = "",
    error: str = "",
) -> None:
    init_mcp_mysql_tables()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {HIAGENT_CACHE_TABLE}
                    (exec_id, tool_name, status, result, error, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    tool_name = VALUES(tool_name),
                    status = VALUES(status),
                    result = VALUES(result),
                    error = VALUES(error),
                    created_at = VALUES(created_at)
                """,
                (exec_id, tool_name, status, result, error, time.time()),
            )
    finally:
        conn.close()


def load_hiagent_exec(exec_id: str) -> dict[str, Any] | None:
    init_mcp_mysql_tables()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT exec_id, tool_name, status, result, error, created_at
                FROM {HIAGENT_CACHE_TABLE}
                WHERE exec_id = %s
                """,
                (exec_id,),
            )
            return cursor.fetchone()
    finally:
        conn.close()


def upsert_token_record(record: dict[str, Any]) -> None:
    init_tokens_db()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {MCP_TOKENS_TABLE}
                    (id, name, token, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    created_at = VALUES(created_at),
                    expires_at = VALUES(expires_at)
                """,
                (
                    record.get("id"),
                    record.get("name"),
                    record.get("token"),
                    record.get("created_at"),
                    record.get("expires_at"),
                ),
            )
    finally:
        conn.close()


def upsert_hiagent_exec_record(record: dict[str, Any]) -> None:
    init_mcp_mysql_tables()
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {HIAGENT_CACHE_TABLE}
                    (exec_id, tool_name, status, result, error, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    tool_name = VALUES(tool_name),
                    status = VALUES(status),
                    result = VALUES(result),
                    error = VALUES(error),
                    created_at = VALUES(created_at)
                """,
                (
                    record.get("exec_id"),
                    record.get("tool_name"),
                    record.get("status"),
                    record.get("result"),
                    record.get("error"),
                    record.get("created_at"),
                ),
            )
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
