from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from api.database.cve_db import init_pool, close_pool
from api.routes import cve, asset, chat
import os
import sys
from loguru import logger

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
    await init_pool()
    yield
    await close_pool()


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

# Serve frontend static files
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
