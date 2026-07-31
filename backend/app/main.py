from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.v1.health import router as health_router
from app.core.config import settings
from app.db.session import engine  # ensures engine created

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Incident Management Platform (IMP)",
    version="0.1.0",
    openapi_url=f"/api/v1/openapi.json",
    docs_url="/docs",
)

# CORS (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in settings.BACKEND_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting application...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")