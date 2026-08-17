"""Problem Management service layer.

`Problem.status` is a fixed five-value workflow -- OPEN ->
UNDER_INVESTIGATION -> KNOWN_ERROR -> RESOLVED -> CLOSED, with
UNDER_INVESTIGATION able to move straight to RESOLVED when no workaround
was ever published -- matching the fixed `ProblemStatus` enum already
declared in app.schemas.problem. Unlike TicketStatus/KBArticleStatus this
isn't configurable master data, so `transition()` below checks a small
hardcoded edge set rather than a database table, mirroring
app/services/rca.py's approach for RCAReport.

`problem_no` allocation mirrors `_next_ticket_number` in
app/api/v1/tickets.py: one row-locked counter per UTC day in
`ProblemNumberSequence`, atomically incremented via an upsert that works
on both PostgreSQL and SQLite.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Problem, ProblemNumberSequence, User

STATUS_OPEN = "OPEN"
STATUS_UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
STATUS_KNOWN_ERROR = "KNOWN_ERROR"
STATUS_RESOLVED = "RESOLVED"
STATUS_CLOSED = "CLOSED"

# (from, to): required_permission
_TRANSITIONS: dict[tuple[str, str], str] = {
    (STATUS_OPEN, STATUS_UNDER_INVESTIGATION): "problem.investigate",
    (STATUS_UNDER_INVESTIGATION, STATUS_KNOWN_ERROR): "problem.identify_known_error",
    (STATUS_UNDER_INVESTIGATION, STATUS_RESOLVED): "problem.resolve",
    (STATUS_KNOWN_ERROR, STATUS_RESOLVED): "problem.resolve",
    (STATUS_RESOLVED, STATUS_CLOSED): "problem.close",
    (STATUS_RESOLVED, STATUS_UNDER_INVESTIGATION): "problem.reopen",
    (STATUS_CLOSED, STATUS_UNDER_INVESTIGATION): "problem.reopen",
}


def required_permission_for(from_status: str, to_status: str) -> str | None:
    """Look up the permission the (from_status -> to_status) edge requires,
    or None if that edge isn't a valid transition. Single source of truth
    for both the router's pre-check and `ProblemService.transition`'s
    enforcement, so the two can't drift out of sync."""
    return _TRANSITIONS.get((from_status, to_status))


class ProblemService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_404(self, problem_id: UUID) -> Problem:
        problem = await self.db.scalar(select(Problem).where(Problem.id == problem_id))
        if problem is None or problem.is_deleted:
            raise HTTPException(status_code=404, detail="Problem not found")
        return problem

    async def next_problem_number(self) -> str:
        """Atomically allocate a daily problem number on PostgreSQL or SQLite."""
        business_date = datetime.now(timezone.utc).date()
        dialect_name = self.db.get_bind().dialect.name
        insert = postgres_insert if dialect_name == "postgresql" else sqlite_insert
        statement = (
            insert(ProblemNumberSequence)
            .values(business_date=business_date, last_value=1)
            .on_conflict_do_update(
                index_elements=[ProblemNumberSequence.business_date],
                set_={"last_value": ProblemNumberSequence.last_value + 1},
            )
            .returning(ProblemNumberSequence.last_value)
        )
        sequence = await self.db.scalar(statement)
        return f"PRB-{business_date:%Y%m%d}-{sequence:06d}"

    async def transition(
        self,
        problem: Problem,
        to_status: str,
        actor: User,
        *,
        required_permission: str,
    ) -> Problem:
        edge = (problem.status, to_status)
        if edge not in _TRANSITIONS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot move problem from {problem.status} to {to_status}",
            )
        expected_permission = _TRANSITIONS[edge]
        if expected_permission != required_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {expected_permission}",
            )

        problem.status = to_status
        problem.updated_by = actor.id
        now = datetime.now(timezone.utc)
        if to_status == STATUS_RESOLVED:
            problem.resolved_at = now
        elif to_status == STATUS_CLOSED:
            problem.closed_at = now
        elif to_status == STATUS_UNDER_INVESTIGATION:
            # Reopen: clear terminal timestamps from a prior resolve/close.
            problem.resolved_at = None
            problem.closed_at = None

        await self.db.commit()
        await self.db.refresh(problem)
        return problem
