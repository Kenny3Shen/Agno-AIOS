from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from api.auth.visibility import can_manage_resource, can_read_resource, normalize_visibility
from api.mcp.config import (
    SERVICE_IDS,
    normalize_mcp_servers,
    read_mcp_config,
    write_mcp_config,
)
from api.utils.json import JSONDecodeError, loads

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StandardMcpServer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command: NonEmptyString
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class StandardMcpManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mcpServers: dict[NonEmptyString, StandardMcpServer] = Field(min_length=1)


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
        message = first.get("msg", "invalid value")
        detail = f"{detail}: {loc} {message}" if loc else f"{detail}: {message}"
    return HTTPException(status_code=400, detail=detail)


def apply_service_toggle(service_id: str, enabled: bool) -> McpConfigChange:
    if service_id not in SERVICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid service ID")

    data = read_mcp_config()
    mcp_cfg = data.setdefault("mcp", {})
    if not isinstance(mcp_cfg, dict):
        data["mcp"] = {}
        mcp_cfg = data["mcp"]

    mcp_cfg[service_id] = enabled
    write_mcp_config(data)
    return McpConfigChange(
        response={
            "success": True,
            "control_mode": "integrated",
            "restart_required": True,
        },
        action="mcp.config_update",
        resource_type="mcp_service",
        resource_id=service_id,
        metadata={"enabled": enabled},
    )


def _parse_mcp_manifest(raw: str) -> tuple[str, dict[str, Any]]:
    text = raw.strip()
    if not text:
        raise HTTPException(status_code=400, detail="manifest 不能为空")
    try:
        manifest = loads(text)
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="manifest must be valid JSON") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be a JSON object")

    if "mcpServers" not in manifest:
        raise HTTPException(
            status_code=400,
            detail="manifest must use standard MCP mcpServers format",
        )

    try:
        standard_manifest = StandardMcpManifest.model_validate(manifest)
    except ValidationError as exc:
        raise _manifest_validation_error(exc) from exc

    return "mcp-json", standard_manifest.model_dump(mode="json")


def apply_mcp_upload(
    *,
    name: str,
    description: str = "",
    manifest: str = "",
    enabled: bool = True,
    visibility: str = "private",
    owner_user_id: str | None = None,
) -> McpConfigChange:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    normalized_description = description.strip()
    try:
        normalized_visibility = normalize_visibility(visibility, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    kind, normalized_manifest = _parse_mcp_manifest(manifest)
    normalized_owner = (owner_user_id or "").strip()

    data = read_mcp_config()
    servers = normalize_mcp_servers(data.get("mcp_servers", []))
    if any(entry["name"] == normalized_name for entry in servers):
        raise HTTPException(status_code=409, detail="该 MCP 名称已存在")
    servers.append(
        {
            "name": normalized_name,
            "description": normalized_description,
            "kind": kind,
            "enabled": enabled,
            "visibility": normalized_visibility,
            "owner_user_id": normalized_owner,
            "manifest": normalized_manifest,
        }
    )
    data["mcp_servers"] = servers
    write_mcp_config(data)

    return McpConfigChange(
        response={
            "success": True,
            "name": normalized_name,
            "kind": kind,
            "visibility": normalized_visibility,
            "restart_required": True,
        },
        action="mcp.upload",
        resource_type="mcp",
        resource_id=normalized_name,
        metadata={
            "kind": kind,
            "has_manifest": bool(normalized_manifest),
            "visibility": normalized_visibility,
        },
    )


def visible_mcp_servers(entries: Any, user: Any) -> list[dict[str, Any]]:
    visible_servers: list[dict[str, Any]] = []
    for entry in normalize_mcp_servers(entries):
        if not can_read_resource(user, entry):
            continue
        visible_servers.append(
            {
                **entry,
                "can_manage": can_manage_resource(user, entry),
            }
        )
    return visible_servers


def apply_mcp_server_visibility(
    name: str,
    visibility: str,
    user: Any,
) -> McpConfigChange:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    try:
        normalized_visibility = normalize_visibility(visibility, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = read_mcp_config()
    servers = normalize_mcp_servers(data.get("mcp_servers", []))
    for entry in servers:
        if entry["name"] != normalized_name:
            continue
        if not can_manage_resource(user, entry):
            raise HTTPException(status_code=403, detail="MCP server is not manageable")
        entry["visibility"] = normalized_visibility
        data["mcp_servers"] = servers
        write_mcp_config(data)
        return McpConfigChange(
            response={
                "success": True,
                "name": normalized_name,
                "visibility": normalized_visibility,
            },
            action="mcp.visibility_update",
            resource_type="mcp",
            resource_id=normalized_name,
            metadata={"visibility": normalized_visibility},
        )
    raise HTTPException(status_code=404, detail="MCP server not found")
