from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Literal, cast

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.exceptions import PromptError, ResourceError, ToolError
from fastmcp.server import create_proxy
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from loguru import logger

from api.mcp.config import (
    component_overrides,
    delegation_subject,
    enabled_mcp_servers,
    ensure_bootstrap_token,
    find_token,
    set_component_override,
)
from api.auth.claims import actor_id, actor_role, actor_scopes
from api.auth.database import get_active_user_by_id
from api.mcp.tools.basic import basic_mcp
from api.mcp.tools.hitl import hitl_mcp
from api.services.capability_policy_service import effective_mcp_server_ids_for_actor

ComponentType = Literal["tool", "resource", "template", "prompt"]


class DatabaseTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        delegated_user_id = delegation_subject(token)
        if delegated_user_id:
            user = await get_active_user_by_id(delegated_user_id)
            if user is not None:
                return _access_token_for_user(token, user, kind="delegation")
            return None

        record = await find_token(token)
        if record is None:
            return None
        expires_at = int(record.get("expires_at") or 0)
        if expires_at and int(time.time()) >= expires_at:
            return None
        token_kind = str(record.get("token_kind") or "service")
        owner_user_id = str(record.get("owner_user_id") or "").strip()
        if token_kind == "user" and owner_user_id:
            user = await get_active_user_by_id(owner_user_id)
            if user is None:
                return None
            return _access_token_for_user(token, user, kind="user")
        # Service credentials retain a distinct, non-human identity.  The
        # capability middleware intentionally gives them no personal surface.
        return AccessToken(
            token=token,
            client_id="mcp-service",
            scopes=[],
            claims={"kind": "service"},
        )


def _access_token_for_user(token: str, user: Any, *, kind: str) -> AccessToken:
    user_id = str(getattr(user, "id", "") or "")
    role = actor_role(user)
    return AccessToken(
        token=token,
        client_id=f"user:{user_id}",
        subject=user_id,
        scopes=actor_scopes(user),
        claims={
            "sub": user_id,
            "role": role,
            "is_superuser": bool(getattr(user, "is_superuser", False)),
            "kind": kind,
        },
    )


def _access_actor() -> Any | None:
    token = get_access_token()
    if token is None:
        # Direct in-process Client(main_mcp) calls are server-internal. REST
        # endpoints still explicitly invoke the same policy before these calls.
        return None
    claims = token.claims or {}
    user_id = str(claims.get("sub") or token.subject or "").strip()
    if not user_id or claims.get("kind") not in {"user", "delegation"}:
        # Service credentials do not map to the user role.  The middleware
        # recognizes the empty subject and grants no user-owned capabilities.
        return SimpleNamespace(id="", role="user", is_superuser=False)
    return SimpleNamespace(
        id=user_id,
        role=str(claims.get("role") or "user"),
        is_superuser=bool(claims.get("is_superuser", False)),
    )


class CapabilityPolicyMiddleware(Middleware):
    """Hide and reject MCP components outside the authenticated user's set."""

    async def _allowed_server_ids(self) -> set[int] | None:
        actor = _access_actor()
        if actor is None:
            return None
        if not actor_id(actor):
            return set()
        return await effective_mcp_server_ids_for_actor(actor)

    async def _component_allowed(self, component_name: object) -> bool:
        allowed_server_ids = await self._allowed_server_ids()
        if allowed_server_ids is None:
            return True
        server_id, _namespace = _component_namespace(str(component_name or ""))
        return server_id is not None and server_id in allowed_server_ids

    async def _filter_components(self, components: Any) -> Any:
        allowed_server_ids = await self._allowed_server_ids()
        if allowed_server_ids is None:
            return components
        filtered = []
        for component in components:
            name = (
                getattr(component, "name", None)
                or getattr(component, "uri", None)
                or getattr(component, "uri_template", None)
            )
            server_id, _namespace = _component_namespace(str(name or ""))
            if server_id is not None and server_id in allowed_server_ids:
                filtered.append(component)
        return filtered

    async def on_list_tools(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        return await self._filter_components(await call_next(context))

    async def on_list_resources(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        return await self._filter_components(await call_next(context))

    async def on_list_resource_templates(
        self, context: MiddlewareContext[Any], call_next: Any
    ) -> Any:
        return await self._filter_components(await call_next(context))

    async def on_list_prompts(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        return await self._filter_components(await call_next(context))

    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        if not await self._component_allowed(getattr(context.message, "name", "")):
            raise ToolError("Tool not found")
        return await call_next(context)

    async def on_read_resource(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        if not await self._component_allowed(getattr(context.message, "uri", "")):
            raise ResourceError("Resource not found")
        return await call_next(context)

    async def on_get_prompt(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        if not await self._component_allowed(getattr(context.message, "name", "")):
            raise PromptError("Prompt not found")
        return await call_next(context)


def create_main_mcp() -> FastMCP:
    mcp = FastMCP("Trinity AI Security MCP", auth=DatabaseTokenVerifier())
    mcp.add_middleware(ErrorHandlingMiddleware(transform_errors=True))
    mcp.add_middleware(CapabilityPolicyMiddleware())
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
    matches = [
        row
        for row in _server_rows
        if name.startswith(f"{row['namespace']}_")
        or f"://{row['namespace']}/" in name
    ]
    if not matches:
        return None, None
    row = max(matches, key=lambda item: len(item["namespace"]))
    return int(row["id"]), str(row["namespace"])


def _serialize_component(component: Any, component_type: ComponentType) -> dict[str, Any]:
    name = str(
        getattr(component, "name", None)
        or getattr(component, "uri", None)
        or getattr(component, "uri_template", "")
    )
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


async def list_components(
    component_type: ComponentType | None = None, *, actor: Any | None = None
) -> list[dict[str, Any]]:
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
    if actor is None:
        return result
    allowed_server_ids = await effective_mcp_server_ids_for_actor(actor)
    return [
        item
        for item in result
        if item.get("server_id") is not None
        and int(item["server_id"]) in allowed_server_ids
    ]


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


async def call_tool(
    name: str, arguments: dict[str, Any], *, actor: Any | None = None
) -> dict[str, Any]:
    await configure_main_mcp()
    if actor is not None:
        server_id, _namespace = _component_namespace(name)
        if server_id is None or server_id not in await effective_mcp_server_ids_for_actor(actor):
            raise PermissionError(name)
    async with Client(main_mcp, timeout=30) as client:
        result = await client.call_tool(name, arguments, raise_on_error=False)
    return result.model_dump(mode="json")


async def bootstrap_mcp_token(token: str | None) -> None:
    await ensure_bootstrap_token(token)
