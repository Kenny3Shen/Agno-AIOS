import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from agno.os.middleware.jwt import JWTMiddleware

from api.auth import claims
from api.auth.claims import (
    actor_role,
    has_permission,
    permission_claims,
    scope_user_id,
)

ADMIN_SCOPE = "agent_os:admin"


def user(role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=uuid4(), role=role, is_superuser=is_superuser)


def test_superuser_is_admin():
    actor = user("guest", is_superuser=True)

    assert actor_role(actor) == "admin"
    assert has_permission(actor, ADMIN_SCOPE)
    assert has_permission(actor, "traces:read")


def test_admin_claims_use_agentos_admin_scope():
    claims = permission_claims(user("guest", is_superuser=True))

    assert claims.role == "admin"
    assert claims.scopes == [ADMIN_SCOPE]
    assert claims.permissions == [ADMIN_SCOPE]


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
        "skill:read",
        "config:read",
        "evals:read",
    ):
        assert has_permission(actor, scope), scope

    for scope in (
        "session:read:own",
        "trace:read:own",
        "memory:write:own",
        "agent_eval:read",
        "settings:read",
        "config:write",
        "mcp:write",
        ADMIN_SCOPE,
    ):
        assert not has_permission(actor, scope), scope


def test_guest_scopes_are_read_only():
    actor = user("guest")

    assert has_permission(actor, "sessions:read")
    assert has_permission(actor, "traces:read")
    assert has_permission(actor, "memories:read")
    assert has_permission(actor, "metrics:read")
    assert has_permission(actor, "cve:read")
    assert has_permission(actor, "knowledge:read")
    assert not has_permission(actor, "sessions:write")
    assert not has_permission(actor, "memories:write")
    assert not has_permission(actor, "knowledge:write")
    assert not has_permission(actor, "evals:read")


def test_evals_permissions_are_role_scoped():
    admin = user("admin")
    normal_user = user("user")
    guest = user("guest")

    assert has_permission(admin, "evals:read")
    assert has_permission(admin, "evals:write")
    assert has_permission(admin, "evals:delete")
    assert has_permission(normal_user, "evals:read")
    assert not has_permission(normal_user, "evals:write")
    assert not has_permission(normal_user, "evals:delete")
    assert not has_permission(guest, "evals:read")


def test_permission_claims_are_expanded_for_frontend_consumers():
    claims = permission_claims(user("user"))

    assert claims.role == "user"
    assert "sessions:read" in claims.permissions
    assert "evals:read" in claims.permissions
    assert "session:read:own" not in claims.permissions
    assert "agent_eval:read" not in claims.permissions


def test_user_read_serializes_scope_claims_without_recursion():
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
    assert payload["permissions"] == [ADMIN_SCOPE]


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


def test_main_app_installs_agno_jwt_middleware():
    from api.main import AGENTOS_JWT_EXCLUDED_ROUTE_PATHS, app

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
    assert "/api/auth/*" in AGENTOS_JWT_EXCLUDED_ROUTE_PATHS
    assert "/assets/*" in AGENTOS_JWT_EXCLUDED_ROUTE_PATHS


@pytest.mark.parametrize(
    "module_name",
    [
        "api.auth.claims",
        "api.auth.ownership",
        "api.auth.schemas",
        "api.services.agent_eval_case_store",
        "api.services.agent_eval_runner",
        "api.services.approval_control_service",
        "api.services.audit_service",
        "api.services.chat_session_service",
        "api.services.os_control_service",
        "api.services.security_policy",
        "api.services.tracing_service",
    ],
)
def test_claims_and_service_modules_do_not_import_fastapi_user_dependencies(module_name):
    script = (
        "import sys\n"
        f"import {module_name}\n"
        "print('api.auth.users' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"
