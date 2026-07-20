"""Single source of truth for user-level Skill and MCP availability."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from api.auth.claims import actor_id
from api.auth.visibility import can_read_resource
from api.mcp.config import list_mcp_servers
from api.persistence.capability_preferences import (
    CapabilityType,
    PreferenceState,
    clear_capability_preference,
    list_capability_preferences,
    set_capability_preference,
)
from api.services.skill_service import find_skill_dir, list_skill_infos

Preference = Literal["enabled", "disabled"]


class CapabilityItem(TypedDict):
    kind: CapabilityType
    capability_key: str
    name: str
    description: str
    platform_enabled: bool
    preference: Preference
    effective_enabled: bool
    unavailable_reason: str | None
    visibility: str
    owner_user_id: str
    server_id: int | None
    namespace: str | None
    risk: str


class RequiredSkillIssue(TypedDict):
    name: str
    capability_key: str | None
    reason: Literal[
        "not_found", "not_authorized", "platform_disabled", "user_disabled"
    ]


def _preference_for(
    preferences: dict[tuple[str, str], PreferenceState],
    kind: CapabilityType,
    key: str,
) -> Preference:
    """Missing preference rows default to enabled (users opt out)."""
    state = preferences.get((kind, key))
    return "disabled" if state == "disabled" else "enabled"


def _effective(
    *, platform_enabled: bool, preference: Preference
) -> tuple[bool, str | None]:
    if not platform_enabled:
        return False, "platform_disabled"
    if preference == "disabled":
        return False, "user_disabled"
    return True, None


async def list_capabilities_for_actor(actor: Any) -> list[CapabilityItem]:
    """List visible resources with server-computed effective state.

    This catalog deliberately includes disabled entries so users can preserve a
    preference for a temporarily disabled platform resource and understand why
    it is not currently active.
    """
    user_id = actor_id(actor)
    preferences = await list_capability_preferences(user_id) if user_id else {}
    items: list[CapabilityItem] = []

    for skill in list_skill_infos(actor, include_detail=False):
        key = str(skill["capability_key"])
        preference = _preference_for(preferences, "skill", key)
        enabled, reason = _effective(
            platform_enabled=bool(skill["enabled"]),
            preference=preference,
        )
        items.append(
            {
                "kind": "skill",
                "capability_key": key,
                "name": str(skill["name"]),
                "description": str(skill["description"]),
                "platform_enabled": bool(skill["enabled"]),
                "preference": preference,
                "effective_enabled": enabled,
                "unavailable_reason": reason,
                "visibility": str(skill["visibility"]),
                "owner_user_id": str(skill["owner_user_id"]),
                "server_id": None,
                "namespace": None,
                "risk": "script" if bool(skill["has_scripts"]) else "standard",
            }
        )

    for row in await list_mcp_servers():
        if not can_read_resource(actor, row):
            continue
        server_id = int(row["id"])
        key = str(server_id)
        preference = _preference_for(preferences, "mcp_server", key)
        enabled, reason = _effective(
            platform_enabled=bool(row.get("enabled", False)),
            preference=preference,
        )
        items.append(
            {
                "kind": "mcp_server",
                "capability_key": key,
                "name": str(row["name"]),
                "description": str(row.get("description") or ""),
                "platform_enabled": bool(row.get("enabled", False)),
                "preference": preference,
                "effective_enabled": enabled,
                "unavailable_reason": reason,
                "visibility": str(row.get("visibility") or "private"),
                "owner_user_id": str(row.get("owner_user_id") or ""),
                "server_id": server_id,
                "namespace": str(row.get("namespace") or ""),
                "risk": "external" if str(row.get("server_type")) == "external" else "builtin",
            }
        )
    return items


async def set_preference_for_actor(
    actor: Any,
    *,
    kind: CapabilityType,
    capability_key: str,
    state: Preference,
) -> CapabilityItem | None:
    """Store a user's enablement after resolving the key in their visible catalog.

    Enabled is stored sparsely: clearing the row means enabled for the user.
    Disabled always writes an explicit override.
    """
    items = await list_capabilities_for_actor(actor)
    item = next(
        (
            candidate
            for candidate in items
            if candidate["kind"] == kind and candidate["capability_key"] == capability_key
        ),
        None,
    )
    if item is None:
        return None
    user_id = actor_id(actor)
    if not user_id:
        return None
    if state == "enabled":
        await clear_capability_preference(
            user_id=user_id, capability_type=kind, capability_key=capability_key
        )
    else:
        await set_capability_preference(
            user_id=user_id,
            capability_type=kind,
            capability_key=capability_key,
            state="disabled",
        )
    refreshed = await list_capabilities_for_actor(actor)
    return next(
        (
            candidate
            for candidate in refreshed
            if candidate["kind"] == kind and candidate["capability_key"] == capability_key
        ),
        None,
    )


async def effective_skill_dirs_for_actor(
    actor: Any,
    requested_names: list[str] | None = None,
) -> list[Path]:
    """Resolve user-effective Local Skill directories, optionally by binding."""
    requested = {str(value).strip() for value in requested_names or [] if str(value).strip()}
    result: list[Path] = []
    for item in await list_capabilities_for_actor(actor):
        if item["kind"] != "skill" or not item["effective_enabled"]:
            continue
        if requested and item["name"] not in requested and item["capability_key"] not in requested:
            continue
        directory = find_skill_dir(item["capability_key"])
        if directory is not None:
            result.append(directory)
    return result


async def effective_mcp_server_ids_for_actor(actor: Any) -> set[int]:
    return {
        int(item["server_id"])
        for item in await list_capabilities_for_actor(actor)
        if item["kind"] == "mcp_server"
        and item["effective_enabled"]
        and item["server_id"] is not None
    }


async def effective_mcp_server_names_for_actor(actor: Any) -> list[str]:
    return [
        item["name"]
        for item in await list_capabilities_for_actor(actor)
        if item["kind"] == "mcp_server" and item["effective_enabled"]
    ]


async def mcp_server_is_effective_for_actor(actor: Any, server_id: int | None) -> bool:
    if server_id is None:
        return False
    return int(server_id) in await effective_mcp_server_ids_for_actor(actor)


async def required_skill_issues_for_actor(
    actor: Any, skill_names: list[str]
) -> list[RequiredSkillIssue]:
    """Explain every unusable explicit workflow Skill binding."""
    clean_names = [str(value).strip() for value in skill_names if str(value).strip()]
    if not clean_names:
        return []
    visible = await list_capabilities_for_actor(actor)
    visible_skills = {
        item["name"]: item for item in visible if item["kind"] == "skill"
    } | {
        item["capability_key"]: item for item in visible if item["kind"] == "skill"
    }
    issues: list[RequiredSkillIssue] = []
    for name in dict.fromkeys(clean_names):
        item = visible_skills.get(name)
        if item is None:
            # A directory may exist but be private to another user.  Never
            # disclose that distinction to the caller.
            issues.append(
                {"name": name, "capability_key": None, "reason": "not_authorized"}
            )
            continue
        if item["effective_enabled"]:
            continue
        reason = str(item["unavailable_reason"] or "not_found")
        if reason not in {"platform_disabled", "user_disabled"}:
            reason = "not_found"
        issues.append(
            {
                "name": name,
                "capability_key": item["capability_key"],
                "reason": reason,  # type: ignore[typeddict-item]
            }
        )
    return issues
