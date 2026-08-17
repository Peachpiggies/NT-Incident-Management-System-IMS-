"""
Pydantic schemas package.

Re-exports all request/response schemas so they can be imported
directly from `app.schemas` instead of the individual submodules.
"""

from app.schemas.attachments import (
    AttachmentBase,
    AttachmentListResponse,
    AttachmentResponse,
    AttachmentSummary,
    AttachmentUpload,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    SessionResponse,
    Token,
    TokenPayload,
)
from app.schemas.comment import (
    CommentAuthor,
    CommentBase,
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
)
from app.schemas.dashboard import (
    AnalyticsMetricResponse,
    ChangeReportResponse,
    ChartDataPoint,
    DashboardOverviewResponse,
    DashboardScope,
    DashboardSummaryResponse,
    DepartmentBreakdown,
    MDDRReportResponse,
    RecentActivityItem,
    ReportResponse,
    SLAReportResponse,
    TimeSeriesPoint,
)
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationBroadcastCreate,
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    NotificationType,
    NotificationUpdate,
    UnreadCountResponse,
)

__all__ = [

    # attachments
    "AttachmentBase",
    "AttachmentListResponse",
    "AttachmentResponse",
    "AttachmentSummary",
    "AttachmentUpload",

    # auth
    "ChangePasswordRequest",
    "CurrentUser",
    "ForgotPasswordRequest",
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "MessageResponse",
    "RefreshTokenRequest",
    "RegisterRequest",
    "SessionResponse",
    "Token",
    "TokenPayload",

    # comment
    "CommentAuthor",
    "CommentBase",
    "CommentCreate",
    "CommentListResponse",
    "CommentResponse",
    "CommentUpdate",

    # dashboard
    "AnalyticsMetricResponse",
    "ChangeReportResponse",
    "DashboardScope",
    "MDDRReportResponse",
    "ReportResponse",
    "SLAReportResponse",
    "ChartDataPoint",
    "DashboardOverviewResponse",
    "DashboardSummaryResponse",
    "DepartmentBreakdown",
    "RecentActivityItem",
    "TimeSeriesPoint",

    # notification
    "MarkAllReadResponse",
    "NotificationBroadcastCreate",
    "NotificationCreate",
    "NotificationListResponse",
    "NotificationResponse",
    "NotificationType",
    "NotificationUpdate",
    "UnreadCountResponse",

]