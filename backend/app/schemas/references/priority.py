"""
Priority schemas.

This module contains all request/response schemas related to
priority levels (e.g. for tickets or tasks).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class PriorityBase(BaseModel):
    """Shared priority fields."""

    name: str = Field(..., min_length=1, max_length=50)
    level: int = Field(..., ge=1, description="Lower number = higher priority")
    color: str | None = Field(None, max_length=20, description="Hex color, e.g. #FF0000")


# ==========================================================
# Create / Update
# ==========================================================


class PriorityCreate(PriorityBase):
    """Create a priority level."""


class PriorityUpdate(BaseModel):
    """Update a priority level. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=50)
    level: int | None = Field(None, ge=1)
    color: str | None = Field(None, max_length=20)


# ==========================================================
# Response
# ==========================================================


class PriorityResponse(PriorityBase):
    """Full priority record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class PriorityBrief(BaseModel):
    """Lightweight priority reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    level: int
    color: str | None = None


class PriorityListResponse(BaseModel):
    """Paginated list of priority levels."""

    items: list[PriorityResponse]
    total: int
    page: int
    page_size: int