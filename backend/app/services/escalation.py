"""Ticket escalation domain service: Functional vs Technical.

Mirrors AssignmentService/TicketWorkflowService: HTTP handlers delegate
mutations here; this module owns the transactional writes.

FUNCTIONAL escalation = re-routing to a more appropriate team (e.g.
Helpdesk -> Billing). Tier does not need to change. Modeled directly after
`AssignmentService.assign_department`: it changes `ticket.department_id`
and writes history, but does NOT force a status transition -- routing to a
different team isn't inherently an SLA-relevant event. It DOES clear the
assignee, though (unlike assign_department), since the receiving team has
its own queue and shouldn't inherit an assignee from a different function.

TECHNICAL escalation = moving up the expertise chain, T1 -> T2 -> T3,
because the problem exceeds the current tier's capability. Requires a
reason from a controlled vocabulary and DOES transition the ticket to the
existing "ESCALATED" status -- same status the old plain-escalate endpoint
used, so queue filtering (`/tickets/queues/escalated`) keeps working
unchanged.

Both record `from_user_id` (the assignee at the moment of handoff) and
write a `TicketEscalation` row plus a `TicketHistory` entry.

NOTE: `action="ticket.escalate"` is passed to `transition_to_code` for the
technical path rather than a new `ticket.escalate_technical` action, so the
existing `TicketStatusTransition` row (whatever `required_permission` it's
configured with today) keeps working without new seed data -- exactly the
same trick `AssignmentService.claim` uses to reuse the `ticket.assign`
transition under a distinct endpoint permission. The endpoint-level
permission (what a caller needs to invoke the route at all) can still be
a new, more specific `ticket.escalate_technical` -- see tickets.py.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Department,
    Role,
    Ticket,
    TicketEscalation,
    TicketHistory,
    User,
    UserRole,
)
from app.services.workflow import TicketWorkflowService

MAX_TIER = 3

# Mirrors the frontend's currentStepFromTicket() (tickets/[id]/page.tsx),
# which maps Ticket.current_tier -> the escalation-rail role currently
# holding the ticket (tier 1 -> helpdesk_t1, tier 2 -> helpdesk_t2, tier 3
# and above -> manager, since there's no dedicated tier-3 role in this
# backend). Used here to enforce server-side that only the role currently
# holding the ticket -- not just any role with the endpoint permission --
# can escalate it further. "admin" is exempt: system administrators can
# act on any ticket regardless of tier.
TIER_ROLE_CODE = {1: "helpdesk_t1", 2: "helpdesk_t2", 3: "manager"}


async def _require_current_tier_holder(db: AsyncSession, ticket: Ticket, actor: User) -> None:
    """Raise 403 unless `actor` holds the role for `ticket`'s current tier.

    `require_permission("ticket.escalate_technical"/"...functional")` only
    checks whether the actor's role has that permission *at all* -- it does
    not check whether the actor is actually the team currently holding the
    ticket. Without this, e.g. a Helpdesk T1 user (or any Manager/Admin)
    could escalate a ticket that has already moved on to T2/T3, since their
    role still carries the generic permission. This closes that gap by
    additionally requiring the actor's own role to match the tier the
    ticket is *currently* sitting at.
    """
    role_codes = set(
        (
            await db.execute(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(
                    UserRole.user_id == actor.id,
                    UserRole.is_deleted.is_(False),
                    Role.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if "admin" in role_codes:
        return
    required_role = TIER_ROLE_CODE.get(min(ticket.current_tier, MAX_TIER))
    if required_role not in role_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only the team currently holding this ticket "
                f"(tier {ticket.current_tier}) or an admin can escalate it"
            ),
        )

# Controlled vocabulary for TECHNICAL escalation reasons. SLA_RISK / MDDR_RISK
# correspond to Ticket.sla_breached and the occurred/detected/diagnosed
# checkpoints respectively (see IncidentTrackingService). Not enforced for
# FUNCTIONAL escalations, which route by team rather than by capability gap.
TECHNICAL_REASON_CODES = {
    "SKILL_REQUIRED",
    "COMPLEXITY",
    "ACCESS_REQUIRED",
    "SYSTEM_DEPENDENCY",
    "UNRESOLVED_AFTER_ATTEMPTS",
    "SLA_RISK",
    "MDDR_RISK",
}


class TicketEscalationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _active_department(self, department_id: UUID) -> Department:
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
        return department

    async def escalate_functional(
        self,
        ticket: Ticket,
        to_department_id: UUID,
        actor: User,
        *,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> TicketEscalation:
        """Re-route to a more appropriate team. Tier is unaffected."""
        await _require_current_tier_holder(self.db, ticket, actor)
        department = await self._active_department(to_department_id)
        from_department_id = ticket.department_id
        from_user_id = ticket.assigned_to

        escalation = TicketEscalation(
            ticket_id=ticket.id,
            escalation_type="FUNCTIONAL",
            from_tier=ticket.current_tier,
            to_tier=ticket.current_tier,
            from_department_id=from_department_id,
            to_department_id=department.id,
            from_user_id=from_user_id,
            reason_code=reason_code,
            comment=comment,
            escalated_by=actor.id,
            created_by=actor.id,
        )
        self.db.add(escalation)

        ticket.department_id = department.id
        ticket.assigned_to = None
        ticket.updated_by = actor.id
        # Lock the department we're escalating away from: it can't self-claim
        # this ticket back until a supervisor manually reassigns it (see
        # AssignmentService.claim / assign_user).
        ticket.escalation_locked_department_id = from_department_id
        ticket.escalation_locked_tier = ticket.current_tier
        self.db.add(
            TicketHistory(
                ticket_id=ticket.id,
                performed_by=actor.id,
                action="ticket.escalate_functional",
                field="department_id",
                old_value=str(from_department_id) if from_department_id else None,
                new_value=str(department.id),
                remark=reason_code or comment,
            )
        )
        return escalation

    async def escalate_technical(
        self,
        ticket: Ticket,
        to_tier: int,
        actor: User,
        *,
        reason_code: str,
        to_department_id: UUID | None = None,
        comment: str | None = None,
        allow_tier_skip: bool = False,
    ) -> TicketEscalation:
        """Move up the expertise chain (T1 -> T2 -> T3)."""
        await _require_current_tier_holder(self.db, ticket, actor)
        if reason_code not in TECHNICAL_REASON_CODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"reason_code must be one of {sorted(TECHNICAL_REASON_CODES)} "
                    "for a technical escalation"
                ),
            )
        if to_tier > MAX_TIER:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot escalate past tier {MAX_TIER}",
            )
        if to_tier <= ticket.current_tier:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"to_tier must be higher than current tier ({ticket.current_tier})",
            )
        if not allow_tier_skip and to_tier != ticket.current_tier + 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Technical escalation must move exactly one tier at a "
                    f"time (from {ticket.current_tier} to {ticket.current_tier + 1})"
                ),
            )

        department = (
            await self._active_department(to_department_id)
            if to_department_id
            else None
        )
        from_department_id = ticket.department_id
        from_user_id = ticket.assigned_to
        from_tier = ticket.current_tier

        escalation = TicketEscalation(
            ticket_id=ticket.id,
            escalation_type="TECHNICAL",
            from_tier=from_tier,
            to_tier=to_tier,
            from_department_id=from_department_id,
            to_department_id=department.id if department else from_department_id,
            from_user_id=from_user_id,
            reason_code=reason_code,
            comment=comment,
            escalated_by=actor.id,
            created_by=actor.id,
        )
        self.db.add(escalation)

        ticket.current_tier = to_tier
        if department is not None and department.id != from_department_id:
            ticket.department_id = department.id
            ticket.assigned_to = None
        ticket.updated_by = actor.id
        # Lock the tier/department we just escalated away from: it can't
        # self-claim this ticket back until a supervisor manually reassigns
        # it (see AssignmentService.claim / assign_user).
        ticket.escalation_locked_department_id = from_department_id
        ticket.escalation_locked_tier = from_tier
        self.db.add(
            TicketHistory(
                ticket_id=ticket.id,
                performed_by=actor.id,
                action="ticket.escalate_technical",
                field="current_tier",
                old_value=str(from_tier),
                new_value=str(to_tier),
                remark=f"{reason_code}: {comment}" if comment else reason_code,
            )
        )
        # See module docstring for why action="ticket.escalate" here.
        # Guard against re-triggering the same status: a ticket that has
        # already been escalated once (status == ESCALATED) will hit this
        # path again on every subsequent tier bump (T1->T2, T2->T3). There is
        # no ESCALATED -> ESCALATED self-transition configured, so calling
        # transition_to_code unconditionally raises InvalidStatusTransition
        # ("No active transition configured from X to X") even though the
        # tier change itself (current_tier, above) is perfectly valid.
        if ticket.status is None or ticket.status.code != "ESCALATED":
            await TicketWorkflowService(self.db).transition_to_code(
                ticket,
                "ESCALATED",
                actor,
                action="ticket.escalate",
                remark=f"Technical escalation to tier {to_tier} ({reason_code})",
            )
        return escalation