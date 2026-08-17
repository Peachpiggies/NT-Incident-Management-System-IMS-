"""Tests for Phase 6 dashboards, analytics, reports, and exports."""

from datetime import datetime, timezone

from app.api.v1.analytics import router
from app.schemas.dashboard import DashboardScope, ReportRow
from app.services.analytics import AnalyticsService, _minutes


def test_phase6_routes_are_registered() -> None:
    paths = {route.path for route in router.routes}
    assert "/dashboards/executive" in paths
    assert "/dashboards/manager" in paths
    assert "/dashboards/helpdesk" in paths
    assert "/dashboards/customer" in paths
    assert "/dashboards/sla" in paths
    assert "/analytics/metrics" in paths
    assert "/reports/tickets" in paths
    assert "/reports/sla" in paths
    assert "/reports/mddr" in paths
    assert "/reports/changes" in paths
    assert "/reports/{report_name}/export.csv" in paths


def test_phase6_metric_math() -> None:
    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 11, 30, tzinfo=timezone.utc)
    assert _minutes(start, end) == 90.0
    assert _minutes(start, None) is None


def test_phase6_report_schema() -> None:
    row = ReportRow(
        ticket_no="INC-0001",
        title="Example",
        status="RESOLVED",
        priority="High",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sla_breached=False,
    )
    assert row.ticket_no == "INC-0001"
    assert DashboardScope.CUSTOMER.value == "customer"
    assert AnalyticsService is not None
