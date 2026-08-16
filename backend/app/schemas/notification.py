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


# ==========================================================
# Delivery channels
# ==========================================================


class NotificationChannel(str, Enum):
    """Where a notification is (or was) delivered."""

    EMAIL = "email"
    IN_APP = "in_app"
    WEBSOCKET = "websocket"
    SMS = "sms"


class NotificationDeliveryStatus(str, Enum):
    """Outcome of a single delivery attempt on a channel."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


# ==========================================================
# Notification Rules
# ==========================================================
# Config-level rules: "when <event_type> happens, notify <recipients> on
# <channels>". Distinct from `NotificationCreate`/`NotificationBroadcastCreate`
# above, which create the actual per-user notification records.


class NotificationRuleBase(BaseModel):
    """Shared notification-rule fields."""

    name: str = Field(..., min_length=1, max_length=150)
    event_type: str = Field(
        ..., min_length=1, max_length=100, description="e.g. 'ticket.assigned', 'sla.breached'"
    )
    channels: list[NotificationChannel] = Field(..., min_length=1)
    recipient_role_ids: list[UUID] = Field(default_factory=list)
    recipient_user_ids: list[UUID] = Field(default_factory=list)
    template_id: UUID | None = None
    is_active: bool = True


class NotificationRuleCreate(NotificationRuleBase):
    pass


class NotificationRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    event_type: str | None = Field(None, min_length=1, max_length=100)
    channels: list[NotificationChannel] | None = Field(None, min_length=1)
    recipient_role_ids: list[UUID] | None = None
    recipient_user_ids: list[UUID] | None = None
    template_id: UUID | None = None
    is_active: bool | None = None


class NotificationRuleResponse(NotificationRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class NotificationRuleListResponse(BaseModel):
    items: list[NotificationRuleResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Escalation Notification
# ==========================================================
# Sent by the SLA Engine's escalation triggers (see app.schemas.sla) rather
# than created directly by a user, so this only has Create (system-issued)
# and Response shapes -- no Update.


class EscalationNotificationCreate(BaseModel):
    """Fired when an SLA escalation trigger fires for a ticket."""

    ticket_id: UUID
    escalation_trigger_id: UUID
    channel: NotificationChannel
    recipient_user_ids: list[UUID] = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=2000)


class EscalationNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID
    escalation_trigger_id: UUID
    channel: NotificationChannel
    recipient_user_ids: list[UUID]
    message: str
    status: NotificationDeliveryStatus
    sent_at: datetime | None = None
    created_at: datetime


# ==========================================================
# Notification History
# ==========================================================
# Delivery log/audit trail: one row per attempted delivery on a channel,
# covering both regular notifications and escalation notifications.


class NotificationHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    notification_id: UUID | None = None
    escalation_notification_id: UUID | None = None
    channel: NotificationChannel
    recipient_user_id: UUID
    status: NotificationDeliveryStatus
    error_message: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class NotificationHistoryListResponse(BaseModel):
    items: list[NotificationHistoryResponse]
    total: int
    page: int
    page_size: int