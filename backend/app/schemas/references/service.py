"""
Service schemas.

This module contains all request/response schemas related to
ticket services (third level of the category -> subcategory ->
service classification hierarchy).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class ServiceBase(BaseModel):
    """Shared service fields."""

    subcategory_id: UUID
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=2000)
    sort_order: int = 0
    is_active: bool = True


# ==========================================================
# Create / Update
# ==========================================================


class ServiceCreate(ServiceBase):
    """Create a service."""


class ServiceUpdate(BaseModel):
    """Update a service. All fields optional."""

    subcategory_id: UUID | None = None
    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str | None = Field(None, min_length=3, max_length=100)
    description: str | None = Field(None, max_length=2000)
    sort_order: int | None = None
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class ServiceResponse(ServiceBase):
    """Full service record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class ServiceBrief(BaseModel):
    """Lightweight service reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class ServiceListResponse(BaseModel):
    """Paginated list of services."""

    items: list[ServiceResponse]
    total: int
    page: int
    page_size: int