import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth.models import User
from api.auth.permissions import require_permission
from api.services.audit_service import (
    AuditRequestContext,
    audit_request_context,
    record_audit_event,
)
from api.services.mcp_config_service import (
    McpConfigChange,
    add_hiagent_entry,
    apply_service_toggle,
    delete_hiagent_entry,
    list_hiagent_entries,
    update_hiagent_entry,
)
from api.mcp.config import (
    HIAGENT_CACHE_DB,
    MCP_CONFIG_FILE,
    MCP_TOKENS_DB,
    delete_token,
    insert_token,
    list_tokens,
    normalize_hiagents,
    normalize_mcp_servers,
    read_mcp_config,
    services_from_config,
    write_mcp_config,
)

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


class ServiceToggle(BaseModel):
    id: str
    enabled: bool


class TokenIssue(BaseModel):
    name: str
    expires_in: int


class TokenDelete(BaseModel):
    id: int | None = None
    token: str | None = None


class HiAgentAdd(BaseModel):
    name: str
    url: str
    description: str = ""
    enabled: bool = True


class HiAgentUpdate(BaseModel):
    target_url: str | None = None
    url: str
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class HiAgentDelete(BaseModel):
    url: str


class McpUploadRequest(BaseModel):
    name: str
    url: str = ""
    description: str = ""
    manifest: str = ""
    enabled: bool = True


class McpUploadResponse(BaseModel):
    success: bool
    name: str
    kind: str
    restart_required: bool = True


def _record_config_change(
    user: User,
    change: McpConfigChange,
    request_context: AuditRequestContext,
) -> None:
    record_audit_event(
        user,
        action=change.action,
        resource_type=change.resource_type,
        resource_id=change.resource_id,
        metadata=change.metadata,
        **request_context,
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


@router.get("/config")
async def get_config(_user: User = Depends(require_permission("mcp:read"))) -> dict[str, Any]:
    data = read_mcp_config()
    return {
        "services": services_from_config(data),
        "control_mode": "integrated",
        "fastmcp": "in-process",
        "mcp_url": "/mcp/",
        "config_path": str(MCP_CONFIG_FILE),
        "tokens_db_path": str(MCP_TOKENS_DB),
        "hiagent_cache_path": str(HIAGENT_CACHE_DB),
    }


@router.post("/config")
async def update_config(
    request: Request,
    body: ServiceToggle,
    user: User = Depends(require_permission("mcp:write")),
):
    change = apply_service_toggle(body.id, body.enabled)
    _record_config_change(user, change, audit_request_context(request))
    return change.response


@router.get("/tokens")
async def get_tokens(_user: User = Depends(require_permission("mcp:read"))):
    return list_tokens()


@router.post("/tokens/issue")
async def issue_token(
    request: Request,
    body: TokenIssue,
    user: User = Depends(require_permission("mcp:write")),
):
    expires_in = int(body.expires_in)
    if expires_in < 0:
        raise HTTPException(status_code=400, detail="Invalid expires_in")
    if expires_in != 0 and expires_in < 86400:
        raise HTTPException(status_code=400, detail="Expires in must be at least 1 day")

    token = insert_token(name=body.name.strip() or "未命名 Token", expires_in=expires_in)
    record_audit_event(
        user,
        action="mcp.token_issue",
        resource_type="mcp_token",
        resource_id=body.name.strip() or "未命名 Token",
        metadata={"expires_in": expires_in},
        **audit_request_context(request),
    )
    return {"token": token}


@router.post("/tokens/delete")
async def remove_token(
    request: Request,
    body: TokenDelete,
    user: User = Depends(require_permission("mcp:write")),
):
    deleted = delete_token(body.id, body.token)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    record_audit_event(
        user,
        action="mcp.token_delete",
        resource_type="mcp_token",
        resource_id=str(body.id or body.token or ""),
        **audit_request_context(request),
    )
    return {"success": True}


@router.get("/hiagent")
async def list_hiagent(_user: User = Depends(require_permission("mcp:read"))):
    return list_hiagent_entries()


@router.post("/hiagent/add")
async def add_hiagent(
    request: Request,
    body: HiAgentAdd,
    user: User = Depends(require_permission("mcp:write")),
):
    change = add_hiagent_entry(
        name=body.name,
        url=body.url,
        description=body.description,
        enabled=body.enabled,
    )
    _record_config_change(user, change, audit_request_context(request))
    return change.response


@router.post("/hiagent/update")
async def update_hiagent(
    request: Request,
    body: HiAgentUpdate,
    user: User = Depends(require_permission("mcp:write")),
):
    change = update_hiagent_entry(
        target_url=body.target_url,
        url=body.url,
        name=body.name,
        description=body.description,
        enabled=body.enabled,
    )
    _record_config_change(user, change, audit_request_context(request))
    return change.response


@router.post("/hiagent/delete")
async def delete_hiagent(
    request: Request,
    body: HiAgentDelete,
    user: User = Depends(require_permission("mcp:write")),
):
    change = delete_hiagent_entry(body.url)
    _record_config_change(user, change, audit_request_context(request))
    return change.response


@router.post("/upload", response_model=McpUploadResponse)
async def upload_mcp(
    request: Request,
    body: McpUploadRequest,
    user: User = Depends(require_permission("mcp:write")),
):
    """上传 MCP manifest 或注册远程 MCP URL。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    url = body.url.strip()
    description = body.description.strip()
    kind, manifest = _parse_mcp_manifest(body.manifest, name)
    if not url and not manifest:
        raise HTTPException(status_code=400, detail="url 或 manifest 至少填写一项")

    data = read_mcp_config()
    if url:
        hiagents = normalize_hiagents(data.get("hiagent", []))
        if any(entry["url"] == url for entry in hiagents):
            raise HTTPException(status_code=409, detail="该 URL 已存在")
        hiagents.append(
            {
                "name": name,
                "url": url,
                "description": description,
                "enabled": body.enabled,
            }
        )
        data["hiagent"] = hiagents

    servers = normalize_mcp_servers(data.get("mcp_servers", []))
    if any(entry["name"] == name for entry in servers):
        raise HTTPException(status_code=409, detail="该 MCP 名称已存在")
    servers.append(
        {
            "name": name,
            "description": description,
            "url": url,
            "kind": kind,
            "enabled": body.enabled,
            "manifest": manifest,
        }
    )
    data["mcp_servers"] = servers
    write_mcp_config(data)

    record_audit_event(
        user,
        action="mcp.upload",
        resource_type="mcp",
        resource_id=name,
        metadata={"kind": kind, "url": url, "has_manifest": bool(manifest)},
        **audit_request_context(request),
    )
    return McpUploadResponse(success=True, name=name, kind=kind)
