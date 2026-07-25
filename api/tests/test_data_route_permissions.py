from types import SimpleNamespace
from fastapi import HTTPException
import pytest
from api.auth.claims import has_scope
from api.routes import collect, cve
from api.tests.route_fakes import route_dependency


def user(role: str = "user"):
    return SimpleNamespace(role=role, is_superuser=False)


def test_normal_user_has_security_data_permissions():
    actor = user()
    assert has_scope(actor, "cve:read")
    assert has_scope(actor, "collect:read")
    assert has_scope(actor, "collect:write")


def test_user_can_run_collect():
    assert has_scope(user("user"), "collect:read")
    assert has_scope(user("user"), "collect:write")


def test_collect_search_allows_user():
    dependency = route_dependency(collect.router, "search_collect_articles_route")
    assert dependency(user=user()).role == "user"


def test_collect_crawl_rejects_non_admin_user():
    dependency = route_dependency(collect.router, "crawl_collect_sources")
    with pytest.raises(HTTPException) as exc:
        dependency(user=user("user"))
    assert exc.value.status_code == 403


def test_collect_bulk_reparse_rejects_user():
    """A bulk retry can trigger network work and is restricted to administrators."""
    dependency = route_dependency(collect.router, "reparse_failed_collect_articles_route")

    with pytest.raises(HTTPException) as exc:
        dependency(user=user())

    assert exc.value.status_code == 403


def test_collect_bulk_reparse_allows_admin():
    dependency = route_dependency(collect.router, "reparse_failed_collect_articles_route")

    assert dependency(user=user("admin")).role == "admin"


def test_cve_search_allows_user():
    dependency = route_dependency(cve.router, "search_cve")

    assert dependency(user=user()).role == "user"


def test_cve_update_rejects_non_admin_user():
    dependency = route_dependency(cve.router, "update_cve_database")

    with pytest.raises(HTTPException) as exc:
        dependency(user=user("user"))

    assert exc.value.status_code == 403
