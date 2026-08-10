"""
Authentication schemas.

This module contains all request/response schemas related to
authentication and authorization.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ==========================================================
# Base
# ==========================================================


class Token(BaseModel):
    """JWT access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: UUID
    exp: int


# ==========================================================
# Login
# ==========================================================


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginResponse(Token):
    """Login response."""

    user_id: UUID
    full_name: str
    role: str


# ==========================================================
# Register
# ==========================================================


class RegisterRequest(BaseModel):
    """User registration."""

    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    department_id: UUID | None = None


# ==========================================================
# Refresh Token
# ==========================================================


class RefreshTokenRequest(BaseModel):
    """Refresh access token."""

    refresh_token: str


# ==========================================================
# Password
# ==========================================================


class ChangePasswordRequest(BaseModel):
    """Change current password."""

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


# ==========================================================
# Current User
# ==========================================================


class CurrentUser(BaseModel):
    """Authenticated user information."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    role: str
    department: str | None = None
    is_active: bool


# ==========================================================
# Generic Message
# ==========================================================


class MessageResponse(BaseModel):
    """Generic success response."""

    message: str


'''=========================================================
Logout
========================================================='''


class LogoutRequest(BaseModel):
    refresh_token: str

