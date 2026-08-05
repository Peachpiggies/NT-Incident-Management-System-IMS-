"""Ticket assignment domain service and pluggable auto-routing policies.

HTTP handlers delegate assignment mutations here.  The policy classes are
deliberately storage-agnostic: a future queue worker can use exactly the same
planner without importing FastAPI or duplicating workflow writes.
"""

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Department,
    Ticket,
    TicketAssignment,
    TicketHistory,
    TicketStatus,
    User,
)
from app.services.workflow import TicketWorkflowService


@dataclass(frozen=True)
class AssignmentCandidate:
    user_id: UUID
    active_ticket_count: int = 0
    skill_codes: frozenset[str] = field(default_factory=frozenset)


class RoundRobinPolicy:
    name = "round_robin"

    def choose(
        self,
        candidates: list[AssignmentCandidate],
        *,
        last_assignee_id: UUID | None = None,
    ) -> AssignmentCandidate | None:
        ordered = sorted(candidates, key=lambda candidate: str(candidate.user_id))
        if not ordered:
            return None
        if last_assignee_id is None:
            return ordered[0]
        for index, candidate in enumerate(ordered):
            if candidate.user_id == last_assignee_id:
                return ordered[(index + 1) % len(ordered)]
        return ordered[0]


class LeastWorkloadPolicy:
    name = "least_workload"

    def choose(
        self, candidates: list[AssignmentCandidate]
    ) -> AssignmentCandidate | None:
        return min(
            candidates,
            key=lambda candidate: (
                candidate.active_ticket_count,
                str(candidate.user_id),
            ),
            default=None,
        )


class SkillBasedPolicy:
    name = "skill_based"

    def choose(
        self, candidates: list[AssignmentCandidate], *, required_skills: set[str]
    ) -> AssignmentCandidate | None:
        eligible = [
            candidate
            for candidate in candidates
            if required_skills.issubset(candidate.skill_codes)
        ]
        return LeastWorkloadPolicy().choose(eligible)


AUTO_ASSIGNMENT_POLICIES = {
    RoundRobinPolicy.name: RoundRobinPolicy(),
    LeastWorkloadPolicy.name: LeastWorkloadPolicy(),
    SkillBasedPolicy.name: SkillBasedPolicy(),
}


class AssignmentService:
    """Owns transactional writes for manual assignment and department routing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def assign_department(
        self,
        ticket: Ticket,
        department_id: UUID,
        actor: User,
        *,
        reason: str | None = None,
    ) -> Department:
        department = await self.db.scalar(
            select(Department).where(
                Department.id == department_id,
                Department.is_active.is_(True),
                Department.is_deleted.is_(False),
            )
        )
        if department is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department"
            )
        previous_department = ticket.department_id
        ticket.department_id = department.id
        ticket.updated_by = actor.id
        self.db.add(
            TicketHistory(
                ticket_id=ticket.id,
                performed_by=actor.id,
                action="ticket.assign_department",
                field="department_id",
                old_value=str(previous_department) if previous_department else None,
                new_value=str(department.id),
                remark=reason,
            )
        )
        return department

    async def assign_user(
        self,
        ticket: Ticket,
        assignee_id: UUID,
        actor: User,
        *,
        reason: str | None = None,
    ) -> User:
        assignee = await self.db.get(User, assignee_id)
        if assignee is None or not assignee.is_active or assignee.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee"
            )
        previous_assignee = ticket.assigned_to
        ticket.assigned_to = assignee.id
        ticket.updated_by = actor.id
        await TicketWorkflowService(self.db).transition_to_code(
            ticket, "ASSIGNED", actor, action="ticket.assign", remark=reason
        )
        self.db.add(
            TicketAssignment(
                ticket_id=ticket.id,
                assigned_from=previous_assignee,
                assigned_to=assignee.id,
                reason=reason,
                created_by=actor.id,
            )
        )
        return assignee

    async def candidates_for_department(
        self, department_id: UUID | None
    ) -> list[AssignmentCandidate]:
        if department_id is None:
            return []
        open_statuses = select(TicketStatus.id).where(
            TicketStatus.is_closed.is_(False), TicketStatus.is_deleted.is_(False)
        )
        rows = (
            await self.db.execute(
                select(User.id, func.count(Ticket.id))
                .outerjoin(
                    Ticket,
                    (Ticket.assigned_to == User.id)
                    & Ticket.is_deleted.is_(False)
                    & Ticket.status_id.in_(open_statuses),
                )
                .where(
                    User.department_id == department_id,
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
                .group_by(User.id)
            )
        ).all()
        return [
            AssignmentCandidate(user_id=user_id, active_ticket_count=count)
            for user_id, count in rows
        ]

    async def auto_assign(
        self,
        ticket: Ticket,
        actor: User,
        *,
        strategy: str,
        last_assignee_id: UUID | None = None,
        required_skills: set[str] | None = None,
    ) -> User | None:
        """Select and persist an assignee when a queue worker enables routing.

        ``last_assignee_id`` is intentionally an input: a later routing-state
        repository can persist the round-robin cursor without changing policy
        behaviour or the ticket router.
        """
        policy = AUTO_ASSIGNMENT_POLICIES.get(strategy)
        if policy is None:
            raise ValueError(f"Unsupported assignment strategy: {strategy}")
        candidates = await self.candidates_for_department(ticket.department_id)
        if isinstance(policy, RoundRobinPolicy):
            selected = policy.choose(candidates, last_assignee_id=last_assignee_id)
        elif isinstance(policy, SkillBasedPolicy):
            selected = policy.choose(
                candidates, required_skills=required_skills or set()
            )
        else:
            selected = policy.choose(candidates)
        if selected is None:
            return None
        return await self.assign_user(
            ticket,
            selected.user_id,
            actor,
            reason=f"Auto-assigned using {strategy}",
        )
