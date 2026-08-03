from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/healthz", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def healthz() -> HealthResponse:
    """Liveness endpoint that does not depend on external services."""
    return HealthResponse(status="ok", database="not-checked")


@router.get("/readyz", response_model=HealthResponse)
async def readyz(db: Annotated[AsyncSession, Depends(get_db)]) -> HealthResponse:
    """Readiness endpoint; validates database connectivity."""
    await db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="connected")
