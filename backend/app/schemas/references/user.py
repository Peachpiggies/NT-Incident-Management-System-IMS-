"""
User schemas.

This module contains all request/response schemas related to
user accounts (admin/user management, as opposed to auth flows
which live in `app.schemas.auth`).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.references.department import DepartmentBrief
from app.schemas.references.role import RoleBrief


# ==========================================================
# Base
# ==========================================================


class UserBase(BaseModel):
    """Shared user fields."""

    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    department_id: UUID | None = None
    role_id: UUID | None = None


# ==========================================================
# Create / Update
# ==========================================================


class UserCreate(UserBase):
    """Create a user (admin-managed, distinct from self-service register)."""

    password: str = Field(..., min_length=8, max_length=128)
    is_active: bool = True


class UserUpdate(BaseModel):
    """Update a user. All fields optional."""

    full_name: str | None = Field(None, min_length=2, max_length=255)
    email: EmailStr | None = None
    department_id: UUID | None = None
    role_id: UUID | None = None
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class UserResponse(BaseModel):
    """Full user record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    role: RoleBrief | None = None
    department: DepartmentBrief | None = None
    is_active: bool
    created_at: datetime


class UserBrief(BaseModel):
    """Lightweight user reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int