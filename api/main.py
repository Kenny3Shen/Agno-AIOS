from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from api.routes import cve, asset, chat, url2md, settings, traces

# from fastmcp.utilities.lifespan import combine_lifespans
from api.utils.db import get_db_pool, close_db_pool
import os
import sys
from loguru import logger
from dotenv import load_dotenv
import asyncio
import aiomysql
import httpx

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


async def create_asset_client() -> httpx.AsyncClient:
    client = httpx.AsyncClient(verify=False, timeout=30.0, follow_redirects=True)
    """从 .env 获取 ACL API token 或登录获取新 token"""
    login_url = "https://10.192.56.37:8088/api/user/login"
    login_data = {
        "username": os.getenv("ACL_USERNAME"),
        "password": os.getenv("ACL_PASSWORD"),
    }

    logger.info("正在登录 ACL API 获取新 token")
    login_resp = await client.post(login_url, json=login_data)
    login_resp.raise_for_status()
    login_result = login_resp.json()

    if login_result.get("code") != 200:
        logger.error("ACL 登录失败: {}", login_result.get("message"))
        raise Exception(f"登录失败: {login_result.get('message')}")

    token = login_result["data"]["token"]

    logger.info("成功登录 ACL API")
    client.headers.update({"Token": token, "Content-Type": "application/json"})
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # initialize resources
    pool: aiomysql.Pool = await get_db_pool()
    asset_client = await create_asset_client()
    app.state.db_pool = pool
    app.state.asset_client = asset_client
    # lock to protect token refresh for asset_client
    app.state.asset_lock = asyncio.Lock()

    try:
        yield
    finally:
        # cleanup resources
        await close_db_pool()
        await asset_client.aclose()


# mcp_app = mcp.http_app(path="/", transport="sse")

app = FastAPI(
    title="CVE Intelligence Platform API",
    # lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
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


# Include routers
app.include_router(cve.router)
app.include_router(asset.router)
app.include_router(chat.router)
app.include_router(url2md.router)
app.include_router(settings.router)
app.include_router(traces.router)

# Mount MCP server
# app.mount("/mcp", mcp_app, name="mcp")

# Serve frontend static files
app.mount("/", StaticFiles(directory="source", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
