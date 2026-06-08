from urllib.parse import parse_qs

from fastmcp import FastMCP
from loguru import logger
from starlette.responses import JSONResponse

from api.mcp.config import enabled_service_ids, ensure_bootstrap_token, is_valid_token
from api.mcp.tools.agent import agent_mcp
from api.mcp.tools.basic import basic_mcp
from api.mcp.tools.playbook import playbook_mcp


def _extract_header(scope: dict, name: str) -> str:
    target = name.lower()
    for key, value in scope.get("headers", []):
        if key.decode().lower() == target:
            return value.decode()
    return ""


def _extract_token(scope: dict) -> str:
    auth_header = _extract_header(scope, "authorization")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    qs = parse_qs((scope.get("query_string", b"") or b"").decode())
    return (qs.get("token") or [""])[0].strip()


class AuthenticatedMcpApp:
    def __init__(self, runtime: "IntegratedMcpRuntime"):
        self.runtime = runtime

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"} and not is_valid_token(_extract_token(scope)):
            response = JSONResponse(
                {"code": 401, "msg": "Unauthorized: invalid_token"},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        await self.runtime.app(scope, receive, send)


def build_main_mcp() -> FastMCP:
    enabled = enabled_service_ids()
    main_mcp = FastMCP("Agno AIOS MCP")
    if "playbook" in enabled:
        main_mcp.mount(playbook_mcp, namespace="playbook")
    if "agent" in enabled:
        main_mcp.mount(agent_mcp, namespace="agent")
    if "basic" in enabled:
        main_mcp.mount(basic_mcp, namespace="basic")
    return main_mcp


class IntegratedMcpRuntime:
    def __init__(self):
        self.mcp = build_main_mcp()
        self.app = self.mcp.http_app(path="/")
        self._lifespan_cm = None
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        self._lifespan_cm = self.app.lifespan(self.app)
        await self._lifespan_cm.__aenter__()
        self._started = True

    async def shutdown(self) -> None:
        if not self._started or self._lifespan_cm is None:
            return
        await self._lifespan_cm.__aexit__(None, None, None)
        self._lifespan_cm = None
        self._started = False

    async def refresh(self) -> None:
        logger.info("刷新内置 FastMCP 工具运行时")
        old_lifespan_cm = self._lifespan_cm
        old_started = self._started

        new_mcp = build_main_mcp()
        new_app = new_mcp.http_app(path="/")
        new_lifespan_cm = None
        if old_started:
            new_lifespan_cm = new_app.lifespan(new_app)
            await new_lifespan_cm.__aenter__()

        self.mcp = new_mcp
        self.app = new_app
        self._lifespan_cm = new_lifespan_cm
        self._started = old_started

        if old_started and old_lifespan_cm is not None:
            try:
                await old_lifespan_cm.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(f"旧 FastMCP 运行时关闭失败，已保留新实例继续服务: {exc}")

    def asgi_app(self) -> AuthenticatedMcpApp:
        return AuthenticatedMcpApp(self)


mcp_runtime = IntegratedMcpRuntime()


async def refresh_mcp_app() -> None:
    await mcp_runtime.refresh()


def bootstrap_mcp_token(token: str | None) -> None:
    ensure_bootstrap_token(token)
