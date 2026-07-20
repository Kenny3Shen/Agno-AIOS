"""Current-user Skill and MCP preference APIs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth.claims import has_scope
from api.auth.models import User
from api.auth.users import current_active_user
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.capability_policy_service import (
    list_capabilities_for_actor,
    set_preference_for_actor,
)

router = APIRouter(prefix="/api/me/capabilities", tags=["Capabilities"])

CapabilityKind = Literal["skill", "mcp_server"]
Preference = Literal["enabled", "disabled"]


class CapabilityPreferenceRequest(BaseModel):
    state: Preference


def _read_scope(kind: CapabilityKind) -> str:
    return "skill:read" if kind == "skill" else "mcp:read"


@router.get("")
async def list_my_capabilities(user: User = Depends(current_active_user)):
    items = await list_capabilities_for_actor(user)
    return {
        "data": [
            item
            for item in items
            if has_scope(user, _read_scope(item["kind"]))
        ]
    }


@router.put("/{kind}/{capability_key}/preference")
async def set_my_capability_preference(
    kind: CapabilityKind,
    capability_key: str,
    body: CapabilityPreferenceRequest,
    request: Request,
    user: User = Depends(current_active_user),
):
    if not has_scope(user, _read_scope(kind)):
        raise HTTPException(status_code=403, detail="权限不足")
    item = await set_preference_for_actor(
        user,
        kind=kind,
        capability_key=capability_key,
        state=body.state,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    await record_audit_event_async(
        user,
        action="capability.preference_update",
        resource_type=kind,
        resource_id=capability_key,
        metadata={"state": body.state, "effective_enabled": item["effective_enabled"]},
        **audit_request_context(request),
    )
    return item
