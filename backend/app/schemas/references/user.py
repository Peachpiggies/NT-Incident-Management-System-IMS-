"""
User schemas.

This module contains all request/response schemas related to
user accounts (admin/user management, as opposed to auth flows
which live in `app.schemas.auth`).

`User` has no `full_name` column (only `first_name`/`last_name`) and no
single `role_id` — roles are many-to-many via the `user_roles` junction
table, so a user has `role_ids`/`roles` (plural), never one `role`.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.validation import normalize_email, validate_password, validate_phone
from app.schemas.references.department import DepartmentSummary
from app.schemas.references.role import RoleSummary

# ==========================================================
# Base
# ==========================================================


class UserBase(BaseModel):
    """Shared user fields."""

    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str = Field(..., min_length=3, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    employee_code: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=30)
    department_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        return validate_phone(value)


# ==========================================================
# Create / Update
# ==========================================================


class UserCreate(UserBase):
    """Create a user (admin-managed, distinct from self-service register)."""

    password: str = Field(..., min_length=12, max_length=128)
    role_ids: list[UUID] = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_password(value)


class UserUpdate(BaseModel):
    """Update a user. All fields optional."""

    username: str | None = Field(
        None, min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$"
    )
    email: str | None = Field(None, min_length=3, max_length=255)
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    employee_code: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=30)
    department_id: UUID | None = None
    role_ids: list[UUID] | None = Field(None, min_length=1)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value is not None else None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        return validate_phone(value)


# ==========================================================
# Response
# ==========================================================


class UserResponse(BaseModel):
    """Full user record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    employee_code: str | None = None
    phone: str | None = None
    department: DepartmentSummary | None = None
    roles: list[RoleSummary] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str = Field(min_length=3, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    employee_code: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    department_id: UUID | None = None
    role_ids: list[UUID] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        return validate_phone(value)

    @field_validator("password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password(value)


class UserUpdateRequest(BaseModel):
    username: str | None = Field(
        default=None, min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$"
    )
    email: str | None = Field(default=None, min_length=3, max_length=255)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    employee_code: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    department_id: UUID | None = None
    role_ids: list[UUID] | None = Field(default=None, min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        return validate_phone(value)