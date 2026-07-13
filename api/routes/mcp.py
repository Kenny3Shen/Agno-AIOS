from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth.claims import actor_id, actor_role
from api.auth.models import User
from api.auth.scopes import require_scope
from api.auth.visibility import normalize_visibility
from api.mcp.config import delete_token, insert_token, list_tokens
from api.mcp.server import (
    call_tool,
    list_components,
    set_component_enabled,
    test_server_config,
)
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.mcp_config_service import (
    apply_mcp_server_visibility,
    apply_mcp_server_toggle,
    apply_mcp_upload,
    apply_service_toggle,
    parse_mcp_manifest,
    remove_mcp_server,
    visible_mcp_servers,
)
from api.services.upload_approval_service import submit_mcp_upload
from api.services.notification_service import notify_admins_of_submission

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


class ServiceToggle(BaseModel):
    id: str
    enabled: bool


class TokenIssue(BaseModel):
    name: str
    expires_in: int


class TokenDelete(BaseModel):
    id: int | None = None


class McpUploadRequest(BaseModel):
    name: str
    description: str = ""
    manifest: str = ""
    enabled: bool = True
    visibility: str = "private"


class McpUploadResponse(BaseModel):
    success: bool
    id: int | None = None
    name: str
    kind: str = "external"
    namespace: str = ""
    visibility: str
    restart_required: bool = False
    status: str = "approved"
    approval_id: str | None = None


class McpVisibilityRequest(BaseModel):
    visibility: str


class ComponentToggle(BaseModel):
    server_id: int
    enabled: bool


class ToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/config")
async def get_config(user: User = Depends(require_scope("mcp:read"))) -> dict[str, Any]:
    servers = await visible_mcp_servers(user)
    return {
        "services": {row["name"]: row["enabled"] for row in servers if row["server_type"] == "builtin"},
        "mcp_servers": servers,
        "control_mode": "integrated",
        "fastmcp": "3",
        "mcp_url": "/mcp/",
        "config_store": "postgresql",
    }


@router.post("/config")
async def update_config(request: Request, body: ServiceToggle, user: User = Depends(require_scope("mcp:write"))):
    change = await apply_service_toggle(body.id, body.enabled)
    await _audit(request, user, change)
    return change.response


@router.get("/components")
async def get_components(
    component_type: Literal["tool", "resource", "template", "prompt"] | None = None,
    namespace: str | None = None,
    _user: User = Depends(require_scope("mcp:read")),
):
    components = await list_components(component_type)
    return [item for item in components if namespace is None or item["namespace"] == namespace]


@router.put("/components/{component_type}/{name}/enabled")
async def update_component_enabled(
    request: Request,
    component_type: Literal["tool", "resource", "template", "prompt"],
    name: str,
    body: ComponentToggle,
    user: User = Depends(require_scope("mcp:write")),
):
    await set_component_enabled(server_id=body.server_id, component_type=component_type, name=name, enabled=body.enabled)
    await record_audit_event_async(
        user, action="mcp.component_toggle", resource_type=f"mcp_{component_type}",
        resource_id=name, metadata={"enabled": body.enabled, "server_id": body.server_id},
        **audit_request_context(request),
    )
    return {"success": True, "enabled": body.enabled}


@router.post("/tools/{name}/call")
async def invoke_tool(
    request: Request, name: str, body: ToolCallRequest,
    user: User = Depends(require_scope("mcp:write")),
):
    result = await call_tool(name, body.arguments)
    await record_audit_event_async(
        user, action="mcp.tool_call", resource_type="mcp_tool", resource_id=name,
        metadata={"argument_names": sorted(body.arguments)}, **audit_request_context(request),
    )
    return result


@router.get("/tokens")
async def get_tokens(_user: User = Depends(require_scope("mcp:read"))):
    return [{key: value for key, value in row.items() if key != "token"} for row in await list_tokens()]


