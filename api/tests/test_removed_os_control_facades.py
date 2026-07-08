from importlib.util import find_spec

import pytest
from fastapi.routing import APIRoute


REMOVED_OS_CONTROL_MODULES = (
    "api.routes.os_control",
    "api.routes.os_memory_control",
    "api.routes.os_approvals_control",
    "api.routes.os_sessions_control",
    "api.routes.os_metrics_control",
    "api.routes.os_evaluation_control",
    "api.routes.os_knowledge_control",
    "api.services.approval_control_service",
    "api.services.os_control_service",
    "api.services.os_control_identity",
    "api.services.os_control_payloads",
    "api.services.os_memory_control",
    "api.services.os_approvals_control",
    "api.services.os_sessions_control",
    "api.services.os_metrics_control",
    "api.services.os_evaluation_control",
    "api.services.os_knowledge_control",
    "api.services.scheduler_service",
)


@pytest.mark.parametrize("module_name", REMOVED_OS_CONTROL_MODULES)
def test_removed_os_control_facades_have_no_importable_modules(module_name: str) -> None:
    assert find_spec(module_name) is None


def test_removed_os_control_facades_have_no_registered_routes() -> None:
    from api.main import app

    route_paths = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    ]

    assert not [
        path
        for path in route_paths
        if path == "/api/os" or path.startswith("/api/os/")
    ]
