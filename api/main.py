import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from api.auth.database import bootstrap_admin_user, close_auth_engine, create_auth_tables
from api.auth.router import router as auth_router
from api.config import get_settings
from api.core.logging import configure_logging
from api.mcp.server import bootstrap_mcp_token, mcp_runtime
from api.routes import (
    audit,
    assets,
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
from api.utils.db import close_db_pool, get_db_pool

app_settings = get_settings()
configure_logging(app_settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动 {}", app_settings.app_name)
    app.state.settings = app_settings
    pool = await get_db_pool()
    app.state.db_pool = pool
    await create_auth_tables()
    await bootstrap_admin_user(app_settings)

    headers = {"Content-Type": "application/json"}
    acl_token = app_settings.acl_token.get_secret_value()
    if acl_token:
        headers["Token"] = acl_token
    app.state.asset_client = httpx.AsyncClient(
        headers=headers,
        timeout=30.0,
        verify=False,
    )
    app.state.asset_lock = asyncio.Lock()

    bootstrap_mcp_token(app_settings.mcp_token.get_secret_value())
    await mcp_runtime.startup()

    try:
        yield
    finally:
        await mcp_runtime.shutdown()
        await app.state.asset_client.aclose()
        await close_auth_engine()
        await close_db_pool()
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
async def health_check():
    return {"status": "ok", "environment": app_settings.environment}


@app.get("/report", include_in_schema=False)
async def report_redirect():
    return RedirectResponse(url="/report/")


@app.api_route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS"], include_in_schema=False)
async def mcp_redirect(request: Request):
    query = request.url.query
    target = "/mcp/" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=307)


# Include routers
app.include_router(auth_router)
app.include_router(audit.router)
app.include_router(cve.router)
app.include_router(assets.router)
app.include_router(chat.router)
app.include_router(collect.router)
app.include_router(settings.router)
app.include_router(trace.router)
app.include_router(skills.router)
app.include_router(mcp_routes.router)
app.include_router(knowledge.router)
app.include_router(os_control.router)

# Integrated FastMCP protocol endpoint. Same process, same port:
# http://<host>:8000/mcp?token=...
app.mount("/mcp", mcp_runtime.asgi_app(), name="mcp")

# Serve frontend static files
app.mount("/", StaticFiles(directory="source", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
