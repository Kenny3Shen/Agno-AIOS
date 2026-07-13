from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from agno.os.middleware.jwt import JWTMiddleware

from api.auth import claims
from api.auth.claims import (
    actor_role,
    has_scope,
    scope_claims,
    scope_user_id,
)

ADMIN_SCOPE = "agent_os:admin"


def user(role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=uuid4(), role=role, is_superuser=is_superuser)


def test_superuser_is_admin():
    actor = user("guest", is_superuser=True)

    assert actor_role(actor) == "admin"
    assert has_scope(actor, ADMIN_SCOPE)
    assert has_scope(actor, "traces:read")


def test_admin_claims_use_agentos_admin_scope():
    claims = scope_claims(user("guest", is_superuser=True))

    assert claims.role == "admin"
    assert claims.scopes == [ADMIN_SCOPE]


def test_user_scopes_use_agentos_resource_names():
    actor = user("user")

    for scope in (
        "sessions:read",
        "sessions:write",
        "traces:read",
        "memories:read",
        "memories:write",
        "memories:delete",
        "metrics:read",
        "collect:write",
        "cve:read",
        "knowledge:read",
        "knowledge:write",
        "mcp:read",
        "mcp:submit",
        "skill:read",
        "skill:submit",
        "config:read",
        "evals:read",
    ):
        assert has_scope(actor, scope), scope

    for scope in (
        "session:read:own",
        "trace:read:own",
        "memory:write:own",
        "agent_eval:read",
        "settings:read",
        "config:write",
        "mcp:write",
        "skill:write",
        ADMIN_SCOPE,
    ):
        assert not has_scope(actor, scope), scope


def test_guest_scopes_are_read_only():
    actor = user("guest")

    assert has_scope(actor, "sessions:read")
    assert has_scope(actor, "traces:read")
    assert has_scope(actor, "memories:read")
    assert has_scope(actor, "metrics:read")
    assert has_scope(actor, "cve:read")
    assert has_scope(actor, "knowledge:read")
    assert not has_scope(actor, "sessions:write")
    assert not has_scope(actor, "memories:write")
    assert not has_scope(actor, "knowledge:write")
    assert not has_scope(actor, "evals:read")


def test_evals_permissions_are_role_scoped():
    admin = user("admin")
    normal_user = user("user")
    guest = user("guest")

    assert has_scope(admin, "evals:read")
    assert has_scope(admin, "evals:write")
    assert has_scope(admin, "evals:delete")
    assert has_scope(normal_user, "evals:read")
    assert not has_scope(normal_user, "evals:write")
    assert not has_scope(normal_user, "evals:delete")
    assert not has_scope(guest, "evals:read")


def test_scope_claims_are_expanded_as_agentos_scopes():
    user_claims = scope_claims(user("user"))

    assert user_claims.role == "user"
    assert "sessions:read" in user_claims.scopes
    assert "evals:read" in user_claims.scopes
    assert "session:read:own" not in user_claims.scopes
    assert "agent_eval:read" not in user_claims.scopes


def test_user_read_serializes_scopes_without_permissions_alias():
    from api.auth.schemas import UserRead

    payload = UserRead(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        is_active=True,
        is_superuser=True,
        is_verified=False,
    ).model_dump()

    assert payload["scopes"] == [ADMIN_SCOPE]
    assert "permissions" not in payload


def test_scope_user_id_uses_actor_for_ordinary_users():
    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)

    assert scope_user_id(actor, "other-user") == "u1"


def test_scope_user_id_allows_admin_requested_user_or_all_users():
    admin = user("admin")

    assert scope_user_id(admin, "u2") == "u2"
    assert scope_user_id(admin, None) is None


@pytest.mark.asyncio
async def test_fastapi_users_jwt_embeds_agentos_scopes():
    from api.auth.users import ScopedJWTStrategy

    actor = user("admin", is_superuser=True)
    secret = "test-secret-with-at-least-32-bytes"
    strategy = ScopedJWTStrategy(secret=secret, lifetime_seconds=60)

    token = await strategy.write_token(actor)
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )

    assert payload["sub"] == str(actor.id)
    assert payload["aud"] == ["fastapi-users:auth"]
    assert payload["scopes"] == [ADMIN_SCOPE]


def test_main_app_installs_jwt_middleware():
    from api.main import JWT_EXCLUDED_ROUTE_PATHS, app

    assert claims.ADMIN_SCOPE == ADMIN_SCOPE
    middleware = next(
        (item for item in app.user_middleware if item.cls is JWTMiddleware),
        None,
    )

    assert middleware is not None
    assert middleware.kwargs["algorithm"] == "HS256"
    assert middleware.kwargs["authorization"] is True
    assert middleware.kwargs["admin_scope"] == ADMIN_SCOPE
    assert middleware.kwargs["user_isolation"] is True
    assert "/api/auth/*" in JWT_EXCLUDED_ROUTE_PATHS
    assert "/" in JWT_EXCLUDED_ROUTE_PATHS
