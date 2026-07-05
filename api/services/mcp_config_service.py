from dataclasses import dataclass
import json
from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from api.mcp.config import (
    SERVICE_IDS,
    normalize_mcp_servers,
    read_mcp_config_async,
    write_mcp_config_async,
)

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


async def apply_service_toggle_async(service_id: str, enabled: bool) -> McpConfigChange:
    if service_id not in SERVICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid service ID")

    data = await read_mcp_config_async()
    mcp_cfg = data.setdefault("mcp", {})
    if not isinstance(mcp_cfg, dict):
        data["mcp"] = {}
        mcp_cfg = data["mcp"]

    mcp_cfg[service_id] = enabled
    await write_mcp_config_async(data)
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
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
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


async def apply_mcp_upload_async(
    *,
    name: str,
    description: str = "",
    manifest: str = "",
    enabled: bool = True,
) -> McpConfigChange:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    normalized_description = description.strip()
    kind, normalized_manifest = _parse_mcp_manifest(manifest)

    data = await read_mcp_config_async()
    servers = normalize_mcp_servers(data.get("mcp_servers", []))
    if any(entry["name"] == normalized_name for entry in servers):
        raise HTTPException(status_code=409, detail="该 MCP 名称已存在")
    servers.append(
        {
            "name": normalized_name,
            "description": normalized_description,
            "kind": kind,
            "enabled": enabled,
            "manifest": normalized_manifest,
        }
    )
    data["mcp_servers"] = servers
    await write_mcp_config_async(data)

    return McpConfigChange(
        response={
            "success": True,
            "name": normalized_name,
            "kind": kind,
            "restart_required": True,
        },
        action="mcp.upload",
        resource_type="mcp",
        resource_id=normalized_name,
        metadata={
            "kind": kind,
            "has_manifest": bool(normalized_manifest),
        },
    )
