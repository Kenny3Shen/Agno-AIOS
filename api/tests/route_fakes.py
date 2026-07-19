from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute


def route_dependency(
    router: APIRouter,
    endpoint_name: str,
    index: int = 0,
) -> Callable[..., Any]:
    for route in router.routes:
        if not isinstance(route, APIRoute) or getattr(route.endpoint, "__name__", "") != endpoint_name:
            continue
        if index >= len(route.dependant.dependencies):
            raise AssertionError(f"route {endpoint_name} has no dependency at index {index}")
        dependency = route.dependant.dependencies[index].call
        if callable(dependency):
            return dependency
        raise AssertionError(f"route {endpoint_name} dependency {index} is not callable")
    raise AssertionError(f"missing route for {endpoint_name}")
