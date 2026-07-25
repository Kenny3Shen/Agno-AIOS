from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast

from agno.os.scopes import AgentOSScope, has_required_scopes

# Product roles deliberately stay small:
# - admin: platform-level control through the AgentOS admin scope
# - user: normal workspace operations
Role = Literal["admin", "user"]
ADMIN_SCOPE = AgentOSScope.ADMIN.value

KNOWN_ROLES: frozenset[str] = frozenset({"admin", "user"})


class ActorLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def role(self) -> object: ...

    @property
    def is_superuser(self) -> bool: ...


USER_SCOPES: set[str] = {
    "sessions:read",
    "sessions:write",
    "traces:read",
    "memories:read",
    "memories:write",
    "memories:delete",
    "metrics:read",
    "knowledge:read",
    "knowledge:write",
    "knowledge:delete",
    "cve:read",
    "ip_blacklist:read",
    "collect:read",
    "collect:write",
    "skill:read",
    "mcp:read",
    "config:read",
    "workflows:read",
    "workflows:write",
    "workflows:run",
    "mcp:submit",
    "skill:submit",
    "approvals:read",
    "approvals:write",
    "evals:read",
}

ROLE_SCOPES: dict[Role, set[str]] = {
    "admin": {ADMIN_SCOPE},
    "user": USER_SCOPES,
}


@dataclass(frozen=True)
class ScopeClaims:
    role: Role
    scopes: list[str]


def actor_id(user: ActorLike) -> str:
    return str(getattr(user, "id", "") or "")


def actor_role(user: ActorLike) -> Role:
    return normalize_actor_role(
        getattr(user, "role", "user"),
        is_superuser=bool(getattr(user, "is_superuser", False)),
    )


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


def normalize_role(value: object, *, default: Role = "user") -> Role:
    """Coerce an API/DB role string to a known product role."""
    role = str(value or default).strip().lower()
    if role in KNOWN_ROLES:
        return cast(Role, role)
    return default


def normalize_actor_role(value: object, *, is_superuser: bool = False) -> Role:
    """Canonicalize a persisted actor role while preserving superuser authority."""
    return "admin" if is_superuser else normalize_role(value)
