"""
Status schemas.

This module contains all request/response schemas related to
workflow statuses (e.g. for tickets or tasks).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ==========================================================
# Base
# ==========================================================


class StatusBase(BaseModel):
    """Shared status fields."""

    name: str = Field(..., min_length=1, max_length=50)
    order: int = Field(..., ge=0, description="Display/workflow order")
    is_default: bool = False
    is_closed: bool = Field(False, description="Whether this status counts as 'done'/closed")
    color: str | None = Field(None, max_length=20, description="Hex color, e.g. #22C55E")


# ==========================================================
# Create / Update
# ==========================================================


class StatusCreate(StatusBase):
    """Create a status."""


class StatusUpdate(BaseModel):
    """Update a status. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=50)
    order: int | None = Field(None, ge=0)
    is_default: bool | None = None
    is_closed: bool | None = None
    color: str | None = Field(None, max_length=20)


# ==========================================================
# Response
# ==========================================================


class StatusResponse(StatusBase):
    """Full status record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class StatusListResponse(BaseModel):
    """Paginated list of statuses."""

    items: list[StatusResponse]
    total: int
    page: int
    page_size: int