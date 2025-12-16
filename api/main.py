from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from api.routes import cve, asset, chat, url2md
import os
import sys
from loguru import logger
from dotenv import load_dotenv
import aiomysql

load_dotenv()

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


DB_CONFIG = {
    "host": os.getenv("MYSQL_TEST_HOST"),
    "port": int(os.getenv("MYSQL_TEST_PORT", 3306)),
    "user": os.getenv("MYSQL_TEST_USER"),
    "password": os.getenv("MYSQL_TEST_PASSWORD"),
    "db": os.getenv("MYSQL_TEST_DATABASE"),
    "charset": "utf8mb4",
    "autocommit": True,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # initialize resources
    pool: aiomysql.Pool = await aiomysql.create_pool(**DB_CONFIG)
    app.state.db_pool = pool

    try:
        yield
    finally:
        # cleanup resources
        pool.close()
        await pool.wait_closed()


app = FastAPI(title="CVE Intelligence Platform API", lifespan=lifespan)

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


# Include routers
app.include_router(cve.router)
app.include_router(asset.router)
app.include_router(chat.router)
app.include_router(url2md.router)

# Serve frontend static files
app.mount("/", StaticFiles(directory="source", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
