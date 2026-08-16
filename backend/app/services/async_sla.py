"""Async integration adapter for the synchronous SLA engine.

The legacy SLA engine intentionally remains synchronous and is also used by
unit tests. The live FastAPI application uses AsyncSession, so all engine
calls cross the boundary through AsyncSession.run_sync(). This gives the
engine a real SQLAlchemy Session bound to the same transaction/connection
without duplicating the SLA rules in a second implementation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, TicketSlaTimer
from app.services import sla_engine


async def match_and_start_sla(
    db: AsyncSession,
    ticket: Ticket,
    *,
    actor_id: UUID | None = None,
) -> list[TicketSlaTimer]:
    def _run(session):
        try:
            return sla_engine.match_and_start_sla(
                session, ticket, actor_id=actor_id
            )
        except sla_engine.NoMatchingSLAPolicy:
            # SLA is configurable; tickets may exist before an administrator
            # creates a matching policy. In that case the live flow succeeds
            # without timers rather than making SLA configuration a hard
            # prerequisite for ticket creation.
            return []

    return await db.run_sync(_run)


async def apply_status_pause_rules(
    db: AsyncSession,
    ticket: Ticket,
    *,
    new_status_id: UUID,
    actor_id: UUID | None = None,
    at: datetime | None = None,
) -> dict[str, list[TicketSlaTimer]]:
    return await db.run_sync(
        lambda session: sla_engine.apply_status_pause_rules(
            session,
            ticket,
            new_status_id=new_status_id,
            actor_id=actor_id,
            at=at,
        )
    )


async def pause_timer(
    db: AsyncSession,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    actor_id: UUID | None = None,
    reason: str | None = None,
) -> TicketSlaTimer:
    return await db.run_sync(
        lambda session: sla_engine.pause_sla_timer(
            session, timer, ticket, actor_id=actor_id, reason=reason
        )
    )


async def resume_timer(
    db: AsyncSession,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    actor_id: UUID | None = None,
) -> TicketSlaTimer:
    return await db.run_sync(
        lambda session: sla_engine.resume_sla_timer(
            session, timer, ticket, actor_id=actor_id
        )
    )


async def mark_timer_met(
    db: AsyncSession,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    actor_id: UUID | None = None,
) -> TicketSlaTimer:
    return await db.run_sync(
        lambda session: sla_engine.mark_timer_met(
            session, timer, ticket, actor_id=actor_id
        )
    )


async def cancel_timer(
    db: AsyncSession,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    actor_id: UUID | None = None,
    reason: str | None = None,
) -> TicketSlaTimer:
    return await db.run_sync(
        lambda session: sla_engine.cancel_sla_timer(
            session, timer, ticket, actor_id=actor_id, reason=reason
        )
    )


async def evaluate_breaches(
    db: AsyncSession,
    *,
    as_of: datetime | None = None,
    limit: int = 500,
) -> int:
    return len(
        await db.run_sync(
            lambda session: sla_engine.evaluate_breaches(
                session, as_of=as_of, limit=limit
            )
        )
    )


async def evaluate_escalations(
    db: AsyncSession,
    *,
    as_of: datetime | None = None,
    limit: int = 500,
) -> list[dict]:
    """Returns plain dicts (not ORM objects -- the sync Session inside
    `run_sync` closes before this returns, so ORM objects from it aren't
    safe to touch afterwards) describing each SLAEscalationEvent fired this
    sweep, for the caller to notify on via app.services.notification_engine.
    """

    def _run(session):
        events = sla_engine.evaluate_escalations(session, as_of=as_of, limit=limit)
        return [
            {
                "trigger_id": event.trigger_id,
                "ticket_id": event.ticket_id,
            }
            for event in events
        ]

    return await db.run_sync(_run)


async def run_scheduler_tick(db: AsyncSession, *, limit: int = 500) -> tuple[int, int]:
    """Run breach detection, SLA escalation evaluation, and notification
    dispatch for any escalations that just fired -- atomically for the
    detection/evaluation part; notification dispatch (and its own commit)
    happens after, so a delivery hiccup can't roll back the escalation
    event itself."""
    from app.db.models import SLAEscalationTrigger, Ticket
    from app.services import notification_engine

    breached = await evaluate_breaches(db, limit=limit)
    fired = await evaluate_escalations(db, limit=limit)
    await db.commit()

    for entry in fired:
        trigger = await db.get(SLAEscalationTrigger, entry["trigger_id"])
        ticket = await db.get(Ticket, entry["ticket_id"])
        if trigger is None or ticket is None or not trigger.channels:
            continue
        try:
            await notification_engine.dispatch_escalation(db, trigger=trigger, ticket=ticket)
        except Exception:  # noqa: BLE001 - one bad dispatch must not break the scheduler loop
            logging.getLogger(__name__).exception(
                "Escalation notification dispatch failed trigger=%s ticket=%s",
                entry["trigger_id"],
                entry["ticket_id"],
            )

    return breached, len(fired)
