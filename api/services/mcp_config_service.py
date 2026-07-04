from dataclasses import dataclass
import json
from typing import Any

from fastapi import HTTPException

from api.mcp.config import (
    SERVICE_IDS,
    normalize_hiagents,
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


def list_hiagent_entries() -> list[dict[str, Any]]:
    data = read_mcp_config()
    return normalize_hiagents(data.get("hiagent", []))


def add_hiagent_entry(
    *,
    name: str,
    url: str,
    description: str = "",
    enabled: bool = True,
) -> McpConfigChange:
    normalized_name = name.strip()
    normalized_url = url.strip()
    if not normalized_name or not normalized_url:
        raise HTTPException(status_code=400, detail="name 和 url 不能为空")

    data = read_mcp_config()
    entries = normalize_hiagents(data.get("hiagent", []))
    if any(entry["url"] == normalized_url for entry in entries):
        raise HTTPException(status_code=409, detail="该 URL 已存在")

    entries.append(
        {
            "name": normalized_name,
            "url": normalized_url,
            "description": description.strip(),
            "enabled": enabled,
        }
    )
    data["hiagent"] = entries
    write_mcp_config(data)
    return McpConfigChange(
        response={"success": True, "restart_required": True},
        action="mcp.hiagent_add",
        resource_type="hiagent",
        resource_id=normalized_url,
        metadata={"name": normalized_name, "enabled": enabled},
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
        return "remote-url", {}
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
    url: str = "",
    description: str = "",
    manifest: str = "",
    enabled: bool = True,
) -> McpConfigChange:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    normalized_url = url.strip()
    normalized_description = description.strip()
    kind, normalized_manifest = _parse_mcp_manifest(manifest, normalized_name)
    if not normalized_url and not normalized_manifest:
        raise HTTPException(status_code=400, detail="url 或 manifest 至少填写一项")

    data = read_mcp_config()
    if normalized_url:
        hiagents = normalize_hiagents(data.get("hiagent", []))
        if any(entry["url"] == normalized_url for entry in hiagents):
            raise HTTPException(status_code=409, detail="该 URL 已存在")
        hiagents.append(
            {
                "name": normalized_name,
                "url": normalized_url,
                "description": normalized_description,
                "enabled": enabled,
            }
        )
        data["hiagent"] = hiagents

    servers = normalize_mcp_servers(data.get("mcp_servers", []))
    if any(entry["name"] == normalized_name for entry in servers):
        raise HTTPException(status_code=409, detail="该 MCP 名称已存在")
    servers.append(
        {
            "name": normalized_name,
            "description": normalized_description,
            "url": normalized_url,
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
            "url": normalized_url,
            "has_manifest": bool(normalized_manifest),
        },
    )


def update_hiagent_entry(
    *,
    target_url: str | None,
    url: str,
    name: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
) -> McpConfigChange:
    normalized_target_url = (target_url or url or "").strip()
    normalized_url = url.strip()
    if not normalized_target_url:
        raise HTTPException(status_code=400, detail="target_url 不能为空")

    data = read_mcp_config()
    entries = normalize_hiagents(data.get("hiagent", []))

    if (
        normalized_url
        and normalized_url != normalized_target_url
        and any(entry["url"] == normalized_url for entry in entries)
    ):
        raise HTTPException(status_code=409, detail="该 URL 已存在")

    found = False
    for entry in entries:
        if entry["url"] == normalized_target_url:
            if name is not None:
                entry["name"] = name
            if description is not None:
                entry["description"] = description
            if enabled is not None:
                entry["enabled"] = enabled
            if normalized_url:
                entry["url"] = normalized_url
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="未找到该条目")

    data["hiagent"] = entries
    write_mcp_config(data)
    return McpConfigChange(
        response={"success": True, "restart_required": True},
        action="mcp.hiagent_update",
        resource_type="hiagent",
        resource_id=normalized_target_url,
        metadata={"url": normalized_url, "enabled": enabled},
    )


def delete_hiagent_entry(url: str) -> McpConfigChange:
    normalized_url = url.strip()
    if not normalized_url:
        raise HTTPException(status_code=400, detail="url 不能为空")

    data = read_mcp_config()
    entries = normalize_hiagents(data.get("hiagent", []))
    next_entries = [entry for entry in entries if entry["url"] != normalized_url]
    if len(next_entries) == len(entries):
        raise HTTPException(status_code=404, detail="未找到该条目")

    data["hiagent"] = next_entries
    write_mcp_config(data)
    return McpConfigChange(
        response={"success": True, "restart_required": True},
        action="mcp.hiagent_delete",
        resource_type="hiagent",
        resource_id=normalized_url,
    )
