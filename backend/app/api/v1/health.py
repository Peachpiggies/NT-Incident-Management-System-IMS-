from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class HealthResponse(BaseModel):

    status: str

@router.get("/healthz", response_model=HealthResponse, tags=["Health"])

async def healthz():

    """
    Simple health check for readiness/liveness.
    """
    
    return {"status": "ok"}