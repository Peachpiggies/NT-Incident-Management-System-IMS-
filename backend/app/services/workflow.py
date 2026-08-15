"""Async facade for the configurable ticket workflow.

The HTTP application uses AsyncSession, while the original domain workflow
implementation is synchronous. The facade deliberately delegates the actual
transition to that implementation through AsyncSession.run_sync(), so there
is one authoritative transition graph and one set of history semantics.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, TicketSlaTimer, TicketStatus, TicketStatusTransition, User
from app.services import ticket_workflow as sync_ticket_workflow


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
        target_status = await self.db.get(TicketStatus, to_status_id)
        if target_status is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ticket status {to_status_id} is not configured",
            )

        def _run(session):
            # The object passed by AsyncSession is attached to this underlying
            # sync session while inside run_sync.
            def has_permission(required: str) -> bool:
                # Endpoint-level authorization is already enforced. The
                # configured transition permission is represented by the
                # action passed by the API workflow endpoint.
                return required == action

            def on_status_changed(sync_session, sync_ticket, new_status_id):
                # Import here avoids a module-level cycle and keeps the SLA
                # engine integration on the same sync transaction.
                from app.services import sla_engine

                sla_engine.apply_status_pause_rules(
                    sync_session,
                    sync_ticket,
                    new_status_id=new_status_id,
                    actor_id=actor.id,
                )
                if target_status.code in {"RESOLVED", "CLOSED"}:
                    resolution_timer = sync_session.execute(
                        select(TicketSlaTimer).where(
                            TicketSlaTimer.ticket_id == sync_ticket.id,
                            TicketSlaTimer.metric_type == "RESOLUTION",
                            TicketSlaTimer.is_deleted.is_(False),
                        )
                    ).scalar_one_or_none()
                    if resolution_timer and resolution_timer.status in {"RUNNING", "PAUSED"}:
                        sla_engine.mark_timer_met(
                            sync_session,
                            resolution_timer,
                            sync_ticket,
                            actor_id=actor.id,
                        )

            try:
                return sync_ticket_workflow.transition_status(
                    session,
                    ticket,
                    to_status_id=to_status_id,
                    performed_by=actor.id,
                    remark=remark,
                    has_permission=has_permission,
                    is_closed_status=target_status.is_closed,
                    on_status_changed=on_status_changed,
                    action=action,
                )
            except sync_ticket_workflow.InvalidStatusTransition as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(exc)
                ) from exc
            except sync_ticket_workflow.MissingTransitionPermission as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
                ) from exc

        transition = await self.db.run_sync(_run)
        return transition


async def commit_ticket_transaction(db: AsyncSession) -> None:
    """Commit a ticket mutation, its history, and its events atomically."""
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise