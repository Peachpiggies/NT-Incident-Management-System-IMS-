"""Configurable ticket workflow domain service.

No API handler may set ``Ticket.status_id`` directly.  This service validates
the configured directed transition and stages the status/history changes in the
caller's transaction.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Ticket,
    TicketHistory,
    TicketStatus,
    TicketStatusTransition,
    User,
)


class TicketWorkflowService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def transition_to_code(
        self,
        ticket: Ticket,
        to_status_code: str,
        actor: User,
        *,
        action: str,
        remark: str | None = None,
    ) -> TicketStatusTransition:
        to_status = await self.db.scalar(
            select(TicketStatus).where(
                TicketStatus.code == to_status_code,
                TicketStatus.is_active.is_(True),
                TicketStatus.is_deleted.is_(False),
            )
        )
        if to_status is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ticket status {to_status_code} is not configured",
            )
        return await self.transition_to_status(
            ticket, to_status.id, actor, action=action, remark=remark
        )

    async def transition_to_status(
        self,
        ticket: Ticket,
        to_status_id: UUID,
        actor: User,
        *,
        action: str,
        remark: str | None = None,
    ) -> TicketStatusTransition:
        current_status = await self.db.get(TicketStatus, ticket.status_id)
        transition = await self.db.scalar(
            select(TicketStatusTransition).where(
                TicketStatusTransition.from_status_id == ticket.status_id,
                TicketStatusTransition.to_status_id == to_status_id,
                TicketStatusTransition.is_active.is_(True),
                TicketStatusTransition.is_deleted.is_(False),
            )
        )
        if transition is None:
            target = await self.db.get(TicketStatus, to_status_id)
            from_code = current_status.code if current_status else str(ticket.status_id)
            to_code = target.code if target else str(to_status_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transition {from_code} -> {to_code} is not allowed",
            )
        if transition.required_permission and transition.required_permission != action:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Transition requires permission: {transition.required_permission}",
            )
        ticket.status_id = to_status_id
        ticket.updated_by = actor.id
        self.db.add(
            TicketHistory(
                ticket_id=ticket.id,
                performed_by=actor.id,
                action=action,
                field="status",
                old_value=current_status.code if current_status else None,
                new_value=(await self.db.get(TicketStatus, to_status_id)).code,
                remark=remark,
            )
        )
        return transition


async def commit_ticket_transaction(db: AsyncSession) -> None:
    """Commit a ticket mutation, its history, and its events atomically."""
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
