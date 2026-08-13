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

    code: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9._-]+$")
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None


# ==========================================================
# Create / Update
# ==========================================================


class RoleRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)


class RoleCreate(RoleBase):
    """Create a role."""


class RoleUpdate(BaseModel):
    """Update a role. All fields optional."""

    code: str | None = Field(None, min_length=2, max_length=100, pattern=r"^[a-z0-9._-]+$")
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None


# ==========================================================
# Response
# ==========================================================


class RoleResponse(RoleBase):
    """Full role record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_system: bool
    created_at: datetime
    updated_at: datetime


class RoleBrief(BaseModel):
    """Lightweight role reference for nesting inside other schemas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class RoleSummary(BaseModel):
    """Lightweight role reference including its code, for user-facing role lists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


class RoleListResponse(BaseModel):
    """Paginated list of roles."""

    items: list[RoleResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# User <-> Role assignment
# ==========================================================


class UserRoleResponse(BaseModel):
    """
    A single role assignment (row in the `user_roles` junction table),
    with the assigned role expanded inline.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role: RoleResponse
    created_at: datetime