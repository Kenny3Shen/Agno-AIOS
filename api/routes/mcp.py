from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth.models import User
from api.auth.permissions import require_permission
from api.services.audit_service import (
    AuditRequestContext,
    audit_request_context,
    record_audit_event_async,
)
from api.services.mcp_config_service import (
    McpConfigChange,
    apply_mcp_upload_async,
    apply_service_toggle_async,
)
from api.mcp.config import (
    MCP_CONFIG_FILE,
    MCP_TOKENS_DB,
    delete_token,
    insert_token,
    list_tokens,
    read_mcp_config_async,
    services_from_config_async,
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


class McpUploadRequest(BaseModel):
    name: str
    description: str = ""
    manifest: str = ""
    enabled: bool = True


class McpUploadResponse(BaseModel):
    success: bool
    name: str
    kind: str
    restart_required: bool = True


async def _record_config_change(
    user: User,
    change: McpConfigChange,
    request_context: AuditRequestContext,
) -> None:
    await record_audit_event_async(
        user,
        action=change.action,
        resource_type=change.resource_type,
        resource_id=change.resource_id,
        metadata=change.metadata,
        **request_context,
    )


@router.get("/config")
async def get_config(_user: User = Depends(require_permission("mcp:read"))) -> dict[str, Any]:
    data = await read_mcp_config_async()
    return {
        "services": await services_from_config_async(data),
        "control_mode": "integrated",
        "fastmcp": "in-process",
        "mcp_url": "/mcp/",
        "config_path": str(MCP_CONFIG_FILE),
        "tokens_db_path": str(MCP_TOKENS_DB),
    }


@router.post("/config")
async def update_config(
    request: Request,
    body: ServiceToggle,
    user: User = Depends(require_permission("mcp:write")),
):
    change = await apply_service_toggle_async(body.id, body.enabled)
    await _record_config_change(user, change, audit_request_context(request))
    return change.response


@router.get("/tokens")
async def get_tokens(_user: User = Depends(require_permission("mcp:read"))):
    return await list_tokens()


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

    token = await insert_token(
        name=body.name.strip() or "未命名 Token",
        expires_in=expires_in,
    )
    await record_audit_event_async(
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
    deleted = await delete_token(body.id, body.token)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    await record_audit_event_async(
        user,
        action="mcp.token_delete",
        resource_type="mcp_token",
        resource_id=str(body.id or body.token or ""),
        **audit_request_context(request),
    )
    return {"success": True}


@router.post("/upload", response_model=McpUploadResponse)
async def upload_mcp(
    request: Request,
    body: McpUploadRequest,
    user: User = Depends(require_permission("mcp:write")),
):
    """上传 MCP manifest。"""
    change = await apply_mcp_upload_async(
        name=body.name,
        description=body.description,
        manifest=body.manifest,
        enabled=body.enabled,
    )
    await _record_config_change(user, change, audit_request_context(request))
    return McpUploadResponse(**change.response)
