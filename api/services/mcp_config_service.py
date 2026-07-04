from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from api.mcp.config import (
    SERVICE_IDS,
    normalize_hiagents,
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
