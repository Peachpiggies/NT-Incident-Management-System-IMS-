"""Phase 6 dashboards, analytics, reports, and exports."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_permission
from app.db.models import User
from app.db.session import get_db
from app.schemas.dashboard import (
    AnalyticsMetricResponse,
    ChangeReportResponse,
    DashboardOverviewResponse,
    DashboardScope,
    MDDRReportResponse,
    ReportResponse,
    SLAReportResponse,
)
from app.services.analytics import AnalyticsService

router = APIRouter(tags=["Dashboard & Analytics"])
DateQuery = Annotated[date | None, Query()]
LimitQuery = Annotated[int, Query(ge=1, le=10000)]


@router.get("/dashboards/executive", response_model=DashboardOverviewResponse)
async def executive_dashboard(
    current_user: Annotated[User, Depends(require_permission("dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
) -> DashboardOverviewResponse:
    return await AnalyticsService(db).overview(current_user, DashboardScope.EXECUTIVE, from_date, to_date)


@router.get("/dashboards/manager", response_model=DashboardOverviewResponse)
async def manager_dashboard(
    current_user: Annotated[User, Depends(require_permission("dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
) -> DashboardOverviewResponse:
    return await AnalyticsService(db).overview(current_user, DashboardScope.MANAGER, from_date, to_date)


@router.get("/dashboards/helpdesk", response_model=DashboardOverviewResponse)
async def helpdesk_dashboard(
    current_user: Annotated[User, Depends(require_permission("dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
) -> DashboardOverviewResponse:
    return await AnalyticsService(db).overview(current_user, DashboardScope.HELPDESK, from_date, to_date)


@router.get("/dashboards/customer", response_model=DashboardOverviewResponse)
async def customer_dashboard(
    current_user: Annotated[User, Depends(require_permission("dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
) -> DashboardOverviewResponse:
    return await AnalyticsService(db).overview(current_user, DashboardScope.CUSTOMER, from_date, to_date)


@router.get("/dashboards/sla", response_model=SLAReportResponse)
async def sla_dashboard(
    current_user: Annotated[User, Depends(require_permission("dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
    limit: LimitQuery = 1000,
) -> SLAReportResponse:
    return await AnalyticsService(db).sla_report(current_user, from_date, to_date, limit)



@router.get("/analytics/metrics", response_model=AnalyticsMetricResponse)
async def analytics_metrics(
    current_user: Annotated[User, Depends(require_permission("report.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
) -> AnalyticsMetricResponse:
    return await AnalyticsService(db).metrics(current_user, from_date, to_date)


@router.get("/reports/tickets", response_model=ReportResponse)
async def tickets_report(
    current_user: Annotated[User, Depends(require_permission("report.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
    limit: LimitQuery = 1000,
) -> ReportResponse:
    return await AnalyticsService(db).ticket_report(current_user, from_date, to_date, limit)


@router.get("/reports/sla", response_model=SLAReportResponse)
async def sla_report(
    current_user: Annotated[User, Depends(require_permission("report.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
    limit: LimitQuery = 1000,
) -> SLAReportResponse:
    return await AnalyticsService(db).sla_report(current_user, from_date, to_date, limit)


@router.get("/reports/mddr", response_model=MDDRReportResponse)
async def mddr_report(
    current_user: Annotated[User, Depends(require_permission("report.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
    limit: LimitQuery = 1000,
) -> MDDRReportResponse:
    return await AnalyticsService(db).mddr_report(current_user, from_date, to_date, limit)


@router.get("/reports/changes", response_model=ChangeReportResponse)
async def change_report(
    current_user: Annotated[User, Depends(require_permission("report.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
    limit: LimitQuery = 1000,
) -> ChangeReportResponse:
    return await AnalyticsService(db).change_report(current_user, from_date, to_date, limit)


@router.get("/reports/{report_name}/export.csv")
async def export_report(
    report_name: str,
    current_user: Annotated[User, Depends(require_permission("report.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: DateQuery = None,
    to_date: DateQuery = None,
    limit: LimitQuery = 1000,
) -> Response:
    service = AnalyticsService(db)
    if report_name == "tickets":
        payload = await service.ticket_report(current_user, from_date, to_date, limit)
    elif report_name == "sla":
        payload = await service.sla_report(current_user, from_date, to_date, limit)
    elif report_name == "mddr":
        payload = await service.mddr_report(current_user, from_date, to_date, limit)
    elif report_name == "changes":
        payload = await service.change_report(current_user, from_date, to_date, limit)
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown report")
    return Response(
        content=service.to_csv(report_name, payload),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_name}-report.csv"'},
    )