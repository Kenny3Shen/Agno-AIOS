from __future__ import annotations

import re
import secrets
import time
from typing import Any

from fastapi_users.jwt import decode_jwt, generate_jwt

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
from api.config import get_settings
from api.utils.async_once import AsyncOnce

SERVICE_IDS = ("basic", "hitl")
MCP_TOKENS_TABLE = "mcp_tokens"
MCP_DELEGATION_AUDIENCE = "tais-mcp-delegation"
MCP_DELEGATION_LIFETIME_SECONDS = 120


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


async def bootstrap_mcp_config() -> None:
    """Idempotent startup seed; runs at most once per process."""
    await _mcp_bootstrap_once.run(_seed_mcp_bootstrap)


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


async def list_tokens(*, owner_user_id: str | None = None) -> list[dict[str, Any]]:
    return await list_token_rows(owner_user_id=owner_user_id)


async def insert_token(
    name: str,
    expires_in: int,
    token: str | None = None,
    *,
    owner_user_id: str | None = None,
    token_kind: str = "user",
) -> str:
    now = int(time.time())
    token_value = token or secrets.token_urlsafe(32)
    await upsert_token_row(
        {
            "id": None,
            "name": name,
            "token": token_value,
            "owner_user_id": owner_user_id,
            "token_kind": token_kind,
            "created_at": now,
            "expires_at": 0 if expires_in == 0 else now + expires_in,
        }
    )
    return token_value


async def delete_token(
    token_id: int | None,
    token_value: str | None,
    *,
    owner_user_id: str | None = None,
) -> bool:
    return await delete_token_row(token_id, token_value, owner_user_id=owner_user_id)


async def find_token(token: str) -> dict[str, Any] | None:
    return await find_token_row(token)


async def is_valid_token(token: str) -> bool:
    record = await find_token(token)
    if record is None:
        return False
    expires_at = int(record.get("expires_at") or 0)
    return expires_at == 0 or int(time.time()) < expires_at


def issue_delegation_token(user_id: str) -> str:
    """Mint a short-lived bearer for the in-process Chat MCP client.

    The FastMCP verifier re-loads the user on every request, so the signed
    token only conveys subject identity and cannot freeze a stale role.
    """
    return generate_jwt(
        {
            "sub": user_id,
            "aud": [MCP_DELEGATION_AUDIENCE],
            "kind": "delegation",
        },
        get_settings().auth_jwt_secret,
        lifetime_seconds=MCP_DELEGATION_LIFETIME_SECONDS,
        algorithm="HS256",
    )


def delegation_subject(token: str) -> str | None:
    try:
        claims = decode_jwt(
            token,
            get_settings().auth_jwt_secret,
            audience=[MCP_DELEGATION_AUDIENCE],
            algorithms=["HS256"],
        )
    except Exception:
        return None
    if claims.get("kind") != "delegation":
        return None
    subject = str(claims.get("sub") or "").strip()
    return subject or None


async def ensure_bootstrap_token(token: str | None) -> None:
    token_value = (token or "").strip()
    if token_value:
        await insert_token(
            "T.A.I.S Agent", 0, token_value, token_kind="service"
        )
