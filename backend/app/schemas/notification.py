"""
Notification schemas.

This module contains all request/response schemas related to
in-app notifications.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Enums
# ==========================================================


class NotificationType(str, Enum):
    """Category of a notification, used for icon/color on the client."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# ==========================================================
# Base
# ==========================================================


class NotificationBase(BaseModel):
    """Shared notification fields."""

    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=2000)
    type: NotificationType = NotificationType.INFO


# ==========================================================
# Create / Update
# ==========================================================


class NotificationCreate(NotificationBase):
    """Create a notification for a specific user."""

    user_id: UUID
    link: str | None = None


class NotificationBroadcastCreate(NotificationBase):
    """Create the same notification for multiple users (or a department)."""

    user_ids: list[UUID] | None = None
    department_id: UUID | None = None
    link: str | None = None


class NotificationUpdate(BaseModel):
    """Update a notification's read state."""

    is_read: bool


# ==========================================================
# Response
# ==========================================================


class NotificationResponse(NotificationBase):
    """Single notification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    link: str | None = None
    is_read: bool
    created_at: datetime
    read_at: datetime | None = None


class NotificationListResponse(BaseModel):
    """Paginated list of notifications."""

    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    """Unread notification count, e.g. for a badge indicator."""

    unread_count: int


# ==========================================================
# Bulk actions
# ==========================================================


class MarkAllReadResponse(BaseModel):
    """Result of marking all notifications as read."""

    updated_count: int