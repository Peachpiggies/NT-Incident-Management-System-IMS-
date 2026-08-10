"""
Department schemas.

This module contains all request/response schemas related to
departments.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class DepartmentBase(BaseModel):
    """Shared department fields."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


# ==========================================================
# Create / Update
# ==========================================================


class DepartmentCreate(DepartmentBase):
    """Create a department."""


class DepartmentUpdate(BaseModel):
    """Update a department. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


# ==========================================================
# Response
# ==========================================================


class DepartmentResponse(DepartmentBase):
    """Full department record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class DepartmentBrief(BaseModel):
    """Lightweight department reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class DepartmentListResponse(BaseModel):
    """Paginated list of departments."""

    items: list[DepartmentResponse]
    total: int
    page: int
    page_size: int