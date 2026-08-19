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
    """Shared status fields.

    Fixed to match `TicketStatus` (models.py): the model has no `order` or
    `is_default` column. `sort_order` is the display/workflow ordering
    field and `is_active` marks whether the status can still be assigned,
    mirroring `PriorityBase`'s shape for consistency across reference types.
    """

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, max_length=20, description="Hex color, e.g. #22C55E")
    is_closed: bool = Field(False, description="Whether this status counts as 'done'/closed")
    sort_order: int = Field(0, ge=0, description="Display/workflow order")
    is_active: bool = True


# ==========================================================
# Create / Update
# ==========================================================


class StatusCreate(StatusBase):
    """Create a status."""


class StatusUpdate(BaseModel):
    """Update a status. All fields optional."""

    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, max_length=20)
    is_closed: bool | None = None
    sort_order: int | None = Field(None, ge=0)
    is_active: bool | None = None


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