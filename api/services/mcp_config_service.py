from dataclasses import dataclass
import json
from typing import Any

from fastapi import HTTPException

from api.mcp.config import (
    SERVICE_IDS,
    normalize_mcp_servers,
    read_mcp_config,
    write_mcp_config,
)


@dataclass(frozen=True)
class McpConfigChange:
    response: dict[str, Any]
    action: str
    resource_type: str
    resource_id: str
    metadata: dict[str, Any] | None = None


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


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{field} must be a non-empty string")
    return value.strip()


def _validate_string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=400, detail=f"{field} must be a string array")
    return value


def _validate_string_map(value: Any, field: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise HTTPException(status_code=400, detail=f"{field} must be a string map")
    return value


def _parse_mcp_manifest(raw: str, name: str) -> tuple[str, dict[str, Any]]:
    text = raw.strip()
    if not text:
        raise HTTPException(status_code=400, detail="manifest 不能为空")
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="manifest must be valid JSON") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be a JSON object")

    if "mcpServers" in manifest:
        servers = manifest.get("mcpServers")
        if not isinstance(servers, dict) or not servers:
            raise HTTPException(status_code=400, detail="mcpServers must be a non-empty object")
        selected_name = name if name in servers else next(iter(servers))
        server = servers.get(selected_name)
        if not isinstance(server, dict):
            raise HTTPException(status_code=400, detail="selected mcpServers entry is invalid")
        normalized_server = {
            "command": _require_string(server.get("command"), "mcpServers.command"),
            "args": _validate_string_list(server.get("args"), "mcpServers.args"),
            "env": _validate_string_map(server.get("env"), "mcpServers.env"),
        }
        return "mcp-json", {"mcpServers": {selected_name: normalized_server}}

    if "source" in manifest:
        source = manifest.get("source")
        if not isinstance(source, dict):
            raise HTTPException(status_code=400, detail="source must be an object")
        normalized_manifest: dict[str, Any] = {
            "source": {
                "type": str(source.get("type") or "filesystem"),
                "path": _require_string(source.get("path"), "source.path"),
            }
        }
        entrypoint = source.get("entrypoint")
        if entrypoint is not None:
            normalized_manifest["source"]["entrypoint"] = _require_string(
                entrypoint, "source.entrypoint"
            )
        for section in ("environment", "deployment"):
            value = manifest.get(section)
            if value is not None:
                if not isinstance(value, dict):
                    raise HTTPException(status_code=400, detail=f"{section} must be an object")
                normalized_manifest[section] = value
        return "fastmcp-json", normalized_manifest

    raise HTTPException(
        status_code=400,
        detail="manifest must use fastmcp.json source or standard mcpServers format",
    )


def apply_mcp_upload(
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
    kind, normalized_manifest = _parse_mcp_manifest(manifest, normalized_name)

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
