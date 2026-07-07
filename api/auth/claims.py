from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["admin", "user", "guest"]

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    "admin": {"*"},
    "user": {
        "session:read:own",
        "session:write:own",
        "trace:read:own",
        "memory:read:own",
        "memory:write:own",
        "metrics:read:own",
        "collect:write",
        "cve:read",
        "knowledge:read",
        "knowledge:write",
        "mcp:read",
        "skill:read",
        "settings:read",
        "agent_eval:read",
    },
    "guest": {
        "session:read:own",
        "trace:read:own",
        "memory:read:own",
        "metrics:read:own",
        "cve:read",
        "knowledge:read",
    },
}


@dataclass(frozen=True)
class PermissionClaims:
    role: Role
    permissions: list[str]


def actor_id(user: Any) -> str:
    return str(getattr(user, "id", "") or "")


def actor_role(user: Any) -> Role:
    if bool(getattr(user, "is_superuser", False)):
        return "admin"
    role = str(getattr(user, "role", "user") or "user").lower()
    if role == "admin":
        return "admin"
    if role == "guest":
        return "guest"
    return "user"


def has_permission(user: Any, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS[actor_role(user)]
    return "*" in permissions or permission in permissions


def permission_claims(user: Any) -> PermissionClaims:
    role = actor_role(user)
    permissions = ROLE_PERMISSIONS[role]
    return PermissionClaims(
        role=role,
        permissions=["*"] if "*" in permissions else sorted(permissions),
    )


def scope_user_id(
    actor: Any | None,
    requested_user_id: str | None,
    any_permission: str,
) -> str | None:
    requested = (requested_user_id or "").strip() or None
    if actor is not None and has_permission(actor, any_permission):
        return requested
    return actor_id(actor) if actor is not None else ""
