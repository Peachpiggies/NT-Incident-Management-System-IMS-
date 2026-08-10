"""
Subcategory schemas.

This module contains all request/response schemas related to
ticket subcategories (second level of the category -> subcategory
-> service classification hierarchy).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class SubcategoryBase(BaseModel):
    """Shared subcategory fields."""

    category_id: UUID
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    sort_order: int = 0
    is_active: bool = True


# ==========================================================
# Create / Update
# ==========================================================


class SubcategoryCreate(SubcategoryBase):
    """Create a subcategory."""


class SubcategoryUpdate(BaseModel):
    """Update a subcategory. All fields optional."""

    category_id: UUID | None = None
    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str | None = Field(None, min_length=3, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class SubcategoryResponse(SubcategoryBase):
    """Full subcategory record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class SubcategoryBrief(BaseModel):
    """Lightweight subcategory reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class SubcategoryListResponse(BaseModel):
    """Paginated list of subcategories."""

    items: list[SubcategoryResponse]
    total: int
    page: int
    page_size: int