from contextlib import asynccontextmanager

from anyio import Lock, Path as AsyncPath
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from agno.agent import AgentFactory
from agno.os import AgentOS
from agno.os.middleware.jwt import JWTMiddleware
from agno.factory import RequestContext
from loguru import logger

from api.auth.claims import ADMIN_SCOPE
from api.auth.database import bootstrap_admin_user, close_auth_engine, create_auth_tables
from api.auth.router import router as auth_router
from api.config import get_settings
from api.core.logging import configure_logging_async
from api.mcp.server import bootstrap_mcp_token, mcp_runtime
from api.persistence.database import dispose_async_control_plane_engine
from api.routes import (
    agent_evals,
    audit,
    chat,
    collect,
    cve,
    knowledge,
    mcp as mcp_routes,
    os_control,
    settings,
    skills,
    trace,
)
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.security_run_runtime import DEFAULT_SECURITY_RUN_RUNTIME
from api.services.tracing_service import setup_agno_tracing
from api.utils.db import initialize_database

app_settings = get_settings()

AGENTOS_JWT_EXCLUDED_ROUTE_PATHS = [
    "/",
    "/index.html",
    "/assets/*",
    "/favicon.ico",
    "/vite.svg",
    "/report",
    "/report/*",
    "/api/auth/*",
    "/api/health",
    "/mcp",
    "/mcp/*",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
]


async def frontend_static_dir() -> str:
    dist_dir = AsyncPath("frontend/dist")
    if await dist_dir.exists():
        return "frontend/dist"
    source_dir = AsyncPath("source")
    if await source_dir.exists():
        return "source"
    return "frontend/dist"


class LazyFrontendStaticFiles:
    def __init__(self) -> None:
        self._app: StaticFiles | None = None
        self._lock = Lock()

    async def _get_app(self) -> StaticFiles:
        if self._app is not None:
            return self._app
        async with self._lock:
            if self._app is None:
                directory = await frontend_static_dir()
                self._app = StaticFiles(
                    directory=directory,
                    html=True,
                    check_dir=False,
                )
            return self._app

    async def __call__(self, scope, receive, send) -> None:
        static_app = await self._get_app()
        await static_app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await configure_logging_async(app_settings)
    logger.info("启动 {}", app_settings.app_name)
    app.state.settings = app_settings
    await initialize_database()
    setup_agno_tracing()
    await create_auth_tables()
    await bootstrap_admin_user(app_settings)

    await bootstrap_mcp_token(app_settings.mcp_token.get_secret_value())
    await mcp_runtime.startup()

    try:
        yield
    finally:
        await mcp_runtime.shutdown()
        await close_auth_engine()
        await dispose_async_control_plane_engine()
        logger.info("关闭 {}", app_settings.app_name)


app = FastAPI(
    title=app_settings.app_name,
    version=app_settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/api/health")
def health_check():
    return {"status": "ok", "environment": app_settings.environment}


@app.get("/report", include_in_schema=False)
def report_redirect():
    return RedirectResponse(url="/report/")


@app.api_route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS"], include_in_schema=False)
def mcp_redirect(request: Request):
    query = request.url.query
    target = "/mcp/" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=307)


async def _build_agentos_fallback_agent(_ctx: RequestContext):
    return await DEFAULT_SECURITY_RUN_RUNTIME.build_fallback_agent()


# Include routers
app.include_router(auth_router)
app.include_router(audit.router)
app.include_router(cve.router)
app.include_router(chat.router)
app.include_router(collect.router)
app.include_router(settings.router)
app.include_router(trace.router)
app.include_router(skills.router)
app.include_router(mcp_routes.router)
app.include_router(knowledge.router)
app.include_router(agent_evals.router)
app.include_router(os_control.router)

if app_settings.scheduler_enabled:
    agentos_db = get_async_agno_postgres_db()
    AgentOS(
        name="Trinity AI Security",
        agents=[
            AgentFactory(
                id="security-operations",
                name="安全防御助手",
                description="无工具模式下的安全防御运营助手。",
                db=agentos_db,
                factory=_build_agentos_fallback_agent,
            )
        ],
        db=agentos_db,
        base_app=app,
        on_route_conflict="preserve_base_app",
        scheduler=True,
        scheduler_poll_interval=app_settings.scheduler_poll_interval_seconds,
        scheduler_base_url=app_settings.scheduler_base_url,
        internal_service_token=app_settings.scheduler_internal_service_token.get_secret_value() or None,
        telemetry=False,
    ).get_app()
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", "") != "/"]

app.state.cors_allowed_origins = app_settings.cors_origins
app.add_middleware(
    JWTMiddleware,  # type: ignore[arg-type]
    verification_keys=[app_settings.auth_jwt_secret.get_secret_value()],
    algorithm="HS256",
    authorization=True,
    excluded_route_paths=AGENTOS_JWT_EXCLUDED_ROUTE_PATHS,
    admin_scope=ADMIN_SCOPE,
    user_isolation=True,
)

# Integrated FastMCP protocol endpoint. Same process, same port:
# http://<host>:8000/mcp?token=...
app.mount("/mcp", mcp_runtime.asgi_app(), name="mcp")

# Serve frontend static files. Production builds are written to frontend/dist.
app.mount("/", LazyFrontendStaticFiles(), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
