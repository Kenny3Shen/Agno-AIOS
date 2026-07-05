from types import SimpleNamespace
from api.auth.permissions import actor_role, has_permission


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
