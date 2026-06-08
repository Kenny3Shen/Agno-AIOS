from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.mcp.config import (
    HIAGENT_CACHE_DB,
    MCP_CONFIG_FILE,
    MCP_TOKENS_DB,
    SERVICE_IDS,
    delete_token,
    insert_token,
    list_tokens,
    normalize_hiagents,
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


@router.get("/config")
async def get_config() -> dict[str, Any]:
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
async def update_config(body: ServiceToggle):
    if body.id not in SERVICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid service ID")

    data = read_mcp_config()
    mcp_cfg = data.setdefault("mcp", {})
    if not isinstance(mcp_cfg, dict):
        data["mcp"] = {}
        mcp_cfg = data["mcp"]

    mcp_cfg[body.id] = body.enabled
    write_mcp_config(data)
    return {"success": True, "control_mode": "integrated", "restart_required": True}


@router.get("/tokens")
async def get_tokens():
    return list_tokens()


@router.post("/tokens/issue")
async def issue_token(body: TokenIssue):
    expires_in = int(body.expires_in)
    if expires_in < 0:
        raise HTTPException(status_code=400, detail="Invalid expires_in")
    if expires_in != 0 and expires_in < 86400:
        raise HTTPException(status_code=400, detail="Expires in must be at least 1 day")

    token = insert_token(name=body.name.strip() or "未命名 Token", expires_in=expires_in)
    return {"token": token}


@router.post("/tokens/delete")
async def remove_token(body: TokenDelete):
    deleted = delete_token(body.id, body.token)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"success": True}


@router.get("/hiagent")
async def list_hiagent():
    data = read_mcp_config()
    return normalize_hiagents(data.get("hiagent", []))


@router.post("/hiagent/add")
async def add_hiagent(body: HiAgentAdd):
    name = body.name.strip()
    url = body.url.strip()
    if not name or not url:
        raise HTTPException(status_code=400, detail="name 和 url 不能为空")

    data = read_mcp_config()
    entries = normalize_hiagents(data.get("hiagent", []))
    if any(entry["url"] == url for entry in entries):
        raise HTTPException(status_code=409, detail="该 URL 已存在")

    entries.append(
        {
            "name": name,
            "url": url,
            "description": body.description.strip(),
            "enabled": body.enabled,
        }
    )
    data["hiagent"] = entries
    write_mcp_config(data)
    return {"success": True, "restart_required": True}


@router.post("/hiagent/update")
async def update_hiagent(body: HiAgentUpdate):
    target_url = (body.target_url or body.url or "").strip()
    new_url = body.url.strip()
    if not target_url:
        raise HTTPException(status_code=400, detail="target_url 不能为空")

    data = read_mcp_config()
    entries = normalize_hiagents(data.get("hiagent", []))

    if new_url and new_url != target_url and any(entry["url"] == new_url for entry in entries):
        raise HTTPException(status_code=409, detail="该 URL 已存在")

    found = False
    for entry in entries:
        if entry["url"] == target_url:
            if body.name is not None:
                entry["name"] = body.name
            if body.description is not None:
                entry["description"] = body.description
            if body.enabled is not None:
                entry["enabled"] = body.enabled
            if new_url:
                entry["url"] = new_url
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="未找到该条目")

    data["hiagent"] = entries
    write_mcp_config(data)
    return {"success": True, "restart_required": True}


@router.post("/hiagent/delete")
async def delete_hiagent(body: HiAgentDelete):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="url 不能为空")

    data = read_mcp_config()
    entries = normalize_hiagents(data.get("hiagent", []))
    next_entries = [entry for entry in entries if entry["url"] != url]
    if len(next_entries) == len(entries):
        raise HTTPException(status_code=404, detail="未找到该条目")

    data["hiagent"] = next_entries
    write_mcp_config(data)
    return {"success": True, "restart_required": True}
