"""Root Cause Analysis service layer.

An RCA is anchored to either a ticket (incident-level) or a problem
(problem-level). A `RootCause` gathers zero or more `ContributingFactor`s
and `ImpactAnalysis`es, and is written up as an `RCAReport`.

`RCAReport.status` is a fixed three-value workflow -- DRAFT -> IN_REVIEW ->
APPROVED, or IN_REVIEW -> DRAFT on rejection -- matching the
`RCAReportStatus` enum already declared in app.schemas.rca. Unlike
TicketStatus/KBArticleStatus this isn't configurable master data, so
`transition()` below checks a small hardcoded edge set rather than a
database table (see app/db/models.py:RCAReport docstring for why).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RCAReport, RootCause, User

STATUS_DRAFT = "DRAFT"
STATUS_IN_REVIEW = "IN_REVIEW"
STATUS_APPROVED = "APPROVED"

# (from, to): required_permission
_TRANSITIONS: dict[tuple[str, str], str] = {
    (STATUS_DRAFT, STATUS_IN_REVIEW): "rca.submit",
    (STATUS_IN_REVIEW, STATUS_APPROVED): "rca.approve",
    (STATUS_IN_REVIEW, STATUS_DRAFT): "rca.approve",
}


class RCAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_root_cause_or_404(self, root_cause_id: UUID) -> RootCause:
        root_cause = await self.db.scalar(
            select(RootCause).where(RootCause.id == root_cause_id)
        )
        if root_cause is None or root_cause.is_deleted:
            raise HTTPException(status_code=404, detail="Root cause not found")
        return root_cause

    async def get_report_or_404(self, report_id: UUID) -> RCAReport:
        report = await self.db.scalar(
            select(RCAReport).where(RCAReport.id == report_id)
        )
        if report is None or report.is_deleted:
            raise HTTPException(status_code=404, detail="RCA report not found")
        return report

    def can_view_report(self, report: RCAReport, user: User, *, can_approve: bool) -> bool:
        """APPROVED reports are visible to anyone authenticated (they're the
        published postmortem); DRAFT/IN_REVIEW are only visible to whoever
        prepared them or a holder of `rca.approve` -- mirrors the KB
        article visibility rule in app/api/v1/knowledge_base.py."""
        if report.status == STATUS_APPROVED:
            return True
        return report.prepared_by_id == user.id or can_approve

    async def transition(
        self,
        report: RCAReport,
        to_status: str,
        actor: User,
        *,
        required_permission: str,
        approve: bool = False,
    ) -> RCAReport:
        edge = (report.status, to_status)
        if edge not in _TRANSITIONS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot move RCA report from {report.status} to {to_status}",
            )
        expected_permission = _TRANSITIONS[edge]
        if expected_permission != required_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {expected_permission}",
            )

        report.status = to_status
        report.updated_by = actor.id
        if approve:
            report.approved_by_id = actor.id
            report.approved_at = datetime.now(timezone.utc)
        elif to_status == STATUS_DRAFT:
            report.approved_by_id = None
            report.approved_at = None

        await self.db.commit()
        await self.db.refresh(report)
        return report
