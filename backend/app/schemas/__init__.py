"""
Pydantic schemas package.

Re-exports all request/response schemas so they can be imported
directly from `app.schemas` instead of the individual submodules.
"""

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

    Token,

    TokenPayload,

)

from app.schemas.dashboard import (
    
    ChartDataPoint,
    
    DashboardOverviewResponse,
    
    DashboardSummaryResponse,
    
    DepartmentBreakdown,
    
    RecentActivityItem,
    
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
    "Token",
    "TokenPayload",

    # dashboard
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