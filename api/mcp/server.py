from __future__ import annotations

from typing import Any, Literal, cast

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.server import create_proxy
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from loguru import logger

from api.mcp.config import (
    component_overrides,
    enabled_mcp_servers,
    ensure_bootstrap_token,
    is_valid_token,
    set_component_override,
)
from api.mcp.tools.basic import basic_mcp
from api.mcp.tools.hitl import hitl_mcp
from api.mcp.tools.playbook import playbook_mcp

ComponentType = Literal["tool", "resource", "template", "prompt"]


class DatabaseTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if not await is_valid_token(token):
            return None
        return AccessToken(token=token, client_id="mcp-token", scopes=[])


def create_main_mcp() -> FastMCP:
    mcp = FastMCP("Trinity AI Security MCP", auth=DatabaseTokenVerifier())
    mcp.add_middleware(ErrorHandlingMiddleware(transform_errors=True))
    mcp.add_middleware(RateLimitingMiddleware(max_requests_per_second=50.0, burst_capacity=100))
    mcp.add_middleware(TimingMiddleware())
    mcp.add_middleware(ResponseLimitingMiddleware(max_size=500_000))
    return mcp


main_mcp = create_main_mcp()
_configured = False
_server_rows: list[dict[str, Any]] = []


async def configure_main_mcp() -> None:
    global _configured, _server_rows
    if _configured:
        return
    rows = await enabled_mcp_servers()
    for row in rows:
        try:
            if row["server_type"] == "builtin":
                child = {
                    "basic": basic_mcp,
                    "hitl": hitl_mcp,
                    "playbook": playbook_mcp,
                }.get(row["name"])
                if child is None:
                    continue
            else:
                child = create_proxy(row["config"], name=row["name"])
            main_mcp.mount(child, namespace=row["namespace"])
        except Exception as exc:
            logger.error("加载 MCP Server {} 失败: {}", row["name"], exc)
    _server_rows = rows
    for override in await component_overrides():
        component = override["component_type"]
        name = override["component_name"]
        if override["enabled"]:
            main_mcp.enable(names={name}, components={component})
        else:
            main_mcp.disable(names={name}, components={component})
    _configured = True


def _component_namespace(name: str) -> tuple[int | None, str | None]:
    matches = [row for row in _server_rows if name.startswith(f"{row['namespace']}_")]
    if not matches:
        return None, None
    row = max(matches, key=lambda item: len(item["namespace"]))
    return int(row["id"]), str(row["namespace"])


def _serialize_component(component: Any, component_type: ComponentType) -> dict[str, Any]:
    name = str(getattr(component, "name", None) or getattr(component, "uri", ""))
    server_id, namespace = _component_namespace(name)
    annotations = getattr(component, "annotations", None)
    icons = getattr(component, "icons", None)
    return {
        "key": f"{component_type}:{name}",
        "type": component_type,
        "name": name,
        "title": getattr(component, "title", None),
        "description": getattr(component, "description", None),
        "namespace": namespace,
        "server_id": server_id,
        "tags": sorted(getattr(component, "tags", None) or []),
        "icons": [icon.model_dump(mode="json") for icon in icons] if icons else [],
        "annotations": annotations.model_dump(mode="json") if hasattr(annotations, "model_dump") else annotations,
        "input_schema": getattr(component, "parameters", None),
        "output_schema": getattr(component, "output_schema", None),
        "meta": getattr(component, "meta", None) or {},
        "enabled": True,
    }


async def list_components(component_type: ComponentType | None = None) -> list[dict[str, Any]]:
    await configure_main_mcp()
    loaders = {
        "tool": main_mcp.list_tools,
        "resource": main_mcp.list_resources,
        "template": main_mcp.list_resource_templates,
        "prompt": main_mcp.list_prompts,
    }
    types = [component_type] if component_type else list(loaders)
    result: list[dict[str, Any]] = []
    for kind in types:
        for component in await loaders[kind]():
            result.append(_serialize_component(component, cast(ComponentType, kind)))
    active_keys = {(item["type"], item["name"]) for item in result}
    rows_by_id = {int(row["id"]): row for row in _server_rows}
    for override in await component_overrides():
        key = (override["component_type"], override["component_name"])
        if override["enabled"] or key in active_keys:
            continue
        if component_type is not None and override["component_type"] != component_type:
            continue
        row = rows_by_id.get(int(override["server_id"]))
        result.append(
            {
                "key": f"{override['component_type']}:{override['component_name']}",
                "type": override["component_type"],
                "name": override["component_name"],
                "title": None,
                "description": "Disabled component",
                "namespace": row["namespace"] if row else None,
                "server_id": override["server_id"],
                "tags": [],
                "icons": [],
                "annotations": None,
                "input_schema": None,
                "output_schema": None,
                "meta": {},
                "enabled": False,
            }
        )
    return result


async def set_component_enabled(
    *, server_id: int, component_type: ComponentType, name: str, enabled: bool
) -> None:
    await configure_main_mcp()
    if enabled:
        main_mcp.enable(names={name}, components={component_type})
    else:
        main_mcp.disable(names={name}, components={component_type})
    await set_component_override(server_id, component_type, name, enabled)


async def test_server_config(config: dict[str, Any]) -> list[str]:
    async with Client(config, timeout=20) as client:
        return [tool.name for tool in await client.list_tools()]


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    await configure_main_mcp()
    async with Client(main_mcp, timeout=30) as client:
        result = await client.call_tool(name, arguments, raise_on_error=False)
    return result.model_dump(mode="json")


async def bootstrap_mcp_token(token: str | None) -> None:
    await ensure_bootstrap_token(token)
