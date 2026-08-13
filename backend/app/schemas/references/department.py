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

    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=2, max_length=160)
    description: str | None = None
    parent_department_id: UUID | None = None
    is_active: bool = True


# ==========================================================
# Create / Update
# ==========================================================


class DepartmentCreate(DepartmentBase):
    """Create a department."""


class DepartmentUpdate(BaseModel):
    """Update a department. All fields optional."""

    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = None
    parent_department_id: UUID | None = None
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class DepartmentResponse(DepartmentBase):
    """Full department record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class DepartmentListResponse(BaseModel):
    """Paginated list of departments."""

    items: list[DepartmentResponse]
    total: int
    page: int
    page_size: int