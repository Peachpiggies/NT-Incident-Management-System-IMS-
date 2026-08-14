"""MDDR checkpoint tracking and SLA breach evaluation.

Genuinely new ground -- no existing service covers this. Kept separate from
`TicketEscalationService` since checkpoints/SLA apply to a ticket regardless
of whether it's ever escalated.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, TicketHistory, User

MDDR_CHECKPOINTS = ("occurred_at", "detected_at", "diagnosed_at", "resolved_at")


class IncidentTrackingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_checkpoint(
        self,
        ticket: Ticket,
        checkpoint: str,
        actor: User,
        *,
        at: datetime | None = None,
    ) -> Ticket:
        if checkpoint not in MDDR_CHECKPOINTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"checkpoint must be one of {MDDR_CHECKPOINTS}",
            )
        at = at or datetime.now(timezone.utc)
        idx = MDDR_CHECKPOINTS.index(checkpoint)

        for earlier in MDDR_CHECKPOINTS[:idx]:
            earlier_value = getattr(ticket, earlier)
            if earlier_value is not None and at < earlier_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{checkpoint} cannot be before {earlier}",
                )
        for later in MDDR_CHECKPOINTS[idx + 1 :]:
            later_value = getattr(ticket, later)
            if later_value is not None and at > later_value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{checkpoint} cannot be after {later}",
                )

        old_value = getattr(ticket, checkpoint)
        setattr(ticket, checkpoint, at)
        ticket.updated_by = actor.id
        self.db.add(
            TicketHistory(
                ticket_id=ticket.id,
                performed_by=actor.id,
                action="ticket.mddr_checkpoint",
                field=checkpoint,
                old_value=old_value.isoformat() if old_value else None,
                new_value=at.isoformat(),
            )
        )
        return ticket

    async def evaluate_sla(self, ticket: Ticket, actor: User) -> bool:
        """Recompute sla_breached against due_at.

        Frozen at resolved_at/closed_at once the ticket is done, so a slow
        close doesn't keep flipping breach state after the work is finished.
        """
        if ticket.due_at is None:
            return ticket.sla_breached

        reference = ticket.resolved_at or ticket.closed_at or datetime.now(timezone.utc)
        breached = reference > ticket.due_at

        if breached != ticket.sla_breached:
            self.db.add(
                TicketHistory(
                    ticket_id=ticket.id,
                    performed_by=actor.id,
                    action="ticket.sla_evaluation",
                    field="sla_breached",
                    old_value=str(ticket.sla_breached),
                    new_value=str(breached),
                )
            )
            ticket.sla_breached = breached
            ticket.updated_by = actor.id
        return ticket.sla_breached