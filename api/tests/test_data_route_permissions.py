import inspect
from types import SimpleNamespace
from api.auth.permissions import has_permission
from api.routes import collect, cve, skills


def user(role: str = "user"):
    return SimpleNamespace(role=role, is_superuser=False)


def test_readonly_security_data_permissions_are_available_to_guest():
    guest = user("guest")
    assert has_permission(guest, "cve:read")
    assert not has_permission(guest, "collect:write")


def test_user_can_run_collect_but_guest_cannot():
    assert has_permission(user("user"), "collect:write")
    assert not has_permission(user("guest"), "collect:write")


def test_collect_parse_requires_write_permission():
    source = inspect.getsource(collect.parse_url_to_markdown)
    assert 'require_permission("collect:write")' in source
    assert "record_audit_event" in source
    assert 'action="collect.parse"' in source


def test_cve_routes_require_read_or_admin_permission():
    search_source = inspect.getsource(cve.search_cve)
    update_source = inspect.getsource(cve.update_cve_database)
    assert 'require_permission("cve:read")' in search_source
    assert 'require_permission("admin:read")' in update_source
    assert "admin.cve.update" in update_source
    assert 'status="failure"' in update_source
    assert '"error": str(e)' in update_source


def test_skills_api_registers_real_upload_route():
    route_paths = {
        path
        for route in skills.router.routes
        if isinstance((path := getattr(route, "path", None)), str)
    }
    assert "/api/skills/upload" in route_paths
    assert "/api/skills/upload-request" not in route_paths
