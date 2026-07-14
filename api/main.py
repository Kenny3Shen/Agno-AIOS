from contextlib import asynccontextmanager

from anyio import Lock, Path as AsyncPath
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from agno.os.middleware.jwt import JWTMiddleware
from loguru import logger
from fastmcp.utilities.lifespan import combine_lifespans

from api.auth.claims import ADMIN_SCOPE
from api.auth.database import bootstrap_admin_user, close_auth_engine, create_auth_tables
from api.auth.router import router as auth_router
from api.config import get_settings
from api.core.logging import configure_logging_async
from api.mcp.config import bootstrap_mcp_config
from api.mcp.server import bootstrap_mcp_token, configure_main_mcp, main_mcp
from api.persistence.database import dispose_async_control_plane_engine
from api.routes import (
    agent_evals,
    approvals,
    audit,
    chat,
    collect,
    cve,
    knowledge,
    memory,
    mcp as mcp_routes,
    notifications,
    overview,
    settings,
    skills,
    trace,
)
from api.services.security_run_runtime import recover_security_runs, shutdown_security_runtime
from api.services.tracing_service import setup_agno_tracing
from api.utils.db import initialize_database

app_settings = get_settings()

JWT_EXCLUDED_ROUTE_PATHS = [
    "/",
    "/index.html",
    "/assets/*",
    "/favicon.ico",
    "/favicon.svg",
    "/vite.svg",
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
                self._app = StaticFiles(
                    directory=await frontend_static_dir(),
                    html=True,
                    check_dir=False,
                )
            return self._app

    async def __call__(self, scope, receive, send) -> None:
        await (await self._get_app())(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await configure_logging_async(app_settings)
    logger.info("启动 {}", app_settings.app_name)
    app.state.settings = app_settings
    await initialize_database()
    setup_agno_tracing()
    await create_auth_tables()
    await bootstrap_admin_user(app_settings)

    await bootstrap_mcp_config()
    await bootstrap_mcp_token(app_settings.mcp_token.get_secret_value())
    await configure_main_mcp()
    try:
        recovered = await recover_security_runs()
        if recovered:
            logger.info("恢复 {} 个已解析的 HITL Run", recovered)
    except Exception:
        logger.exception("启动时恢复 HITL Run 失败")

    try:
        yield
    finally:
        await shutdown_security_runtime()
        await close_auth_engine()
        await dispose_async_control_plane_engine()
        logger.info("关闭 {}", app_settings.app_name)


mcp_app = main_mcp.http_app(path="/")

app = FastAPI(
    title=app_settings.app_name,
    version=app_settings.app_version,
    lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
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


# Include routers
app.include_router(auth_router)
app.include_router(audit.router)
app.include_router(cve.router)
app.include_router(chat.router)
app.include_router(collect.router)
app.include_router(settings.router)
app.include_router(trace.router)
app.include_router(overview.router)
app.include_router(skills.router)
app.include_router(mcp_routes.router)
app.include_router(knowledge.router)
app.include_router(agent_evals.router)
app.include_router(memory.router)
app.include_router(approvals.router)
app.include_router(notifications.router)

app.state.cors_allowed_origins = app_settings.cors_origins
app.add_middleware(
    JWTMiddleware,  # type: ignore[arg-type]
    verification_keys=[app_settings.auth_jwt_secret.get_secret_value()],
    algorithm="HS256",
    authorization=True,
    excluded_route_paths=JWT_EXCLUDED_ROUTE_PATHS,
    admin_scope=ADMIN_SCOPE,
    user_isolation=True,
)

# Integrated FastMCP protocol endpoint. Same process, same port:
# http://<host>:8000/mcp/ with Authorization: Bearer <token>
app.mount("/mcp", mcp_app, name="mcp")

# Serve the independently built frontend without AgentOS owning the root route.
app.mount("/", LazyFrontendStaticFiles(), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
