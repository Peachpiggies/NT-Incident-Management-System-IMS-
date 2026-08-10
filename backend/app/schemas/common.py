"""
Common reusable schemas.

Shared Pydantic models used across the application.
"""

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ==========================================================
# Base Models
# ==========================================================


class ORMModel(BaseModel):
    """Base schema with SQLAlchemy compatibility."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class TimestampMixin(ORMModel):
    """Timestamp fields shared by many response schemas."""

    created_at: datetime
    updated_at: datetime


class AuditMixin(TimestampMixin):
    """Audit fields."""

    created_by: UUID | None = None
    updated_by: UUID | None = None


# ==========================================================
# API Response
# ==========================================================


class MessageResponse(BaseModel):
    """Simple success message."""

    success: bool = True
    message: str


class DataResponse(BaseModel, Generic[T]):
    """Standard API response."""

    success: bool = True
    message: str = "Success"
    data: T


# ==========================================================
# Pagination
# ==========================================================


class Pagination(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)
    total: int
    pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    pagination: Pagination


# ==========================================================
# Shared Lookup Schema
# ==========================================================


class UUIDNameSchema(ORMModel):
    """Simple lookup schema."""

    id: UUID
    name: str


# ==========================================================
# Shared User Summary
# ==========================================================


class UserSummary(ORMModel):
    id: UUID
    full_name: str
    email: str


# ==========================================================
# Health Check
# ==========================================================


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    timestamp: datetime