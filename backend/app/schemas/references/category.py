"""
Category schemas.

This module contains all request/response schemas related to
ticket categories (top level of the category -> subcategory ->
service classification hierarchy).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class CategoryBase(BaseModel):
    """Shared category fields."""

    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=100)
    sort_order: int = 0
    is_active: bool = True


# ==========================================================
# Create / Update
# ==========================================================


class CategoryCreate(CategoryBase):
    """Create a category."""


class CategoryUpdate(BaseModel):
    """Update a category. All fields optional."""

    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str | None = Field(None, min_length=3, max_length=100)
    color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class CategoryResponse(CategoryBase):
    """Full category record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class CategoryListResponse(BaseModel):
    """Paginated list of categories."""

    items: list[CategoryResponse]
    total: int
    page: int
    page_size: int