@router.post("/tokens/issue")
async def issue_token(request: Request, body: TokenIssue, user: User = Depends(require_scope("mcp:write"))):
    if body.expires_in < 0 or (body.expires_in != 0 and body.expires_in < 86400):
        raise HTTPException(status_code=400, detail="Expires in must be zero or at least 1 day")
    token = await insert_token(body.name.strip() or "未命名 Token", body.expires_in)
    await record_audit_event_async(
        user, action="mcp.token_issue", resource_type="mcp_token",
        resource_id=body.name.strip() or "未命名 Token", metadata={"expires_in": body.expires_in},
        **audit_request_context(request),
    )
    return {"token": token}


@router.post("/tokens/delete")
async def remove_token(request: Request, body: TokenDelete, user: User = Depends(require_scope("mcp:write"))):
    if not await delete_token(body.id, None):
        raise HTTPException(status_code=404, detail="Token not found")
    await record_audit_event_async(
        user, action="mcp.token_delete", resource_type="mcp_token", resource_id=str(body.id or ""),
        **audit_request_context(request),
    )
    return {"success": True}


@router.post("/upload", response_model=McpUploadResponse)
async def upload_mcp(request: Request, body: McpUploadRequest, user: User = Depends(require_scope("mcp:submit"))):
    if actor_role(user) != "admin":
        # Validate now, before persisting a request that can never be installed.
        parse_mcp_manifest(body.manifest)
        try:
            normalized_visibility = normalize_visibility(body.visibility, strict=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        approval = await submit_mcp_upload(
            payload=body.model_dump(), submitted_by=actor_id(user),
            submitted_by_email=str(getattr(user, "email", "") or ""),
        )
        await notify_admins_of_submission(approval_id=str(approval["id"]), resource_type="mcp", submitter_email=str(getattr(user, "email", "") or ""))
        await record_audit_event_async(
            user, action="mcp.upload_submitted", resource_type="mcp_approval",
            resource_id=str(approval["id"]), metadata={"name": body.name.strip()},
            **audit_request_context(request),
        )
        return McpUploadResponse(
            success=True, name=body.name.strip(), visibility=normalized_visibility,
            status="pending", approval_id=str(approval["id"]),
        )
    change = await apply_mcp_upload(
        name=body.name, description=body.description, manifest=body.manifest,
        enabled=body.enabled, visibility=body.visibility, owner_user_id=actor_id(user),
    )
    await _audit(request, user, change)
    return McpUploadResponse(**change.response)


@router.post("/servers/test")
async def test_mcp_server(body: McpUploadRequest, _user: User = Depends(require_scope("mcp:write"))):
    _transport, config = parse_mcp_manifest(body.manifest)
    tools = await test_server_config(config)
    return {"success": True, "tools": tools}


@router.put("/servers/{server_name}/visibility")
async def update_mcp_server_visibility(
    request: Request, server_name: str, body: McpVisibilityRequest,
    user: User = Depends(require_scope("mcp:write")),
):
    change = await apply_mcp_server_visibility(server_name, body.visibility, user)
    await _audit(request, user, change)
    return change.response


@router.put("/servers/{server_id}/enabled")
async def update_mcp_server_enabled(
    request: Request, server_id: int, body: ComponentToggle,
    user: User = Depends(require_scope("mcp:write")),
):
    change = await apply_mcp_server_toggle(server_id, body.enabled, user)
    await _audit(request, user, change)
    return change.response


@router.delete("/servers/{server_id}")
async def delete_mcp_server(request: Request, server_id: int, user: User = Depends(require_scope("mcp:write"))):
    change = await remove_mcp_server(server_id, user)
    await _audit(request, user, change)
    return change.response


async def _audit(request: Request, user: User, change: Any) -> None:
    await record_audit_event_async(
        user, action=change.action, resource_type=change.resource_type,
        resource_id=change.resource_id, metadata=change.metadata,
        **audit_request_context(request),
    )
