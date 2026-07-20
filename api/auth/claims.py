from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast

from agno.os.scopes import AgentOSScope, has_required_scopes

# Product roles:
# - admin: full control (AgentOS admin scope)
# - user: default operator (existing broad access; backward compatible)
# - analyst: day-to-day security investigation & chat
# - author: content / workflow / skill authoring
# - approver: HITL approval duty desk
# - auditor: read-only audit & compliance
# - guest: minimal read-only visitor
Role = Literal["admin", "user", "analyst", "author", "approver", "auditor", "guest"]
ADMIN_SCOPE = AgentOSScope.ADMIN.value

KNOWN_ROLES: frozenset[str] = frozenset(
    {"admin", "user", "analyst", "author", "approver", "auditor", "guest"}
)


class ActorLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def role(self) -> object: ...

    @property
    def is_superuser(self) -> bool: ...


# Shared building blocks so presets stay readable and consistent.
_READ_OPS = {
    "sessions:read",
    "traces:read",
    "memories:read",
    "metrics:read",
    "knowledge:read",
    "cve:read",
    "ip_blacklist:read",
    "collect:read",
    "skill:read",
    "mcp:read",
    "config:read",
}

ROLE_SCOPES: dict[Role, set[str]] = {
    "admin": {ADMIN_SCOPE},
    # Backward-compatible full operator (non-admin).
    "user": {
        *_READ_OPS,
        "sessions:write",
        "workflows:read",
        "workflows:write",
        "workflows:run",
        "memories:write",
        "memories:delete",
        "collect:write",
        "knowledge:write",
        "knowledge:delete",
        "mcp:submit",
        "skill:submit",
        "approvals:read",
        "evals:read",
    },
    # Security analyst: investigate, chat, run published workflows; no system config writes.
    "analyst": {
        *_READ_OPS,
        "sessions:write",
        "workflows:read",
        "workflows:run",
        "memories:write",
        "memories:delete",
        "knowledge:write",
        "collect:write",
        "approvals:read",
        "evals:read",
    },
    # Content / automation author: build knowledge, skills, workflows; submit MCP.
    "author": {
        *_READ_OPS,
        "sessions:write",
        "workflows:read",
        "workflows:write",
        "workflows:run",
        "knowledge:write",
        "knowledge:delete",
        "skill:submit",
        "mcp:submit",
        "collect:write",
        "memories:write",
    },
    # Approval duty: resolve HITL + review context; no content authoring.
    "approver": {
        "sessions:read",
        "sessions:write",
        "traces:read",
        "metrics:read",
        "knowledge:read",
        "memories:read",
        "approvals:read",
        "approvals:write",
        "workflows:read",
        "config:read",
    },
    # Compliance auditor: read audit trail, traces, evals; no mutations.
    "auditor": {
        "sessions:read",
        "traces:read",
        "metrics:read",
        "knowledge:read",
        "cve:read",
        "ip_blacklist:read",
        "collect:read",
        "memories:read",
        "evals:read",
        "audit:read",
        "approvals:read",
        "workflows:read",
        "config:read",
    },
    "guest": {
        "sessions:read",
        "traces:read",
        "memories:read",
        "metrics:read",
        "cve:read",
        "ip_blacklist:read",
        "collect:read",
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
    if role in KNOWN_ROLES:
        return cast(Role, role)
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


def normalize_role(value: object, *, default: Role = "user") -> Role:
    """Coerce an API/DB role string to a known product role."""
    role = str(value or default).strip().lower()
    if role in KNOWN_ROLES:
        return cast(Role, role)
    return default
