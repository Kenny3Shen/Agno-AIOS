from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from api.routes import asset, chat, cve, knowledge, mcp as mcp_routes, settings, skills, traces, url2md
from api.mcp.server import bootstrap_mcp_token, mcp_runtime
from api.utils.db import get_db_pool, close_db_pool
import os
import sys
from loguru import logger
from dotenv import load_dotenv

load_dotenv(override=True)

# Configure logger
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
log_dir = os.getenv("LOG_DIR", "logs")
os.makedirs(log_dir, exist_ok=True)
logger.add(
    os.path.join(log_dir, "poc.log"),
    level=LOG_LEVEL,
    rotation="10 MB",
    retention="10 days",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # initialize resources
    pool = await get_db_pool()
    app.state.db_pool = pool
    bootstrap_mcp_token(os.getenv("MCP_TOKEN") or os.getenv("MCP_Token"))
    await mcp_runtime.startup()

    try:
        yield
    finally:
        # cleanup resources
        await mcp_runtime.shutdown()
        await close_db_pool()


app = FastAPI(
    title="Agno AIOS Security Platform API",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,  # type: ignore
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/report", include_in_schema=False)
async def report_redirect():
    return RedirectResponse(url="/report/")


@app.api_route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS"], include_in_schema=False)
async def mcp_redirect(request: Request):
    query = request.url.query
    target = "/mcp/" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=307)


# Include routers
app.include_router(cve.router)
app.include_router(asset.router)
app.include_router(chat.router)
app.include_router(url2md.router)
app.include_router(settings.router)
app.include_router(traces.router)
app.include_router(skills.router)
app.include_router(mcp_routes.router)
app.include_router(knowledge.router)

# Integrated FastMCP protocol endpoint. Same process, same port:
# http://<host>:8000/mcp?token=...
app.mount("/mcp", mcp_runtime.asgi_app(), name="mcp")

# Serve frontend static files
app.mount("/", StaticFiles(directory="source", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
