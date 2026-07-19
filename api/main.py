import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from anyio import Lock
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from agno.os.middleware.jwt import JWTMiddleware
from loguru import logger
from fastmcp.utilities.lifespan import combine_lifespans
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.auth.claims import ADMIN_SCOPE
from api.auth.database import bootstrap_admin_user, close_auth_engine, create_auth_tables
from api.auth.router import router as auth_router
from api.config import get_settings
from api.core.logging import configure_logging_async
from api.mcp.config import bootstrap_mcp_config
from api.mcp.server import bootstrap_mcp_token, configure_main_mcp, main_mcp
from api.persistence.database import (
    dispose_async_control_plane_engine,
    get_async_control_plane_engine,
)
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
    workflows,
)
from api.services.security_run_runtime import recover_security_runs, shutdown_security_runtime
from api.services.postgres_store import ensure_app_tables_async
from api.services.workflow_cron import start_workflow_cron_scheduler, stop_workflow_cron_scheduler
from api.services.tracing_service import setup_agno_tracing

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
    "/api/ready",
    "/mcp",
    "/mcp/*",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
]

ReadinessProbe = Callable[[], Awaitable[bool | None]]


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
                    directory="frontend/dist",
                    html=True,
                    check_dir=False,
                )
            return self._app

    async def __call__(self, scope, receive, send) -> None:
        await (await self._get_app())(scope, receive, send)


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """Surface fire-and-forget task failures (e.g. Agno amake_memories)."""
    message = str(context.get("message") or "Unhandled asyncio exception")
    exception = context.get("exception")
    task = context.get("task") or context.get("future")
    task_name = getattr(task, "get_name", lambda: None)() if task is not None else None
    error_text = str(exception) if exception is not None else message
    task_label = f" [{task_name}]" if task_name else ""
    if exception is not None:
        logger.opt(exception=exception).error(
            "Asyncio background failure{}: {}", task_label, message
        )
    else:
        logger.error("Asyncio background failure{}: {}", task_label, message)
    # Best-effort durable alert; never re-raise into the event loop.
    try:
        from api.services.notification_service import notify_background_task_failure

        loop.create_task(
            notify_background_task_failure(
                task_name=str(task_name or ""),
                error=error_text,
            )
        )
    except Exception:
        logger.exception("Unable to schedule background failure notification")


async def check_control_plane_database() -> bool:
    """Verify that the control-plane database can serve a minimal query."""
    engine = get_async_control_plane_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def is_application_ready(application: FastAPI) -> bool:
    """Check startup completion and the injectable readiness dependency.

    ``application.state.readiness_probe`` permits focused tests and deployments
    with an extended probe without making liveness depend on external services.
    """
    if not getattr(application.state, "is_ready", False):
        return False

    readiness_probe: ReadinessProbe = getattr(
        application.state,
        "readiness_probe",
        check_control_plane_database,
    )
    try:
        return (await readiness_probe()) is not False
    except Exception:
        logger.warning("Readiness probe failed")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.is_ready = False
    await configure_logging_async(app_settings)
    try:
        asyncio.get_running_loop().set_exception_handler(_asyncio_exception_handler)
    except RuntimeError:
        logger.warning("Unable to install asyncio exception handler (no running loop)")
    logger.info("启动 {}", app_settings.app_name)
    await ensure_app_tables_async()
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
        await start_workflow_cron_scheduler()
    except Exception:
        logger.exception("启动 Workflow cron 调度器失败")

    app.state.is_ready = True
    try:
        yield
    finally:
        app.state.is_ready = False
        await stop_workflow_cron_scheduler()
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
app.state.is_ready = False
app.state.readiness_probe = check_control_plane_database

# Starlette middleware typing expects pure ASGI; FastAPI classes are compatible at runtime.
app.add_middleware(
    cast(Any, CORSMiddleware),
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Liveness check: deliberately does not depend on PostgreSQL or other services.
@app.get("/api/health")
def health_check():
    return {"status": "ok", "environment": app_settings.environment}


@app.get("/api/ready")
async def readiness_check(request: Request):
    """Return 503 until startup and the control-plane dependency are ready."""
    if not await is_application_ready(request.app):
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready", "environment": app_settings.environment}


# Include routers
app.include_router(auth_router)
app.include_router(audit.router)
app.include_router(cve.router)
app.include_router(chat.router)
app.include_router(collect.router)
app.include_router(settings.router)
app.include_router(trace.router)
app.include_router(workflows.router)
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
    cast(Any, JWTMiddleware),
    verification_keys=[app_settings.auth_jwt_secret.get_secret_value()],
    algorithm="HS256",
    authorization=True,
    excluded_route_paths=JWT_EXCLUDED_ROUTE_PATHS,
    admin_scope=ADMIN_SCOPE,
    user_isolation=True,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=app_settings.trusted_hosts,
)

# Integrated FastMCP protocol endpoint. Same process, same port:
# http://<host>:8000/mcp/ with Authorization: Bearer <token>
app.mount("/mcp", mcp_app, name="mcp")

# Serve the independently built frontend without AgentOS owning the root route.
app.mount("/", LazyFrontendStaticFiles(), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
