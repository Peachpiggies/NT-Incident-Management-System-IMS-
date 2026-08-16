"""
Common reusable schemas.

Shared Pydantic models used across the application.
"""

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """
    Lightweight user reference for nested display.

    `User` (the ORM model) stores `first_name`/`last_name`, not `full_name` —
    there is no `full_name` attribute to read via `from_attributes`. The
    validator below derives it so API consumers still get a single
    `full_name` field.
    """

    id: UUID
    full_name: str
    email: str

    @model_validator(mode="before")
    @classmethod
    def _derive_full_name(cls, data):
        if isinstance(data, dict):
            return data

        full_name = getattr(data, "full_name", None)
        if not full_name:
            first_name = (getattr(data, "first_name", "") or "").strip()
            last_name = (getattr(data, "last_name", "") or "").strip()
            if last_name == "-":
                last_name = ""
            full_name = " ".join(part for part in (first_name, last_name) if part)

        return {
            "id": data.id,
            "full_name": full_name,
            "email": data.email,
        }


# ==========================================================
# Shared Reference Summaries
# ==========================================================


class CategorySummary(ORMModel):
    """Lightweight category reference for nested display (e.g. on a ticket)."""

    id: UUID
    code: str
    name: str
    color: str | None = None
    icon: str | None = None


class DepartmentSummary(ORMModel):
    """Lightweight department reference for nested display."""

    id: UUID
    name: str


class PrioritySummary(ORMModel):
    """Lightweight priority reference for nested display."""

    id: UUID
    name: str
    sort_order: int
    color: str | None = None


class StatusSummary(ORMModel):
    """Lightweight status reference for nested display."""

    id: UUID
    name: str
    color: str | None = None
    is_closed: bool = False


# ==========================================================
# Health Check
# ==========================================================


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    timestamp: datetime