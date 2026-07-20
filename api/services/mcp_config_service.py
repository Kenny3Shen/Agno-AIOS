from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from api.auth.claims import actor_role
from api.auth.visibility import can_manage_resource, can_read_resource, normalize_visibility
from api.mcp.config import list_mcp_servers, normalize_namespace
from api.persistence.mcp import (
    delete_server_row,
    get_server_row,
    get_server_row_by_name,
    insert_server_row,
    server_name_exists,
    update_server_row,
)
from api.persistence.capability_preferences import clear_capability_preferences_for_resource
from api.utils.json import JSONDecodeError, loads

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StdioMcpServer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command: NonEmptyString
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class HttpMcpServer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: NonEmptyString
    transport: Literal["http", "streamable-http"] = "http"
    headers: dict[str, str] = Field(default_factory=dict)


McpServerConfig = StdioMcpServer | HttpMcpServer
SERVER_CONFIG_ADAPTER = TypeAdapter(dict[NonEmptyString, McpServerConfig])


class StandardMcpManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mcpServers: dict[str, Any] = Field(min_length=1)


@dataclass(frozen=True)
class McpConfigChange:
    response: dict[str, Any]
    action: str
    resource_type: str
    resource_id: str
    metadata: dict[str, Any] | None = None


def _manifest_validation_error(exc: ValidationError) -> HTTPException:
    errors = exc.errors()
    detail = "manifest must use standard MCP mcpServers format"
    if errors:
        first = errors[0]
        loc = ".".join(str(part) for part in first.get("loc", ()))
        detail = f"{detail}: {loc} {first.get('msg', 'invalid value')}"
    return HTTPException(status_code=400, detail=detail)


def parse_mcp_manifest(raw: str) -> tuple[str, dict[str, Any]]:
    text = raw.strip()
    if not text:
        raise HTTPException(status_code=400, detail="manifest 不能为空")
    try:
        manifest = loads(text)
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="manifest must be valid JSON") from exc
    if not isinstance(manifest, dict) or "mcpServers" not in manifest:
        raise HTTPException(status_code=400, detail="manifest must use standard MCP mcpServers format")
    try:
        wrapper = StandardMcpManifest.model_validate(manifest)
        servers = SERVER_CONFIG_ADAPTER.validate_python(wrapper.mcpServers, strict=True)
    except ValidationError as exc:
        raise _manifest_validation_error(exc) from exc
    normalized = {name: config.model_dump(mode="json") for name, config in servers.items()}
    transports = {"stdio" if isinstance(config, StdioMcpServer) else "streamable-http" for config in servers.values()}
    transport = transports.pop() if len(transports) == 1 else "mcp-config"
    return transport, {"mcpServers": normalized}


def _public_server(row: dict[str, Any], user: Any) -> dict[str, Any]:
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    redacted = _redact_config(config)
    return {
        **row,
        "kind": row["server_type"],
        "manifest": redacted,
        "config": redacted,
        "can_manage": can_manage_resource(user, row),
        "can_delete": row["server_type"] != "builtin" and actor_role(user) == "admin",
    }


def _redact_config(value: Any, key: str = "") -> Any:
    if key.lower() in {"env", "headers"} and isinstance(value, dict):
        return {name: "********" for name in value}
    if isinstance(value, dict):
        return {name: _redact_config(child, name) for name, child in value.items()}
    if isinstance(value, list):
        return [_redact_config(child) for child in value]
    return value


async def visible_mcp_servers(user: Any) -> list[dict[str, Any]]:
    return [_public_server(row, user) for row in await list_mcp_servers() if can_read_resource(user, row)]


async def apply_service_toggle(service_id: str, enabled: bool) -> McpConfigChange:
    row = await get_server_row_by_name(service_id)
    if row is None or row.get("server_type") != "builtin":
        raise HTTPException(status_code=400, detail="Invalid service ID")
    await update_server_row(row["id"], {"enabled": enabled, "updated_at": int(time.time())})
    return McpConfigChange(
        response={"success": True, "control_mode": "integrated", "restart_required": True},
        action="mcp.config_update", resource_type="mcp_service", resource_id=service_id,
        metadata={"enabled": enabled},
    )


async def apply_mcp_upload(
    *, name: str, description: str = "", manifest: str = "", enabled: bool = True,
    visibility: str = "private", owner_user_id: str | None = None,
) -> McpConfigChange:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    try:
        normalized_visibility = normalize_visibility(visibility, strict=True)
        namespace = normalize_namespace(normalized_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    transport, config = parse_mcp_manifest(manifest)
    if await server_name_exists(normalized_name):
        raise HTTPException(status_code=409, detail="该 MCP 名称已存在")
    now = int(time.time())
    try:
        row = await insert_server_row({
            "name": normalized_name, "namespace": namespace, "description": description.strip(),
            "server_type": "external", "transport": transport, "enabled": enabled,
            "visibility": normalized_visibility, "owner_user_id": (owner_user_id or "").strip(),
            "config": config, "created_at": now, "updated_at": now,
        })
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该 MCP 名称或 namespace 已存在") from exc
    return McpConfigChange(
        response={"success": True, "id": row["id"], "name": normalized_name, "kind": "external", "namespace": namespace, "visibility": normalized_visibility, "restart_required": True},
        action="mcp.upload", resource_type="mcp", resource_id=normalized_name,
        metadata={"transport": transport, "visibility": normalized_visibility},
    )


async def apply_mcp_server_visibility(name: str, visibility: str, user: Any) -> McpConfigChange:
    try:
        normalized_visibility = normalize_visibility(visibility, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await get_server_row_by_name(name)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if not can_manage_resource(user, row):
        raise HTTPException(status_code=403, detail="MCP server is not manageable")
    await update_server_row(row["id"], {"visibility": normalized_visibility, "updated_at": int(time.time())})
    return McpConfigChange(
        response={"success": True, "name": name, "visibility": normalized_visibility},
        action="mcp.visibility_update", resource_type="mcp", resource_id=name,
        metadata={"visibility": normalized_visibility},
    )


async def apply_mcp_server_toggle(server_id: int, enabled: bool, user: Any) -> McpConfigChange:
    row = await get_server_row(server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if not can_manage_resource(user, row):
        raise HTTPException(status_code=403, detail="MCP server is not manageable")
    await update_server_row(server_id, {"enabled": enabled, "updated_at": int(time.time())})
    return McpConfigChange(
        response={"success": True, "enabled": enabled, "restart_required": True},
        action="mcp.server_toggle", resource_type="mcp", resource_id=row["name"],
        metadata={"enabled": enabled},
    )




async def remove_mcp_server(server_id: int, user: Any) -> McpConfigChange:
    row = await get_server_row(server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if actor_role(user) != "admin":
        raise HTTPException(status_code=403, detail="Administrator permission required")
    if row["server_type"] == "builtin" or not await delete_server_row(server_id):
        raise HTTPException(status_code=400, detail="Built-in MCP server cannot be deleted")
    await clear_capability_preferences_for_resource(
        capability_type="mcp_server", capability_key=str(server_id)
    )
    return McpConfigChange(
        response={"success": True, "restart_required": True}, action="mcp.delete",
        resource_type="mcp", resource_id=row["name"],
    )
