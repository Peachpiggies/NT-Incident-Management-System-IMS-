"""
Category schemas.

This module contains all request/response schemas related to
categories (e.g. for tickets or tasks).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class CategoryBase(BaseModel):
    """Shared category fields."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    department_id: UUID | None = Field(
        None, description="Optional department this category belongs to"
    )


# ==========================================================
# Create / Update
# ==========================================================


class CategoryCreate(CategoryBase):
    """Create a category."""


class CategoryUpdate(BaseModel):
    """Update a category. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    department_id: UUID | None = None


# ==========================================================
# Response
# ==========================================================


class CategoryResponse(CategoryBase):
    """Full category record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class CategoryBrief(BaseModel):
    """Lightweight category reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class CategoryListResponse(BaseModel):
    """Paginated list of categories."""

    items: list[CategoryResponse]
    total: int
    page: int
    page_size: int