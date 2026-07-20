from types import SimpleNamespace
from fastapi import HTTPException
import pytest
from api.auth.claims import has_scope
from api.routes import collect, cve
from api.tests.route_fakes import route_dependency


def user(role: str = "user"):
    return SimpleNamespace(role=role, is_superuser=False)


def test_readonly_security_data_permissions_are_available_to_guest():
    guest = user("guest")
    assert has_scope(guest, "cve:read")
    assert has_scope(guest, "collect:read")
    assert not has_scope(guest, "collect:write")


def test_user_can_run_collect_but_guest_cannot():
    assert has_scope(user("user"), "collect:read")
    assert has_scope(user("user"), "collect:write")
    assert not has_scope(user("guest"), "collect:write")


def test_collect_search_allows_guest_reader():
    dependency = route_dependency(collect.router, "search_collect_articles_route")
    assert dependency(user=user("guest")).role == "guest"


def test_collect_crawl_rejects_non_admin_user():
    dependency = route_dependency(collect.router, "crawl_collect_sources")
    with pytest.raises(HTTPException) as exc:
        dependency(user=user("user"))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["user", "analyst", "author", "approver", "auditor", "guest"])
def test_collect_bulk_reparse_rejects_non_admin_roles(role: str):
    """A bulk retry can trigger network work and is restricted to administrators."""
    dependency = route_dependency(collect.router, "reparse_failed_collect_articles_route")

    with pytest.raises(HTTPException) as exc:
        dependency(user=user(role))

    assert exc.value.status_code == 403


def test_collect_bulk_reparse_allows_admin():
    dependency = route_dependency(collect.router, "reparse_failed_collect_articles_route")

    assert dependency(user=user("admin")).role == "admin"


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
