"""Service layer for SLA policy matching and per-ticket timer lifecycle.

Mirrors app/services/ticket_workflow.py's conventions: every function takes
a live SQLAlchemy `Session` and already-loaded ORM instance(s), mutates
them, writes a `TicketHistory` audit row where the mutation is
ticket-visible, and `session.flush()`es -- but never `commit()`s. Committing
(and rolling back on error) is the caller's responsibility.

Three halves:
  - Policy matching: `match_sla_policy` picks the best-fit SLAPolicy for a
    ticket's department/category/subcategory/service/priority. Lower
    `match_priority` wins; ties broken by whichever policy is more specific
    (more non-null filters), then by creation order for determinism.
  - Timer lifecycle: `start_sla_timers` creates one TicketSlaTimer per
    RESPONSE/RESOLUTION target on the matched policy; `pause_sla_timer` /
    `resume_sla_timer` track paused time and push `due_at` out by however
    long the pause lasted; `mark_timer_met` / `evaluate_timer_breach` /
    `cancel_sla_timer` close a timer out; `evaluate_breaches` sweeps every
    RUNNING timer past due.
  - Escalation: `evaluate_escalations` sweeps timers approaching (WARNING)
    or past (BREACH) their target and fires any matching, not-yet-fired
    SLAEscalationTrigger for that policy/metric_type, recording an
    SLAEscalationEvent per firing so the same trigger never fires twice for
    the same timer.

Business-hours calendars aren't modeled yet (SLAPolicy.business_hours_only
exists as a flag with no calendar table behind it). `start_sla_timers`
takes an optional `resolve_due_at` callback so a calendar can be plugged in
later without changing this module's signature -- same dependency-injection
shape as `transition_status`'s `has_permission` callback in
ticket_workflow.py. The default just adds calendar minutes.

For RESOLUTION timers specifically, breaching also flips `ticket.sla_breached`
to keep the legacy flat flag (and `ticket_workflow.evaluate_sla`, which reads
`ticket.due_at`/`ticket.sla_breached`) in sync with the new per-metric
timers. RESPONSE timers have no ticket-level flag to sync -- their state
lives entirely on the TicketSlaTimer row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    SLAEscalationEvent,
    SLAEscalationTrigger,
    SLAPauseRule,
    SLAPolicy,
    SLATarget,
    Ticket,
    TicketHistory,
    TicketSlaTimer,
)

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class SLAEngineError(Exception):
    """Base class for all SLA-engine violations."""


class NoMatchingSLAPolicy(SLAEngineError):
    """Raised when no active SLAPolicy matches a ticket's attributes."""


class InvalidTimerTransition(SLAEngineError):
    """Raised when a pause/resume/met call doesn't fit the timer's current status."""


# --------------------------------------------------------------------------
# Helpers (duplicated from ticket_workflow.py rather than imported, matching
# this codebase's existing preference for per-module self-containment -- see
# the audit-column duplication across the 0005/0006/0007 migrations)
# --------------------------------------------------------------------------


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
    performed_by=None,
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


def _touch_ticket(ticket: Ticket, *, actor_id=None) -> None:
    ticket.version += 1
    if actor_id is not None:
        ticket.updated_by = actor_id


def _default_resolve_due_at(
    started_at: datetime, target_minutes: int, business_hours_only: bool
) -> datetime:
    # TODO: business_hours_only is inert until a business-hours calendar
    # table exists. Pass a resolve_due_at callback into start_sla_timers to
    # override this once one does.
    return started_at + timedelta(minutes=target_minutes)


def _apply_pause_resume_math(timer: TicketSlaTimer, at: datetime) -> None:
    """Fold the just-ended pause window into total_paused_seconds and push
    due_at out by the same amount. Shared by resume_sla_timer and
    mark_timer_met (which must close out a pending pause before completing).
    """
    if timer.paused_at is None:
        return
    elapsed = (at - timer.paused_at).total_seconds()
    if elapsed > 0:
        timer.total_paused_seconds += int(elapsed)
        timer.due_at = timer.due_at + timedelta(seconds=elapsed)
    timer.paused_at = None


def _elapsed_percent(timer: TicketSlaTimer, at: datetime) -> float:
    """% of the timer's target duration that has actually elapsed, with
    paused time excluded -- mirrors the pause-aware math in
    _apply_pause_resume_math rather than just comparing `at` to `due_at`
    (which would count paused time against the ticket).
    """
    target_seconds = timer.target_minutes * 60
    if target_seconds <= 0:
        return 0.0
    elapsed_seconds = (at - timer.started_at).total_seconds() - timer.total_paused_seconds
    return max(0.0, elapsed_seconds / target_seconds * 100)


