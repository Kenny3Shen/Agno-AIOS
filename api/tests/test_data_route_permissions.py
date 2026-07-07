from types import SimpleNamespace
from fastapi import HTTPException
from fastapi.routing import APIRoute
import pytest
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


def route_dependency(router, endpoint_name: str):
    for route in router.routes:
        if isinstance(route, APIRoute) and route.endpoint.__name__ == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_collect_parse_rejects_guest_without_write_permission():
    dependency = route_dependency(collect.router, "parse_url_to_markdown")

    with pytest.raises(HTTPException) as exc:
        dependency(user=user("guest"))

    assert exc.value.status_code == 403


def test_cve_search_allows_guest_reader():
    dependency = route_dependency(cve.router, "search_cve")

    assert dependency(user=user("guest")).role == "guest"


def test_cve_update_rejects_non_admin_user():
    dependency = route_dependency(cve.router, "update_cve_database")

    with pytest.raises(HTTPException) as exc:
        dependency(user=user("user"))

    assert exc.value.status_code == 403


def test_skills_api_registers_real_upload_route():
    route_paths = {
        path
        for route in skills.router.routes
        if isinstance((path := getattr(route, "path", None)), str)
    }
    assert "/api/skills/upload" in route_paths
    assert "/api/skills/upload-request" not in route_paths
