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
    """Shared priority fields.

    Fixed to match `TicketPriority` (models.py): the model has no `level`
    field. `sort_order` is the ordering field (lower = shown first, not
    necessarily "more urgent" — that's implied by which SLA policy/target
    references this priority). `sla_minutes` is the legacy flat resolution
    target predating the SLA Engine's `sla_policies`/`sla_targets` tables;
    kept here since the column still exists and older code may still read
    it, but new SLA logic should prefer an explicit SLAPolicy match.
    """

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, max_length=20, description="Hex color, e.g. #FF0000")
    sla_minutes: int | None = Field(None, ge=1, description="Legacy flat resolution SLA; superseded by SLAPolicy/SLATarget")
    sort_order: int = Field(0, ge=0)
    is_active: bool = True


# ==========================================================
# Create / Update
# ==========================================================


class PriorityCreate(PriorityBase):
    """Create a priority level."""


class PriorityUpdate(BaseModel):
    """Update a priority level. All fields optional."""

    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, max_length=20)
    sla_minutes: int | None = Field(None, ge=1)
    sort_order: int | None = Field(None, ge=0)
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class PriorityResponse(PriorityBase):
    """Full priority record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class PriorityListResponse(BaseModel):
    """Paginated list of priority levels."""

    items: list[PriorityResponse]
    total: int
    page: int
    page_size: int