# --------------------------------------------------------------------------
# Policy matching
# --------------------------------------------------------------------------


def match_sla_policy(session: Session, ticket: Ticket) -> SLAPolicy | None:
    """Return the best-fit active SLAPolicy for this ticket, or None.

    A policy matches when every one of its filter columns is either NULL
    ("matches any") or equal to the ticket's corresponding value. Among
    matches, the lowest `match_priority` wins; ties go to the more specific
    policy (more non-null filters), then to whichever was created first.
    """
    specificity = (
        case((SLAPolicy.department_id.isnot(None), 1), else_=0)
        + case((SLAPolicy.category_id.isnot(None), 1), else_=0)
        + case((SLAPolicy.subcategory_id.isnot(None), 1), else_=0)
        + case((SLAPolicy.service_id.isnot(None), 1), else_=0)
        + case((SLAPolicy.priority_id.isnot(None), 1), else_=0)
    )

    stmt = (
        select(SLAPolicy)
        .where(
            SLAPolicy.is_active.is_(True),
            SLAPolicy.is_deleted.is_(False),
            or_(
                SLAPolicy.department_id.is_(None),
                SLAPolicy.department_id == ticket.department_id,
            ),
            or_(
                SLAPolicy.category_id.is_(None),
                SLAPolicy.category_id == ticket.category_id,
            ),
            or_(
                SLAPolicy.subcategory_id.is_(None),
                SLAPolicy.subcategory_id == ticket.subcategory_id,
            ),
            or_(
                SLAPolicy.service_id.is_(None),
                SLAPolicy.service_id == ticket.service_id,
            ),
            or_(
                SLAPolicy.priority_id.is_(None),
                SLAPolicy.priority_id == ticket.priority_id,
            ),
        )
        .order_by(
            SLAPolicy.match_priority.asc(),
            specificity.desc(),
            SLAPolicy.created_at.asc(),
        )
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


# --------------------------------------------------------------------------
# Timer start
# --------------------------------------------------------------------------


def start_sla_timers(
    session: Session,
    ticket: Ticket,
    policy: SLAPolicy,
    *,
    started_at: datetime | None = None,
    actor_id=None,
    resolve_due_at: Callable[[datetime, int, bool], datetime] | None = None,
) -> list[TicketSlaTimer]:
    """Create one TicketSlaTimer per RESPONSE/RESOLUTION target on `policy`.

    Idempotent per metric_type: a metric that already has a (non-deleted)
    timer on this ticket is skipped rather than duplicated or overwritten --
    safe to call again after a reclassification without clobbering a timer
    already in flight. Returns only the newly-created timers.
    """
    started_at = started_at or _utcnow()
    resolve_due_at = resolve_due_at or _default_resolve_due_at

    existing_metrics = set(
        session.execute(
            select(TicketSlaTimer.metric_type).where(
                TicketSlaTimer.ticket_id == ticket.id,
                TicketSlaTimer.is_deleted.is_(False),
            )
        ).scalars()
    )

    targets = (
        session.execute(
            select(SLATarget).where(
                SLATarget.policy_id == policy.id,
                SLATarget.is_deleted.is_(False),
            )
        )
        .scalars()
        .all()
    )

    created: list[TicketSlaTimer] = []
    for target in targets:
        if target.metric_type in existing_metrics:
            continue
        due_at = resolve_due_at(started_at, target.target_minutes, policy.business_hours_only)
        timer = TicketSlaTimer(
            ticket_id=ticket.id,
            policy_id=policy.id,
            metric_type=target.metric_type,
            target_minutes=target.target_minutes,
            started_at=started_at,
            due_at=due_at,
            status="RUNNING",
            created_by=actor_id,
        )
        session.add(timer)
        _record_history(
            session,
            ticket,
            action="SLA_TIMER_STARTED",
            field=target.metric_type,
            new_value=due_at.isoformat(),
            performed_by=actor_id,
            remark=f"policy={policy.code}",
        )
        created.append(timer)

    if created:
        session.flush()
    return created


def match_and_start_sla(
    session: Session,
    ticket: Ticket,
    *,
    actor_id=None,
    resolve_due_at: Callable[[datetime, int, bool], datetime] | None = None,
) -> list[TicketSlaTimer]:
    """Convenience entry point for ticket creation: match a policy and start
    its timers in one call. Raises NoMatchingSLAPolicy if nothing matches --
    callers that want to allow SLA-less tickets should call
    `match_sla_policy` directly instead and handle a None result themselves.
    """
    policy = match_sla_policy(session, ticket)
    if policy is None:
        raise NoMatchingSLAPolicy(
            f"No active SLA policy matches ticket {ticket.id} "
            f"(department={ticket.department_id}, category={ticket.category_id}, "
            f"priority={ticket.priority_id})"
        )
    return start_sla_timers(
        session, ticket, policy, actor_id=actor_id, resolve_due_at=resolve_due_at
    )


# --------------------------------------------------------------------------
# Pause / resume
# --------------------------------------------------------------------------


def pause_sla_timer(
    session: Session,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    at: datetime | None = None,
    actor_id=None,
    reason: str | None = None,
) -> TicketSlaTimer:
    """Pause a running timer (e.g. waiting on the customer)."""
    if timer.status != "RUNNING":
        raise InvalidTimerTransition(
            f"Cannot pause a {timer.metric_type} timer in status {timer.status!r}; must be RUNNING"
        )
    at = at or _utcnow()
    timer.paused_at = at
    timer.status = "PAUSED"
    _record_history(
        session,
        ticket,
        action="SLA_TIMER_PAUSED",
        field=timer.metric_type,
        performed_by=actor_id,
        remark=reason,
    )
    session.flush()
    return timer


def resume_sla_timer(
    session: Session,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    at: datetime | None = None,
    actor_id=None,
) -> TicketSlaTimer:
    """Resume a paused timer, pushing due_at out by however long it was paused."""
    if timer.status != "PAUSED":
        raise InvalidTimerTransition(
            f"Cannot resume a {timer.metric_type} timer in status {timer.status!r}; must be PAUSED"
        )
    at = at or _utcnow()
    _apply_pause_resume_math(timer, at)
    timer.status = "RUNNING"
    _record_history(
        session,
        ticket,
        action="SLA_TIMER_RESUMED",
        field=timer.metric_type,
        new_value=timer.due_at.isoformat(),
        performed_by=actor_id,
    )
    session.flush()
    return timer


# --------------------------------------------------------------------------
# Automatic pause/resume (status-driven)
# --------------------------------------------------------------------------


def apply_status_pause_rules(
    session: Session,
    ticket: Ticket,
    *,
    new_status_id,
    at: datetime | None = None,
    actor_id=None,
) -> dict[str, list[TicketSlaTimer]]:
    """Pause or resume this ticket's timers based on the SLAPauseRule table,
    given the status the ticket just transitioned into.

    Call this *after* the status change is committed (or at least staged),
    passing the new status_id -- this module has no opinion on how the
    transition itself is validated (see ticket_workflow.transition_status).

    For every non-terminal timer on the ticket:
      - If an active SLAPauseRule exists for (timer.policy_id, new_status_id)
        and the timer is RUNNING, pause it and stamp
        `auto_paused_status_id = new_status_id` so a later resume knows this
        pause was rule-driven, not manual.
      - If the timer is PAUSED, was paused by *this* mechanism
        (`auto_paused_status_id is not None`), and no active rule matches
        the new status, resume it and clear the stamp.
      - A timer already PAUSED with `auto_paused_status_id is None` (i.e.
        paused manually via `pause_sla_timer`) is left alone regardless of
        the new status -- an unrelated status change should never silently
        resume a timer a person paused on purpose. It stays paused until
        someone calls `resume_sla_timer` directly.
      - MET/BREACHED/CANCELLED timers are terminal and skipped.

    A ticket can have multiple timers (RESPONSE, RESOLUTION) potentially
    against different policies if it was reclassified after RESPONSE
    started; each timer is checked against its own `policy_id`, not the
    ticket's current policy as a whole.

    Returns {"paused": [...], "resumed": [...]}.
    """
    at = at or _utcnow()
    paused: list[TicketSlaTimer] = []
    resumed: list[TicketSlaTimer] = []

    timers = (
        session.execute(
            select(TicketSlaTimer).where(
                TicketSlaTimer.ticket_id == ticket.id,
                TicketSlaTimer.is_deleted.is_(False),
                TicketSlaTimer.status.in_(["RUNNING", "PAUSED"]),
            )
        )
        .scalars()
        .all()
    )
    if not timers:
        return {"paused": paused, "resumed": resumed}

    # One query per distinct policy among this ticket's timers rather than
    # per timer -- usually 1, at most 2 (RESPONSE/RESOLUTION rarely diverge
    # in policy, but nothing here assumes they can't).
    policy_ids = {timer.policy_id for timer in timers}
    rule_by_policy: dict = {}
    for policy_id in policy_ids:
        rule_by_policy[policy_id] = session.execute(
            select(SLAPauseRule.id).where(
                SLAPauseRule.policy_id == policy_id,
                SLAPauseRule.status_id == new_status_id,
                SLAPauseRule.is_active.is_(True),
                SLAPauseRule.is_deleted.is_(False),
            )
        ).first()

    for timer in timers:
        rule_matches = rule_by_policy.get(timer.policy_id) is not None

        if rule_matches and timer.status == "RUNNING":
            pause_sla_timer(
                session,
                timer,
                ticket,
                at=at,
                actor_id=actor_id,
                reason="Auto-paused by SLA pause rule",
            )
            timer.auto_paused_status_id = new_status_id
            paused.append(timer)
        elif (
            not rule_matches
            and timer.status == "PAUSED"
            and timer.auto_paused_status_id is not None
        ):
            resume_sla_timer(session, timer, ticket, at=at, actor_id=actor_id)
            timer.auto_paused_status_id = None
            resumed.append(timer)
        # else: RUNNING with no matching rule (no-op), or PAUSED-manually
        # (left alone), or PAUSED-by-rule but the new status still matches
        # a rule for this policy (stays paused, nothing to do).

    if paused or resumed:
        session.flush()
    return {"paused": paused, "resumed": resumed}


# --------------------------------------------------------------------------
# Completion / breach
# --------------------------------------------------------------------------


def mark_timer_met(
    session: Session,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    at: datetime | None = None,
    actor_id=None,
) -> TicketSlaTimer:
    """Mark a timer met (e.g. first response sent, ticket resolved).

    If the timer is currently paused, the pending pause window is folded in
    first so total_paused_seconds/due_at stay accurate even though the
    timer never explicitly resumed.
    """
    if timer.status in {"MET", "BREACHED", "CANCELLED"}:
        raise InvalidTimerTransition(
            f"{timer.metric_type} timer is already terminal (status={timer.status})"
        )
    at = at or _utcnow()
    if timer.status == "PAUSED":
        _apply_pause_resume_math(timer, at)
    timer.status = "MET"
    timer.met_at = at
    _record_history(
        session,
        ticket,
        action="SLA_TIMER_MET",
        field=timer.metric_type,
        new_value=at.isoformat(),
        performed_by=actor_id,
    )
    session.flush()
    return timer


def evaluate_timer_breach(
    session: Session,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    as_of: datetime | None = None,
    actor_id=None,
) -> bool:
    """Check a RUNNING timer against due_at and flip it to BREACHED if past due.

    Only RUNNING timers are evaluated: a PAUSED timer's due_at is frozen
    until it resumes, so comparing it against "now" would misreport a
    legitimate pause as a breach. MET/BREACHED/CANCELLED are already
    terminal and are returned as-is.

    For a RESOLUTION timer, breaching also flips `ticket.sla_breached` so
    the legacy flat flag (and anything still reading it, e.g.
    ticket_workflow.evaluate_sla) stays in sync. RESPONSE timers have no
    ticket-level flag to sync.
    """
    if timer.status != "RUNNING":
        return timer.status == "BREACHED"

    reference = as_of or _utcnow()
    if reference <= timer.due_at:
        return False

    timer.status = "BREACHED"
    timer.breached_at = reference
    _record_history(
        session,
        ticket,
        action="SLA_TIMER_BREACHED",
        field=timer.metric_type,
        new_value=reference.isoformat(),
        performed_by=actor_id,
    )

    if timer.metric_type == "RESOLUTION" and not ticket.sla_breached:
        ticket.sla_breached = True
        _touch_ticket(ticket, actor_id=actor_id)

    session.flush()
    return True


def evaluate_breaches(
    session: Session,
    *,
    as_of: datetime | None = None,
    limit: int = 500,
) -> list[TicketSlaTimer]:
    """Sweep every RUNNING timer past due and flip it to BREACHED.

    Meant to be called on a schedule (cron / Celery beat) rather than
    per-request -- `evaluate_timer_breach` above only checks one timer you
    already have loaded, and nothing else in this module walks the table.
    Loads each timer's Ticket to satisfy `evaluate_timer_breach`'s
    signature (and to flip `ticket.sla_breached` on RESOLUTION breaches),
    so this is one query plus one flush per breached timer, not one flush
    for the whole batch -- `evaluate_timer_breach` already flushes per-call,
    and splitting the sweep into per-timer transactions means one bad
    ticket (e.g. a stale FK) fails that timer without losing the rest of
    the batch. Caller still owns the commit, same as everywhere else in
    this module.

    `limit` caps how many timers a single sweep processes, so a large
    backlog (e.g. after a scheduler outage) gets drained over several runs
    instead of one call trying to do it all and holding the session open
    for too long. Returns only the timers that were actually breached in
    this call, not the full past-due set that was considered.
    """
    reference = as_of or _utcnow()

    stmt = (
        select(TicketSlaTimer)
        .where(
            TicketSlaTimer.status == "RUNNING",
            TicketSlaTimer.due_at < reference,
            TicketSlaTimer.is_deleted.is_(False),
        )
        .order_by(TicketSlaTimer.due_at.asc())
        .limit(limit)
    )
    due_timers = session.execute(stmt).scalars().all()

    breached: list[TicketSlaTimer] = []
    for timer in due_timers:
        ticket = session.get(Ticket, timer.ticket_id)
        if ticket is None:
            # Orphaned timer (ticket hard-deleted out from under it). Skip
            # rather than raise -- evaluate_timer_breach needs a Ticket to
            # write history/sla_breached against, and one bad row shouldn't
            # sink the whole sweep.
            continue
        if evaluate_timer_breach(session, timer, ticket, as_of=reference):
            breached.append(timer)

    return breached


# --------------------------------------------------------------------------
# Cancellation
# --------------------------------------------------------------------------


def cancel_sla_timer(
    session: Session,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    at: datetime | None = None,
    actor_id=None,
    reason: str | None = None,
) -> TicketSlaTimer:
    """Cancel a timer that will never be met or breached (e.g. the ticket
    was closed as a duplicate, merged, or deleted before this metric
    resolved).

    Valid from RUNNING or PAUSED -- MET/BREACHED/CANCELLED are already
    terminal. Cancelling from PAUSED does not fold in pause math the way
    resume/mark_timer_met do, since a cancelled timer's due_at is no
    longer meaningful; total_paused_seconds is left as whatever it already
    accrued for audit purposes.
    """
    if timer.status not in {"RUNNING", "PAUSED"}:
        raise InvalidTimerTransition(
            f"Cannot cancel a {timer.metric_type} timer in status {timer.status!r}; "
            "must be RUNNING or PAUSED"
        )
    at = at or _utcnow()
    timer.status = "CANCELLED"
    timer.cancelled_at = at
    timer.paused_at = None
    _record_history(
        session,
        ticket,
        action="SLA_TIMER_CANCELLED",
        field=timer.metric_type,
        performed_by=actor_id,
        remark=reason,
    )
    session.flush()
    return timer


# --------------------------------------------------------------------------
# Escalation
# --------------------------------------------------------------------------


def _matching_triggers(
    session: Session, policy_id, trigger_on: str, metric_type: str
) -> list[SLAEscalationTrigger]:
    stmt = select(SLAEscalationTrigger).where(
        SLAEscalationTrigger.policy_id == policy_id,
        SLAEscalationTrigger.trigger_on == trigger_on,
        SLAEscalationTrigger.is_active.is_(True),
        or_(
            SLAEscalationTrigger.metric_type.is_(None),
            SLAEscalationTrigger.metric_type == metric_type,
        ),
    )
    return session.execute(stmt).scalars().all()


def _already_fired(session: Session, trigger_id, timer_id) -> bool:
    stmt = select(SLAEscalationEvent.id).where(
        SLAEscalationEvent.trigger_id == trigger_id,
        SLAEscalationEvent.timer_id == timer_id,
    )
    return session.execute(stmt).first() is not None


def _fire_trigger(
    session: Session,
    trigger: SLAEscalationTrigger,
    timer: TicketSlaTimer,
    ticket: Ticket,
    *,
    at: datetime,
    notify: Callable[[TicketSlaTimer, SLAEscalationTrigger], None] | None,
) -> SLAEscalationEvent:
    event = SLAEscalationEvent(
        trigger_id=trigger.id,
        timer_id=timer.id,
        ticket_id=ticket.id,
        trigger_on=trigger.trigger_on,
        fired_at=at,
    )
    session.add(event)
    _record_history(
        session,
        ticket,
        action="SLA_ESCALATION_FIRED",
        field=timer.metric_type,
        new_value=trigger.trigger_on,
        remark=f"trigger={trigger.id}",
    )
    if notify is not None:
        # Left to the caller rather than sent from here, same
        # dependency-injection shape as start_sla_timers' resolve_due_at --
        # this module doesn't know how EscalationNotificationCreate rows
        # get dispatched (email/in-app/websocket), only that a trigger
        # fired and who/what it should reach.
        notify(timer, trigger)
    return event


def evaluate_escalations(
    session: Session,
    *,
    as_of: datetime | None = None,
    limit: int = 500,
    notify: Callable[[TicketSlaTimer, SLAEscalationTrigger], None] | None = None,
) -> list[SLAEscalationEvent]:
    """Sweep timers approaching or past their target and fire any matching,
    not-yet-fired SLAEscalationTrigger.

    Two independent passes, mirroring the two `SLAEscalationTriggerOn`
    values:
      - WARNING: RUNNING timers whose elapsed time (pause-excluded, via
        `_elapsed_percent`) has crossed their target's
        `warning_threshold_pct`. A timer can only warn once it's actually
        RUNNING -- a PAUSED timer's elapsed time is frozen, same reasoning
        as `evaluate_timer_breach` only evaluating RUNNING timers.
      - BREACH: timers already in BREACHED status (i.e. after
        `evaluate_timer_breach`/`evaluate_breaches` has run).

    A trigger fires at most once per timer: `_already_fired` checks
    SLAEscalationEvent before calling `_fire_trigger`, so re-running this
    sweep (e.g. every few minutes via the same scheduler that drives
    `evaluate_breaches`) doesn't re-notify anyone for a threshold already
    crossed. `limit` caps timers considered per pass, same reasoning as
    `evaluate_breaches`: drain a large backlog over several runs rather
    than holding the session open for one giant sweep.

    Does not call `evaluate_breaches` itself -- run that first (or trust an
    earlier scheduled run already flipped the relevant timers to BREACHED)
    so the BREACH pass here has something to find. Splitting them keeps
    each function doing one thing and lets a caller run breach detection
    more frequently than escalation notification if they want to.
    """
    reference = as_of or _utcnow()
    fired: list[SLAEscalationEvent] = []

    # -- WARNING pass -------------------------------------------------
    running_stmt = (
        select(TicketSlaTimer)
        .where(
            TicketSlaTimer.status == "RUNNING",
            TicketSlaTimer.is_deleted.is_(False),
        )
        .order_by(TicketSlaTimer.due_at.asc())
        .limit(limit)
    )
    for timer in session.execute(running_stmt).scalars().all():
        target = session.execute(
            select(SLATarget).where(
                SLATarget.policy_id == timer.policy_id,
                SLATarget.metric_type == timer.metric_type,
                SLATarget.is_deleted.is_(False),
            )
        ).scalars().first()
        if target is None:
            continue
        if _elapsed_percent(timer, reference) < target.warning_threshold_pct:
            continue

        ticket = session.get(Ticket, timer.ticket_id)
        if ticket is None:
            continue

        for trigger in _matching_triggers(
            session, timer.policy_id, "WARNING", timer.metric_type
        ):
            if _already_fired(session, trigger.id, timer.id):
                continue
            fired.append(
                _fire_trigger(session, trigger, timer, ticket, at=reference, notify=notify)
            )

    # -- BREACH pass ----------------------------------------------------
    breached_stmt = (
        select(TicketSlaTimer)
        .where(
            TicketSlaTimer.status == "BREACHED",
            TicketSlaTimer.is_deleted.is_(False),
        )
        .order_by(TicketSlaTimer.breached_at.asc())
        .limit(limit)
    )
    for timer in session.execute(breached_stmt).scalars().all():
        ticket = session.get(Ticket, timer.ticket_id)
        if ticket is None:
            continue

        for trigger in _matching_triggers(
            session, timer.policy_id, "BREACH", timer.metric_type
        ):
            if _already_fired(session, trigger.id, timer.id):
                continue
            fired.append(
                _fire_trigger(session, trigger, timer, ticket, at=reference, notify=notify)
            )

    if fired:
        session.flush()
    return fired