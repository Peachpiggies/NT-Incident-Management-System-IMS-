"""
Role schemas.

This module contains all request/response schemas related to
user roles.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class RoleBase(BaseModel):
    """Shared role fields."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


# ==========================================================
# Create / Update
# ==========================================================


class RoleCreate(RoleBase):
    """Create a role."""


class RoleUpdate(BaseModel):
    """Update a role. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


# ==========================================================
# Response
# ==========================================================


class RoleResponse(RoleBase):
    """Full role record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class RoleBrief(BaseModel):
    """Lightweight role reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class RoleListResponse(BaseModel):
    """Paginated list of roles."""

    items: list[RoleResponse]
    total: int
    page: int
    page_size: int