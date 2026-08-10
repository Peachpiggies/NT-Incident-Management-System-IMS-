"""
Dashboard schemas.

This module contains all response schemas related to the
dashboard overview, summary stats, and charts.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ==========================================================
# Summary Cards
# ==========================================================


class DashboardSummaryResponse(BaseModel):
    """Top-level summary cards shown on the dashboard."""

    total_users: int
    active_users: int
    total_departments: int
    unread_notifications: int


# ==========================================================
# Charts
# ==========================================================


class ChartDataPoint(BaseModel):
    """A single (label, value) point, e.g. for a bar/line chart."""

    label: str
    value: float


class TimeSeriesPoint(BaseModel):
    """A single point in a time series chart."""

    date: date
    value: float


class DepartmentBreakdown(BaseModel):
    """Distribution of users (or another metric) across departments."""

    department_id: UUID
    department_name: str
    count: int


# ==========================================================
# Recent Activity
# ==========================================================


class RecentActivityItem(BaseModel):
    """A single entry in the dashboard's recent activity feed."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_name: str
    action: str
    target: str | None = None
    created_at: datetime


# ==========================================================
# Aggregate Response
# ==========================================================


class DashboardOverviewResponse(BaseModel):
    """Full payload for the main dashboard page."""

    summary: DashboardSummaryResponse
    users_by_department: list[DepartmentBreakdown]
    signups_over_time: list[TimeSeriesPoint]
    recent_activity: list[RecentActivityItem]