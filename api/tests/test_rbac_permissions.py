import subprocess
import sys
from types import SimpleNamespace

from api.auth.claims import actor_role, has_permission, permission_claims, scope_user_id
import pytest


def user(role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(role=role, is_superuser=is_superuser)


def test_superuser_is_admin():
    assert actor_role(user("guest", is_superuser=True)) == "admin"
    assert has_permission(user("guest", is_superuser=True), "trace:read:any")


def test_admin_can_read_and_write_all_supported_resources():
    actor = user("admin")
    for permission in (
        "session:read:any",
        "session:write:any",
        "trace:read:any",
        "knowledge:write",
        "mcp:write",
        "skill:write",
        "settings:write",
        "audit:read",
    ):
        assert has_permission(actor, permission), permission


def test_user_is_own_resource_only_and_not_config_writer():
    actor = user("user")
    assert has_permission(actor, "session:read:own")
    assert has_permission(actor, "session:write:own")
    assert has_permission(actor, "trace:read:own")
    assert has_permission(actor, "knowledge:write")
    assert not has_permission(actor, "session:read:any")
    assert not has_permission(actor, "mcp:write")
    assert not has_permission(actor, "settings:write")


def test_guest_is_read_only_for_owned_resources():
    actor = user("guest")
    assert has_permission(actor, "session:read:own")
    assert has_permission(actor, "trace:read:own")
    assert has_permission(actor, "knowledge:read")
    assert not has_permission(actor, "session:write:own")
    assert not has_permission(actor, "knowledge:write")


def test_agent_eval_permissions_are_role_scoped():
    admin = user("admin")
    normal_user = user("user")
    guest = user("guest")

    assert has_permission(admin, "agent_eval:read")
    assert has_permission(admin, "agent_eval:write")
    assert has_permission(admin, "agent_eval:run")
    assert has_permission(normal_user, "agent_eval:read")
    assert not has_permission(normal_user, "agent_eval:write")
    assert not has_permission(normal_user, "agent_eval:run")
    assert not has_permission(guest, "agent_eval:read")


def test_permission_claims_are_expanded_for_frontend_consumers():
    claims = permission_claims(user("user"))

    assert claims.role == "user"
    assert "session:read:own" in claims.permissions
    assert "agent_eval:read" in claims.permissions
    assert "*" not in claims.permissions


def test_admin_permission_claims_keep_wildcard_authority():
    claims = permission_claims(user("guest", is_superuser=True))

    assert claims.role == "admin"
    assert claims.permissions == ["*"]


def test_scope_user_id_uses_actor_for_ordinary_users():
    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)

    assert scope_user_id(actor, "other-user", "session:read:any") == "u1"


def test_scope_user_id_allows_admin_requested_user_or_all_users():
    admin = user("admin")

    assert scope_user_id(admin, "u2", "session:read:any") == "u2"
    assert scope_user_id(admin, None, "session:read:any") is None


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


def test_permissions_module_keeps_compatibility_exports():
    from api.auth.permissions import (
        assert_owned_resource,
        actor_id,
        actor_role,
        has_permission,
        permission_claims,
        scope_user_id,
    )

    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)

    assert actor_id(actor) == "u1"
    assert actor_role(actor) == "user"
    assert has_permission(actor, "session:read:own")
    assert permission_claims(actor).role == "user"
    assert scope_user_id(actor, "other", "session:read:any") == "u1"
    assert_owned_resource(actor, owner_user_id="u1", resource_name="Session")
