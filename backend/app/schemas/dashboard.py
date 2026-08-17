"""Dashboard, analytics, report, and export response schemas."""

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardScope(str, Enum):
    EXECUTIVE = "executive"
    MANAGER = "manager"
    HELPDESK = "helpdesk"
    CUSTOMER = "customer"


class DashboardKPI(BaseModel):
    value: float
    unit: str = "count"
    target: float | None = None
    trend_percent: float | None = None


class DashboardSummaryResponse(BaseModel):
    total_tickets: int
    open_tickets: int
    unassigned_tickets: int
    resolved_tickets: int
    closed_tickets: int
    sla_breached_tickets: int
    active_users: int | None = None


class AnalyticsMetricResponse(BaseModel):
    from_date: date | None
    to_date: date | None
    mddr_minutes: float | None
    mtta_minutes: float | None
    mttr_minutes: float | None
    mddr_sample_size: int
    mtta_sample_size: int
    mttr_sample_size: int


class TrendPoint(BaseModel):
    date: date
    value: float


class DistributionItem(BaseModel):
    label: str
    value: int
    percentage: float | None = None


class RecentActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_name: str
    action: str
    target: str | None = None
    created_at: datetime


class DashboardOverviewResponse(BaseModel):
    scope: DashboardScope
    period_start: date | None
    period_end: date | None
    summary: DashboardSummaryResponse
    metrics: AnalyticsMetricResponse
    tickets_by_status: list[DistributionItem]
    tickets_by_priority: list[DistributionItem]
    tickets_by_department: list[DistributionItem]
    sla_summary: dict[str, int | float]
    ticket_trend: list[TrendPoint]
    mddr_trend: list[TrendPoint]
    recent_activity: list[RecentActivityItem]
    change_summary: dict[str, int]


class DepartmentBreakdown(BaseModel):
    department_id: UUID
    department_name: str
    count: int


class TimeSeriesPoint(BaseModel):
    date: date
    value: float


class ChartDataPoint(BaseModel):
    label: str
    value: float


class ReportRow(BaseModel):
    ticket_no: str
    title: str
    status: str
    priority: str
    department: str | None = None
    assignee: str | None = None
    created_at: datetime
    occurred_at: datetime | None = None
    detected_at: datetime | None = None
    diagnosed_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    sla_breached: bool
    mtta_minutes: float | None = None
    mtdr_minutes: float | None = None
    mttr_minutes: float | None = None


class ReportResponse(BaseModel):
    report: str
    generated_at: datetime
    from_date: date | None
    to_date: date | None
    total: int
    rows: list[ReportRow]


class SLAReportRow(BaseModel):
    ticket_no: str
    metric_type: str
    status: str
    target_minutes: int
    elapsed_minutes: float
    remaining_minutes: float | None
    started_at: datetime
    due_at: datetime
    completed_at: datetime | None


class SLAReportResponse(BaseModel):
    generated_at: datetime
    from_date: date | None
    to_date: date | None
    total: int
    on_track: int
    breached: int
    met: int
    rows: list[SLAReportRow]


class MDDRReportRow(BaseModel):
    ticket_no: str
    title: str
    occurred_at: datetime | None = None
    detected_at: datetime | None = None
    diagnosed_at: datetime | None = None
    resolved_at: datetime | None = None
    detection_minutes: float | None = None
    diagnosis_minutes: float | None = None
    resolution_minutes: float | None = None
    total_minutes: float | None = None


class MDDRReportResponse(BaseModel):
    generated_at: datetime
    from_date: date | None
    to_date: date | None
    total: int
    rows: list[MDDRReportRow]


class ChangeReportRow(BaseModel):
    change_no: str
    title: str
    change_type: str
    status: str
    risk_level: str | None
    planned_start: datetime
    planned_end: datetime
    created_at: datetime


class ChangeReportResponse(BaseModel):
    generated_at: datetime
    from_date: date | None
    to_date: date | None
    total: int
    rows: list[ChangeReportRow]
