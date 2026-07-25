from types import SimpleNamespace
from uuid import uuid4

import jwt
from agno.os.middleware.jwt import JWTMiddleware
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from api.auth import router as auth_router
from api.auth import claims
from api.auth.claims import actor_role, has_scope, scope_claims, scope_user_id
from api.tests.route_fakes import route_dependency

ADMIN_SCOPE = "agent_os:admin"


def user(role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=uuid4(), role=role, is_superuser=is_superuser)


def test_superuser_is_admin():
    actor = user("user", is_superuser=True)

    assert actor_role(actor) == "admin"
    assert has_scope(actor, ADMIN_SCOPE)
    assert has_scope(actor, "traces:read")


def test_admin_claims_use_agentos_admin_scope():
    actor_claims = scope_claims(user("admin"))

    assert actor_claims.role == "admin"
    assert actor_claims.scopes == [ADMIN_SCOPE]


def test_user_scopes_cover_normal_workspace_operations():
    actor = user()

    for scope in (
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
        "collect:read",
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
        "approvals:write",
        "config:read",
        "evals:read",
    ):
        assert has_scope(actor, scope), scope

    for scope in (
        "config:write",
        "mcp:write",
        "skill:write",
        "evals:write",
        "evals:delete",
        "audit:read",
        ADMIN_SCOPE,
    ):
        assert not has_scope(actor, scope), scope


def test_retired_and_unknown_roles_fail_closed_to_user():
    for legacy_role in (
        "analyst",
        "author",
        "approver",
        "auditor",
        "guest",
        "not-a-real-role",
    ):
        actor = user(legacy_role)
        assert actor_role(actor) == "user"
        assert has_scope(actor, "sessions:write")
        assert not has_scope(actor, ADMIN_SCOPE)


def test_scope_claims_are_expanded_as_agentos_scopes():
    actor_claims = scope_claims(user())

    assert actor_claims.role == "user"
    assert "sessions:read" in actor_claims.scopes
    assert "approvals:write" in actor_claims.scopes
    assert "audit:read" not in actor_claims.scopes
    assert "session:read:own" not in actor_claims.scopes
    assert "agent_eval:read" not in actor_claims.scopes


def test_user_read_normalizes_retired_roles_and_superusers():
    from api.auth.schemas import UserRead

    retired = UserRead.model_validate(
        {
            "id": uuid4(),
            "email": "member@example.com",
            "role": "author",
            "is_active": True,
            "is_superuser": False,
            "is_verified": False,
        }
    ).model_dump()
    superuser = UserRead(
        id=uuid4(),
        email="admin@example.com",
        role="user",
        is_active=True,
        is_superuser=True,
        is_verified=False,
    ).model_dump()

    assert retired["role"] == "user"
    assert "approvals:write" in retired["scopes"]
    assert superuser["role"] == "admin"
    assert superuser["scopes"] == [ADMIN_SCOPE]
    assert "permissions" not in retired


def test_public_user_schemas_do_not_expose_role_assignment():
    from api.auth.schemas import UserCreate, UserUpdate

    assert "role" not in UserCreate.model_fields
    assert "role" not in UserUpdate.model_fields
    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "email": "member@example.com",
                "password": "secure-password",
                "role": "admin",
            }
        )
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({"role": "admin"})


def test_admin_role_update_only_accepts_the_two_product_roles():
    from api.auth.router import AdminRoleUpdate

    assert AdminRoleUpdate(role="admin").role == "admin"
    assert AdminRoleUpdate(role="user").role == "user"
    with pytest.raises(ValidationError):
        AdminRoleUpdate.model_validate({"role": "author"})


@pytest.mark.asyncio
async def test_role_catalog_is_admin_only_and_contains_two_roles():
    dependency = route_dependency(auth_router.router, "list_role_presets")
    with pytest.raises(HTTPException) as exc:
        dependency(user=user())
    assert exc.value.status_code == 403

    catalog = await auth_router.list_role_presets(_admin=user("admin"))

    assert [preset["role"] for preset in catalog["data"]] == ["admin", "user"]


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

    actor = user("admin")
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
    assert payload["role"] == "admin"
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
