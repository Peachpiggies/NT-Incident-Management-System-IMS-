"""Read-only analytics service for NT-IMS dashboards and reports."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ActivityLog,
    ChangeRequest,
    Department,
    Role,
    Ticket,
    TicketHistory,
    TicketPriority,
    TicketSlaTimer,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.dashboard import (
    AnalyticsMetricResponse,
    ChangeReportResponse,
    ChangeReportRow,
    DashboardOverviewResponse,
    DashboardScope,
    DashboardSummaryResponse,
    DistributionItem,
    MDDRReportResponse,
    MDDRReportRow,
    RecentActivityItem,
    ReportResponse,
    ReportRow,
    SLAReportResponse,
    SLAReportRow,
    TrendPoint,
)

UTC = timezone.utc


def _period_bounds(from_date: date | None, to_date: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(from_date, time.min, tzinfo=UTC) if from_date else None
    end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC) if to_date else None
    return start, end


def _minutes(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() / 60.0)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def role_codes(self, user_id) -> set[str]:
        rows = await self.db.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
            )
        )
        return set(rows.all())

    async def scope_filter(self, user: User):
        roles = await self.role_codes(user.id)
        if "admin" in roles or "manager" in roles:
            return None
        if "customer" in roles:
            return Ticket.requester_id == user.id
        if user.department_id is None:
            return Ticket.assigned_to == user.id
        return (Ticket.department_id == user.department_id) | (Ticket.assigned_to == user.id)

    async def overview(
        self,
        user: User,
        scope: DashboardScope,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> DashboardOverviewResponse:
        roles = await self.role_codes(user.id)
        if scope in {DashboardScope.EXECUTIVE, DashboardScope.MANAGER} and not ({"admin", "manager"} & roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
        if scope == DashboardScope.HELPDESK and not ({"admin", "manager", "helpdesk_t1", "helpdesk_t2"} & roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Helpdesk access required")
        start, end = _period_bounds(from_date, to_date)
        ticket_scope = await self.scope_filter(user)
        filters = [Ticket.is_deleted.is_(False)]
        if ticket_scope is not None:
            filters.append(ticket_scope)
        if start is not None:
            filters.append(Ticket.created_at >= start)
        if end is not None:
            filters.append(Ticket.created_at < end)

        total = int(await self.db.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0)
        closed_subq = await self.db.scalar(
            select(func.count()).select_from(Ticket).where(*filters, Ticket.closed_at.is_not(None))
        )
        resolved = await self.db.scalar(
            select(func.count()).select_from(Ticket).where(*filters, Ticket.resolved_at.is_not(None))
        )
        unassigned = await self.db.scalar(
            select(func.count()).select_from(Ticket).where(*filters, Ticket.assigned_to.is_(None))
        )
        breached = await self.db.scalar(
            select(func.count()).select_from(Ticket).where(*filters, Ticket.sla_breached.is_(True))
        )

        status_rows = await self.db.execute(
            select(TicketStatus.code, func.count(Ticket.id))
            .select_from(Ticket)
            .join(TicketStatus, Ticket.status_id == TicketStatus.id)
            .where(*filters)
            .group_by(TicketStatus.code)
            .order_by(func.count(Ticket.id).desc())
        )
        priority_rows = await self.db.execute(
            select(TicketPriority.name, func.count(Ticket.id))
            .select_from(Ticket)
            .join(TicketPriority, Ticket.priority_id == TicketPriority.id)
            .where(*filters)
            .group_by(TicketPriority.name)
            .order_by(func.count(Ticket.id).desc())
        )
        department_rows = await self.db.execute(
            select(Department.name, func.count(Ticket.id))
            .select_from(Ticket)
            .outerjoin(Department, Ticket.department_id == Department.id)
            .where(*filters)
            .group_by(Department.name)
            .order_by(func.count(Ticket.id).desc())
        )

        tickets = (await self.db.scalars(
            select(Ticket)
            .where(*filters)
            .options(selectinload(Ticket.assignee), selectinload(Ticket.department), selectinload(Ticket.status), selectinload(Ticket.priority))
            .order_by(Ticket.created_at.desc())
            .limit(10000)
        )).all()

        history_rows = await self.db.execute(
            select(TicketHistory.ticket_id, func.min(TicketHistory.performed_at))
            .where(
                TicketHistory.ticket_id.in_([ticket.id for ticket in tickets]),
                TicketHistory.is_deleted.is_(False),
                TicketHistory.action.in_(("ticket.assign", "ticket.start", "assign", "ticket.receive_escalated")),
            )
            .group_by(TicketHistory.ticket_id)
        ) if tickets else None
        first_actions = {ticket_id: occurred_at for ticket_id, occurred_at in (history_rows.all() if history_rows else [])}
        mtta_values: list[float] = []
        mttr_values: list[float] = []
        mddr_values: list[float] = []
        for ticket in tickets:
            first_action = first_actions.get(ticket.id)
            mtta = _minutes(ticket.created_at, first_action)
            if mtta is not None:
                mtta_values.append(mtta)
            mttr = _minutes(ticket.detected_at, ticket.resolved_at)
            if mttr is not None:
                mttr_values.append(mttr)
            mddr = _minutes(ticket.occurred_at, ticket.resolved_at)
            if mddr is not None:
                mddr_values.append(mddr)

        timer_filters = [TicketSlaTimer.is_deleted.is_(False)]
        if start is not None:
            timer_filters.append(TicketSlaTimer.started_at >= start)
        if end is not None:
            timer_filters.append(TicketSlaTimer.started_at < end)
        if ticket_scope is not None:
            timer_ticket_ids = select(Ticket.id).where(ticket_scope, Ticket.is_deleted.is_(False))
            timer_filters.append(TicketSlaTimer.ticket_id.in_(timer_ticket_ids))
        timer_rows = await self.db.execute(
            select(TicketSlaTimer.status, func.count()).where(*timer_filters).group_by(TicketSlaTimer.status)
        )
        timer_summary = {row[0]: int(row[1]) for row in timer_rows.all()}

        trend: list[TrendPoint] = []
        mddr_trend: list[TrendPoint] = []
        grouped: dict[date, int] = defaultdict(int)
        grouped_mddr: dict[date, list[float]] = defaultdict(list)
        for ticket in tickets:
            grouped[ticket.created_at.date()] += 1
            mddr = _minutes(ticket.occurred_at, ticket.resolved_at)
            if mddr is not None:
                grouped_mddr[ticket.created_at.date()].append(mddr)
        for day in sorted(grouped):
            trend.append(TrendPoint(date=day, value=grouped[day]))
        for day in sorted(grouped_mddr):
            values = grouped_mddr[day]
            mddr_trend.append(TrendPoint(date=day, value=sum(values) / len(values)))

        change_filters = [ChangeRequest.is_deleted.is_(False)]
        if start is not None:
            change_filters.append(ChangeRequest.created_at >= start)
        if end is not None:
            change_filters.append(ChangeRequest.created_at < end)
        change_rows = await self.db.execute(
            select(ChangeRequest.status, func.count()).where(*change_filters).group_by(ChangeRequest.status)
        )
        change_summary = {row[0]: int(row[1]) for row in change_rows.all()}

        activity_filters = [ActivityLog.is_deleted.is_(False)]
        if "customer" in roles and not ({"admin", "manager", "helpdesk_t1", "helpdesk_t2"} & roles):
            activity_filters.append(ActivityLog.user_id == user.id)
        elif not ({"admin", "manager"} & roles) and user.department_id is not None:
            activity_filters.append(
                ActivityLog.user_id.in_(
                    select(User.id).where(User.department_id == user.department_id, User.is_deleted.is_(False))
                )
            )
        activity_rows = await self.db.execute(
            select(ActivityLog, User)
            .outerjoin(User, ActivityLog.user_id == User.id)
            .where(*activity_filters)
            .order_by(ActivityLog.created_at.desc())
            .limit(20)
        )
        recent_activity = [
            RecentActivityItem(
                id=log.id,
                actor_name=user.full_name if user else "System",
                action=log.action,
                target=log.resource,
                created_at=log.created_at,
            )
            for log, user in activity_rows.all()
        ]

        return DashboardOverviewResponse(
            scope=scope,
            period_start=from_date,
            period_end=to_date,
            summary=DashboardSummaryResponse(
                total_tickets=total,
                open_tickets=max(0, total - int(closed_subq or 0)),
                unassigned_tickets=int(unassigned or 0),
                resolved_tickets=int(resolved or 0),
                closed_tickets=int(closed_subq or 0),
                sla_breached_tickets=int(breached or 0),
            ),
            metrics=AnalyticsMetricResponse(
                from_date=from_date,
                to_date=to_date,
                mddr_minutes=sum(mddr_values) / len(mddr_values) if mddr_values else None,
                mtta_minutes=sum(mtta_values) / len(mtta_values) if mtta_values else None,
                mttr_minutes=sum(mttr_values) / len(mttr_values) if mttr_values else None,
                mddr_sample_size=len(mddr_values),
                mtta_sample_size=len(mtta_values),
                mttr_sample_size=len(mttr_values),
            ),
            tickets_by_status=self._distribution(status_rows.all(), total),
            tickets_by_priority=self._distribution(priority_rows.all(), total),
            tickets_by_department=self._distribution(department_rows.all(), total),
            sla_summary=timer_summary,
            ticket_trend=trend,
            mddr_trend=mddr_trend,
            recent_activity=recent_activity,
            change_summary=change_summary,
        )

    @staticmethod
    def _distribution(rows: Iterable[tuple[str | None, int]], total: int) -> list[DistributionItem]:
        return [
            DistributionItem(label=label or "Unassigned", value=int(value), percentage=(float(value) / total * 100) if total else 0)
            for label, value in rows
        ]

    async def metrics(self, user: User, from_date: date | None, to_date: date | None) -> AnalyticsMetricResponse:
        overview = await self.overview(user, DashboardScope.MANAGER, from_date, to_date)
        return overview.metrics

    async def ticket_report(self, user: User, from_date: date | None, to_date: date | None, limit: int = 1000) -> ReportResponse:
        start, end = _period_bounds(from_date, to_date)
        scope = await self.scope_filter(user)
        filters = [Ticket.is_deleted.is_(False)]
        if scope is not None:
            filters.append(scope)
        if start is not None:
            filters.append(Ticket.created_at >= start)
        if end is not None:
            filters.append(Ticket.created_at < end)
        tickets = (await self.db.scalars(
            select(Ticket)
            .where(*filters)
            .options(selectinload(Ticket.assignee), selectinload(Ticket.department), selectinload(Ticket.status), selectinload(Ticket.priority))
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )).all()
        history_rows = await self.db.execute(
            select(TicketHistory.ticket_id, func.min(TicketHistory.performed_at))
            .where(
                TicketHistory.ticket_id.in_([ticket.id for ticket in tickets]),
                TicketHistory.is_deleted.is_(False),
                TicketHistory.action.in_(("ticket.assign", "ticket.start", "assign", "ticket.receive_escalated")),
            )
            .group_by(TicketHistory.ticket_id)
        ) if tickets else None
        first_actions = {ticket_id: occurred_at for ticket_id, occurred_at in (history_rows.all() if history_rows else [])}
        rows: list[ReportRow] = []
        for ticket in tickets:
            first_action = first_actions.get(ticket.id)
            rows.append(ReportRow(
                ticket_no=ticket.ticket_no,
                title=ticket.title,
                status=ticket.status.code,
                priority=ticket.priority.name,
                department=ticket.department.name if ticket.department else None,
                assignee=ticket.assignee.full_name if ticket.assignee else None,
                created_at=ticket.created_at,
                occurred_at=ticket.occurred_at,
                detected_at=ticket.detected_at,
                diagnosed_at=ticket.diagnosed_at,
                resolved_at=ticket.resolved_at,
                closed_at=ticket.closed_at,
                sla_breached=ticket.sla_breached,
                mtta_minutes=_minutes(ticket.created_at, first_action),
                mtdr_minutes=_minutes(ticket.detected_at, ticket.diagnosed_at),
                mttr_minutes=_minutes(ticket.detected_at, ticket.resolved_at),
            ))
        return ReportResponse(
            report="tickets",
            generated_at=datetime.now(UTC),
            from_date=from_date,
            to_date=to_date,
            total=len(rows),
            rows=rows,
        )

    async def sla_report(self, user: User, from_date: date | None, to_date: date | None, limit: int = 1000) -> SLAReportResponse:
        start, end = _period_bounds(from_date, to_date)
        ticket_scope = await self.scope_filter(user)
        filters = [TicketSlaTimer.is_deleted.is_(False)]
        if start is not None:
            filters.append(TicketSlaTimer.started_at >= start)
        if end is not None:
            filters.append(TicketSlaTimer.started_at < end)
        if ticket_scope is not None:
            filters.append(TicketSlaTimer.ticket_id.in_(select(Ticket.id).where(ticket_scope, Ticket.is_deleted.is_(False))))
        timer_rows = await self.db.execute(
            select(TicketSlaTimer, Ticket.ticket_no)
            .join(Ticket, Ticket.id == TicketSlaTimer.ticket_id)
            .where(*filters, Ticket.is_deleted.is_(False))
            .order_by(TicketSlaTimer.started_at.desc())
            .limit(limit)
        )
        rows: list[SLAReportRow] = []
        counts = {"ON_TRACK": 0, "BREACHED": 0, "MET": 0}
        now = datetime.now(UTC)
        for timer, ticket_no in timer_rows.all():
            completed_at = timer.met_at or timer.breached_at or timer.cancelled_at
            reference = completed_at or now
            elapsed = max(0.0, (reference - timer.started_at).total_seconds() / 60.0 - timer.total_paused_seconds / 60.0)
            remaining = max(0.0, timer.target_minutes - elapsed) if timer.status not in ("MET", "BREACHED", "CANCELLED") else 0.0
            if timer.status == "BREACHED":
                counts["BREACHED"] += 1
            elif timer.status == "MET":
                counts["MET"] += 1
            else:
                counts["ON_TRACK"] += 1
            rows.append(SLAReportRow(
                ticket_no=ticket_no,
                metric_type=timer.metric_type,
                status=timer.status,
                target_minutes=timer.target_minutes,
                elapsed_minutes=elapsed,
                remaining_minutes=remaining,
                started_at=timer.started_at,
                due_at=timer.due_at,
                completed_at=completed_at,
            ))
        return SLAReportResponse(
            generated_at=datetime.now(UTC),
            from_date=from_date,
            to_date=to_date,
            total=len(rows),
            on_track=counts["ON_TRACK"],
            breached=counts["BREACHED"],
            met=counts["MET"],
            rows=rows,
        )

    async def mddr_report(self, user: User, from_date: date | None, to_date: date | None, limit: int = 1000) -> MDDRReportResponse:
        start, end = _period_bounds(from_date, to_date)
        scope = await self.scope_filter(user)
        filters = [Ticket.is_deleted.is_(False)]
        if scope is not None:
            filters.append(scope)
        if start is not None:
            filters.append(Ticket.created_at >= start)
        if end is not None:
            filters.append(Ticket.created_at < end)
        tickets = (await self.db.scalars(
            select(Ticket).where(*filters).order_by(Ticket.created_at.desc()).limit(limit)
        )).all()
        rows = [
            MDDRReportRow(
                ticket_no=ticket.ticket_no,
                title=ticket.title,
                occurred_at=ticket.occurred_at,
                detected_at=ticket.detected_at,
                diagnosed_at=ticket.diagnosed_at,
                resolved_at=ticket.resolved_at,
                detection_minutes=_minutes(ticket.occurred_at, ticket.detected_at),
                diagnosis_minutes=_minutes(ticket.detected_at, ticket.diagnosed_at),
                resolution_minutes=_minutes(ticket.diagnosed_at, ticket.resolved_at),
                total_minutes=_minutes(ticket.occurred_at, ticket.resolved_at),
            )
            for ticket in tickets
        ]
        return MDDRReportResponse(
            generated_at=datetime.now(UTC),
            from_date=from_date,
            to_date=to_date,
            total=len(rows),
            rows=rows,
        )

    async def change_report(self, user: User, from_date: date | None, to_date: date | None, limit: int = 1000) -> ChangeReportResponse:
        start, end = _period_bounds(from_date, to_date)
        filters = [ChangeRequest.is_deleted.is_(False)]
        roles = await self.role_codes(user.id)
        if not ({"admin", "manager"} & roles):
            filters.append(ChangeRequest.requested_by_id == user.id)
        if start is not None:
            filters.append(ChangeRequest.created_at >= start)
        if end is not None:
            filters.append(ChangeRequest.created_at < end)
        changes = (await self.db.scalars(
            select(ChangeRequest).where(*filters).order_by(ChangeRequest.created_at.desc()).limit(limit)
        )).all()
        rows = [ChangeReportRow(
            change_no=c.change_no,
            title=c.title,
            change_type=c.change_type,
            status=c.status,
            risk_level=c.risk_level,
            planned_start=c.planned_start,
            planned_end=c.planned_end,
            created_at=c.created_at,
        ) for c in changes]
        return ChangeReportResponse(
            generated_at=datetime.now(UTC),
            from_date=from_date,
            to_date=to_date,
            total=len(rows),
            rows=rows,
        )

    @staticmethod
    def to_csv(report_name: str, payload) -> str:
        output = StringIO()
        writer = csv.writer(output)
        if report_name == "tickets":
            headers = list(ReportRow.model_fields)
            writer.writerow(headers)
            for row in payload.rows:
                writer.writerow([getattr(row, field) for field in headers])
        elif report_name == "sla":
            headers = list(SLAReportRow.model_fields)
            writer.writerow(headers)
            for row in payload.rows:
                writer.writerow([getattr(row, field) for field in headers])
        elif report_name == "mddr":
            headers = list(MDDRReportRow.model_fields)
            writer.writerow(headers)
            for row in payload.rows:
                writer.writerow([getattr(row, field) for field in headers])
        elif report_name == "changes":
            headers = list(ChangeReportRow.model_fields)
            writer.writerow(headers)
            for row in payload.rows:
                writer.writerow([getattr(row, field) for field in headers])
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown report")
        return output.getvalue()