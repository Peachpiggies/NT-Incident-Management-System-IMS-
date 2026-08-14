"""Service layer for ticket assignment, tier escalation, status transitions,
MDDR checkpoints, SLA evaluation, and comment/technical-update recording.

All functions take a live SQLAlchemy `Session` and an already-loaded `Ticket`
instance. They mutate the ORM objects, write the appropriate audit rows
(`TicketHistory`, `TicketAssignment`, `TicketEscalation`), and `session.flush()`
so generated IDs/timestamps are available -- but they never `commit()`.
Committing (and rolling back on error) is the caller's responsibility, so this
module composes cleanly inside a single request-scoped transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Ticket,
    TicketAssignment,
    TicketComment,
    TicketEscalation,
    TicketHistory,
    TicketStatusTransition,
)

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class TicketWorkflowError(Exception):
    """Base class for all ticket-workflow violations."""


class InvalidStatusTransition(TicketWorkflowError):
    """Raised when there is no active, configured edge between two statuses."""


class MissingTransitionPermission(TicketWorkflowError):
    """Raised when a status transition requires a permission the actor lacks."""


class InvalidTierTransition(TicketWorkflowError):
    """Raised when an escalation would skip a tier or move backwards."""


class InvalidCheckpointOrder(TicketWorkflowError):
    """Raised when an MDDR checkpoint would violate chronological ordering."""


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

ESCALATION_TYPES = {"FUNCTIONAL", "TECHNICAL"}

# Controlled vocabulary for *technical* escalation reasons -- why this needs
# a higher skill tier, not just a different team. SLA_RISK and MDDR_RISK
# deliberately line up with `Ticket.sla_breached` and the
# occurred/detected/diagnosed checkpoint fields: an escalation reasoned as
# one of those should generally correspond to that flag/checkpoint state,
# though this module doesn't cross-check it automatically (see note in
# escalate_ticket). Functional escalations are NOT constrained to this list
# -- they're about routing to the right team, not a skill gap.
TECHNICAL_REASON_CODES = {
    "SKILL_REQUIRED",
    "COMPLEXITY",
    "ACCESS_REQUIRED",
    "SYSTEM_DEPENDENCY",
    "UNRESOLVED_AFTER_ATTEMPTS",
    "SLA_RISK",
    "MDDR_RISK",
}

# MDDR: Occurred -> Detected -> Diagnosed -> Resolved. `closed_at` is a
# separate, post-resolution lifecycle event and is not part of the MDDR chain.
MDDR_CHECKPOINTS = ("occurred_at", "detected_at", "diagnosed_at", "resolved_at")

MAX_TIER = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_history(
    session: Session,
    ticket: Ticket,
    *,
    action: str,
    field: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    performed_by: UUID | None = None,
    remark: str | None = None,
) -> TicketHistory:
    entry = TicketHistory(
        ticket_id=ticket.id,
        action=action,
        field=field,
        old_value=old_value,
        new_value=new_value,
        performed_by=performed_by,
        remark=remark,
    )
    session.add(entry)
    return entry


def _touch(ticket: Ticket, *, actor_id: UUID | None) -> None:
    """Bump optimistic-lock version and updated_by on every mutation."""
    ticket.version += 1
    if actor_id is not None:
        ticket.updated_by = actor_id


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


def assign_ticket(
    session: Session,
    ticket: Ticket,
    *,
    assigned_to: UUID,
    actor_id: UUID | None,
    reason: str | None = None,
) -> TicketAssignment:
    """Assign (or reassign) a ticket to a user, recording full history.

    Safe to call whether or not the ticket currently has an assignee -- the
    first call is treated as an initial assignment (assigned_from=None).
    """
    if ticket.assigned_to == assigned_to:
        raise TicketWorkflowError("Ticket is already assigned to this user")

    assignment = TicketAssignment(
        ticket_id=ticket.id,
        assigned_from=ticket.assigned_to,
        assigned_to=assigned_to,
        reason=reason,
        created_by=actor_id,
    )
    session.add(assignment)

    _record_history(
        session,
        ticket,
        action="REASSIGN" if ticket.assigned_to else "ASSIGN",
        field="assigned_to",
        old_value=str(ticket.assigned_to) if ticket.assigned_to else None,
        new_value=str(assigned_to),
        performed_by=actor_id,
        remark=reason,
    )

    ticket.assigned_to = assigned_to
    _touch(ticket, actor_id=actor_id)
    session.flush()
    return assignment


# --------------------------------------------------------------------------
# Tier escalation (T1 -> T2 -> T3), with team ownership handoff
# --------------------------------------------------------------------------


def escalate_ticket(
    session: Session,
    ticket: Ticket,
    *,
    escalation_type: str,
    to_tier: int | None = None,
    to_department_id: UUID | None = None,
    reason_code: str | None = None,
    comment: str | None = None,
    escalated_by: UUID | None = None,
    allow_tier_skip: bool = False,
) -> TicketEscalation:
    """Escalate a ticket, either functionally or technically.

    FUNCTIONAL: re-routes to a more appropriate team (e.g. Helpdesk ->
    Billing). `to_department_id` is required. Tier does NOT need to change --
    it defaults to the current tier, and if a tier is given it only needs to
    be >= the current one (no "one step at a time" restriction, since this
    isn't a tier chain).

    TECHNICAL: moves the ticket up the expertise chain (T1 -> T2 -> T3).
    `to_tier` is required and must be exactly one tier higher unless
    `allow_tier_skip=True`. `to_department_id` is optional -- the ticket may
    stay with the same team at a higher tier, or hand off to that team's
    senior/manager tier.

    Either way, `ticket.department_id` (current owner) is kept in sync with
    `to_department_id` here -- this is the one place that happens.
    """
    if escalation_type not in ESCALATION_TYPES:
        raise TicketWorkflowError(
            f"Unknown escalation_type {escalation_type!r}; expected one of {sorted(ESCALATION_TYPES)}"
        )

    if escalation_type == "FUNCTIONAL":
        if to_department_id is None:
            raise TicketWorkflowError(
                "to_department_id is required for a functional escalation"
            )
        to_tier = ticket.current_tier if to_tier is None else to_tier
        if to_tier < ticket.current_tier or to_tier > MAX_TIER:
            raise InvalidTierTransition(
                f"to_tier ({to_tier}) must be between current_tier "
                f"({ticket.current_tier}) and {MAX_TIER} for a functional escalation"
            )
    else:  # TECHNICAL
        if to_tier is None:
            raise TicketWorkflowError("to_tier is required for a technical escalation")
        if to_tier > MAX_TIER:
            raise InvalidTierTransition(f"Cannot escalate past tier {MAX_TIER}")
        if to_tier <= ticket.current_tier:
            raise InvalidTierTransition(
                f"to_tier ({to_tier}) must be higher than current_tier "
                f"({ticket.current_tier}) for a technical escalation"
            )
        if not allow_tier_skip and to_tier != ticket.current_tier + 1:
            raise InvalidTierTransition(
                f"Technical escalation must move exactly one tier at a time "
                f"(from {ticket.current_tier} to {ticket.current_tier + 1}), got {to_tier}"
            )
        if reason_code not in TECHNICAL_REASON_CODES:
            raise TicketWorkflowError(
                f"reason_code must be one of {sorted(TECHNICAL_REASON_CODES)} "
                f"for a technical escalation, got {reason_code!r}"
            )

    from_department_id = ticket.department_id
    from_user_id = ticket.assigned_to
    escalation = TicketEscalation(
        ticket_id=ticket.id,
        escalation_type=escalation_type,
        from_tier=ticket.current_tier,
        to_tier=to_tier,
        from_department_id=from_department_id,
        to_department_id=to_department_id or from_department_id,
        from_user_id=from_user_id,
        reason_code=reason_code,
        comment=comment,
        escalated_by=escalated_by,
        created_by=escalated_by,
    )
    session.add(escalation)

    _record_history(
        session,
        ticket,
        action="ESCALATE_FUNCTIONAL" if escalation_type == "FUNCTIONAL" else "ESCALATE_TECHNICAL",
        field="current_tier",
        old_value=str(ticket.current_tier),
        new_value=str(to_tier),
        performed_by=escalated_by,
        remark=reason_code or comment,
    )

    previous_tier = ticket.current_tier
    ticket.current_tier = to_tier
    if to_department_id and to_department_id != from_department_id:
        _record_history(
            session,
            ticket,
            action="REASSIGN_TEAM",
            field="department_id",
            old_value=str(from_department_id) if from_department_id else None,
            new_value=str(to_department_id),
            performed_by=escalated_by,
            remark=f"{escalation_type} escalation T{previous_tier}->T{to_tier}",
        )
        ticket.department_id = to_department_id
        # New team, new investigation queue: clear the previous assignee so
        # the ticket surfaces as unassigned in the receiving team's queue.
        ticket.assigned_to = None

    _touch(ticket, actor_id=escalated_by)
    session.flush()
    return escalation


# --------------------------------------------------------------------------
# Status transitions (administrator-configured state machine)
# --------------------------------------------------------------------------


def transition_status(
    session: Session,
    ticket: Ticket,
    *,
    to_status_id: UUID,
    performed_by: UUID | None,
    remark: str | None = None,
    has_permission: Callable[[str], bool] | None = None,
    is_closed_status: bool = False,
) -> Ticket:
    """Move a ticket to a new status, enforcing the configured transition graph.

    `has_permission`, if given, is called with the transition's
    `required_permission` code (when set) and must return True/False. Pass it
    from wherever your auth/permission checking already lives -- this module
    intentionally has no opinion on how permissions are resolved.
    """
    edge = session.execute(
        select(TicketStatusTransition).where(
            TicketStatusTransition.from_status_id == ticket.status_id,
            TicketStatusTransition.to_status_id == to_status_id,
            TicketStatusTransition.is_active.is_(True),
            TicketStatusTransition.is_deleted.is_(False),
        )
    ).scalar_one_or_none()

    if edge is None:
        raise InvalidStatusTransition(
            f"No active transition configured from {ticket.status_id} to {to_status_id}"
        )
    if edge.required_permission and has_permission is not None:
        if not has_permission(edge.required_permission):
            raise MissingTransitionPermission(
                f"Missing required permission: {edge.required_permission}"
            )

    _record_history(
        session,
        ticket,
        action="STATUS_CHANGE",
        field="status_id",
        old_value=str(ticket.status_id),
        new_value=str(to_status_id),
        performed_by=performed_by,
        remark=remark,
    )

    ticket.status_id = to_status_id
    if is_closed_status:
        ticket.closed_at = ticket.closed_at or _utcnow()

    _touch(ticket, actor_id=performed_by)
    session.flush()
    return ticket


# --------------------------------------------------------------------------
# MDDR checkpoints
# --------------------------------------------------------------------------


def record_checkpoint(
    session: Session,
    ticket: Ticket,
    *,
    checkpoint: str,
    at: datetime | None = None,
    performed_by: UUID | None = None,
) -> Ticket:
    """Record one MDDR checkpoint (occurred/detected/diagnosed/resolved),
    enforcing that checkpoints stay chronologically consistent with each
    other regardless of the order they're reported in.
    """
    if checkpoint not in MDDR_CHECKPOINTS:
        raise TicketWorkflowError(
            f"Unknown checkpoint {checkpoint!r}; expected one of {MDDR_CHECKPOINTS}"
        )
    at = at or _utcnow()
    idx = MDDR_CHECKPOINTS.index(checkpoint)

    for earlier in MDDR_CHECKPOINTS[:idx]:
        earlier_value = getattr(ticket, earlier)
        if earlier_value is not None and at < earlier_value:
            raise InvalidCheckpointOrder(
                f"{checkpoint}={at.isoformat()} is before {earlier}={earlier_value.isoformat()}"
            )
    for later in MDDR_CHECKPOINTS[idx + 1 :]:
        later_value = getattr(ticket, later)
        if later_value is not None and at > later_value:
            raise InvalidCheckpointOrder(
                f"{checkpoint}={at.isoformat()} is after {later}={later_value.isoformat()}"
            )

    old_value = getattr(ticket, checkpoint)
    _record_history(
        session,
        ticket,
        action="MDDR_CHECKPOINT",
        field=checkpoint,
        old_value=old_value.isoformat() if old_value else None,
        new_value=at.isoformat(),
        performed_by=performed_by,
    )
    setattr(ticket, checkpoint, at)
    _touch(ticket, actor_id=performed_by)
    session.flush()
    return ticket


# --------------------------------------------------------------------------
# SLA evaluation
# --------------------------------------------------------------------------


def evaluate_sla(
    session: Session,
    ticket: Ticket,
    *,
    as_of: datetime | None = None,
    performed_by: UUID | None = None,
) -> bool:
    """Recompute `ticket.sla_breached` against `due_at`.

    Once a ticket is resolved or closed the breach state is frozen (evaluated
    against `resolved_at`/`closed_at` rather than "now"), so a slow-to-close
    ticket doesn't keep flipping breached after the work is actually done.
    """
    if ticket.due_at is None:
        return ticket.sla_breached

    reference = ticket.resolved_at or ticket.closed_at or as_of or _utcnow()
    breached = reference > ticket.due_at

    if breached != ticket.sla_breached:
        _record_history(
            session,
            ticket,
            action="SLA_EVALUATION",
            field="sla_breached",
            old_value=str(ticket.sla_breached),
            new_value=str(breached),
            performed_by=performed_by,
        )
        ticket.sla_breached = breached
        _touch(ticket, actor_id=performed_by)
        session.flush()

    return ticket.sla_breached


# --------------------------------------------------------------------------
# Notes / technical updates (investigation timeline)
# --------------------------------------------------------------------------


def add_update(
    session: Session,
    ticket: Ticket,
    *,
    user_id: UUID,
    comment: str,
    update_type: str = "NOTE",
    is_internal: bool = True,
) -> TicketComment:
    """Append an internal note or a technical/investigation update.

    `update_type="TECHNICAL_UPDATE"` entries are what the T2/T3 investigation
    timeline filters on (see `ix_ticket_comments_ticket_update_type`);
    `"NOTE"` is a general internal note. Both are stored in `ticket_comments`.
    """
    if update_type not in {"NOTE", "TECHNICAL_UPDATE"}:
        raise TicketWorkflowError(f"Unknown update_type {update_type!r}")

    entry = TicketComment(
        ticket_id=ticket.id,
        user_id=user_id,
        comment=comment,
        is_internal=is_internal,
        update_type=update_type,
        created_by=user_id,
    )
    session.add(entry)
    session.flush()
    return entry