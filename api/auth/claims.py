from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from agno.os.scopes import AgentOSScope, has_required_scopes

Role = Literal["admin", "user", "guest"]
ADMIN_SCOPE = AgentOSScope.ADMIN.value


class ActorLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def role(self) -> object: ...

    @property
    def is_superuser(self) -> bool: ...

ROLE_SCOPES: dict[Role, set[str]] = {
    "admin": {ADMIN_SCOPE},
    "user": {
        "sessions:read",
        "sessions:write",
        "workflows:read",
        "workflows:write",
        "workflows:run",
        "traces:read",
        "memories:read",
        "memories:write",
        "memories:delete",
        "metrics:read",
        "collect:write",
        "cve:read",
        "knowledge:read",
        "knowledge:write",
        "knowledge:delete",
        "mcp:read",
        "mcp:submit",
        "skill:read",
        "skill:submit",
        "approvals:read",
        "config:read",
        "evals:read",
    },
    "guest": {
        "sessions:read",
        "traces:read",
        "memories:read",
        "metrics:read",
        "cve:read",
        "knowledge:read",
    },
}


@dataclass(frozen=True)
class ScopeClaims:
    role: Role
    scopes: list[str]


def actor_id(user: ActorLike) -> str:
    return str(getattr(user, "id", "") or "")


def actor_role(user: ActorLike) -> Role:
    if bool(getattr(user, "is_superuser", False)):
        return "admin"
    role = str(getattr(user, "role", "user") or "user").lower()
    if role == "admin":
        return "admin"
    if role == "guest":
        return "guest"
    return "user"


def actor_scopes(user: ActorLike) -> list[str]:
    scopes = set(ROLE_SCOPES[actor_role(user)])
    return sorted(scopes)


def has_scope(
    user: ActorLike,
    scope: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> bool:
    return has_required_scopes(
        actor_scopes(user),
        [scope],
        resource_type=resource_type,
        resource_id=resource_id,
        admin_scope=ADMIN_SCOPE,
    )


def scope_claims(user: ActorLike) -> ScopeClaims:
    role = actor_role(user)
    return ScopeClaims(
        role=role,
        scopes=actor_scopes(user),
    )


def scope_user_id(
    actor: ActorLike | None,
    requested_user_id: str | None,
) -> str | None:
    requested = (requested_user_id or "").strip() or None
    if actor is not None and has_scope(actor, ADMIN_SCOPE):
        return requested
    return actor_id(actor) if actor is not None else ""
