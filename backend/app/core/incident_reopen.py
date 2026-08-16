"""
Incident Management - Reopen Flow (4.6)
=========================================

Implements the RESOLVED -> REOPENED -> IN_PROGRESS cycle described in the
NT-IMS incident flow, with the following corrections vs. a naive
"Reopen -> Submit Incident Ticket (start over)" design:

  1. Reopen routes back to the TEAM/TIER that produced the resolution
     (not back through Validation / Duplicate Detection / Auto
     Classification / Assignment Engine).
  2. reopen_count is tracked and capped; exceeding the cap auto-escalates
     to Tier 3 (Manager) instead of looping forever.
  3. SLA / MDDR is recalculated (shortened) on each reopen cycle.
  4. Full audit trail is kept: reopen_reason, reopened_by, reopened_at,
     previous_resolution, reopen_count.

No third-party dependencies - stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

class TicketState(str, Enum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"


class Tier(str, Enum):
    TIER_1 = "TIER_1_HELPDESK"
    TIER_2 = "TIER_2_SPECIALIST"
    TIER_3 = "TIER_3_MANAGER"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ReopenPolicy:
    """Business rules for how reopen affects SLA and routing."""

    max_reopen_count: int = 3          # after this many reopens -> force escalate to Tier 3
    base_sla_hours: int = 24           # SLA given on first resolution attempt
    sla_shrink_factor: float = 0.5     # each reopen cycle shrinks the SLA window
    min_sla_hours: int = 2             # floor so SLA never goes to 0


# ---------------------------------------------------------------------------
# Audit record for a single reopen event
# ---------------------------------------------------------------------------

@dataclass
class ReopenEvent:
    reopen_reason: str
    reopened_by: str
    reopened_at: datetime
    previous_resolution: str
    reopen_count_after: int
    new_sla_deadline: datetime
    routed_to_tier: Tier


# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------

@dataclass
class IncidentTicket:
    ticket_id: str
    state: TicketState = TicketState.NEW

    # who currently owns the resolution work
    current_tier: Tier | None = None
    current_agent: str | None = None

    # who most recently RESOLVED it (needed so Reopen can route back to them)
    resolved_by_tier: Tier | None = None
    resolved_by_agent: str | None = None
    last_resolution_note: str | None = None
    resolved_at: datetime | None = None

    # reopen bookkeeping
    reopen_count: int = 0
    reopen_history: list[ReopenEvent] = field(default_factory=list)

    # SLA
    sla_deadline: datetime | None = None

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def assign(self, tier: Tier, agent: str, policy: ReopenPolicy) -> None:
        self.current_tier = tier
        self.current_agent = agent
        self.state = TicketState.ASSIGNED
        if self.sla_deadline is None:
            self.sla_deadline = datetime.now(timezone.utc) + timedelta(hours=policy.base_sla_hours)

    def start_progress(self) -> None:
        if self.state not in (TicketState.ASSIGNED, TicketState.REOPENED):
            raise ValueError(f"Cannot start progress from state {self.state}")
        self.state = TicketState.IN_PROGRESS

    def resolve(self, resolution_note: str) -> None:
        if self.state != TicketState.IN_PROGRESS:
            raise ValueError(f"Cannot resolve from state {self.state}")
        self.state = TicketState.RESOLVED
        self.resolved_by_tier = self.current_tier
        self.resolved_by_agent = self.current_agent
        self.last_resolution_note = resolution_note
        self.resolved_at = datetime.now(timezone.utc)

    def confirm_close(self) -> None:
        """Customer accepts the resolution."""
        if self.state != TicketState.RESOLVED:
            raise ValueError(f"Cannot close from state {self.state}")
        self.state = TicketState.CLOSED

    def reject_and_reopen(
        self,
        reason: str,
        reopened_by: str,
        policy: ReopenPolicy,
    ) -> ReopenEvent:
        """
        Customer rejects the resolution ("ยังใช้งานไม่ได้ครับ").

        Routes back to the tier/agent that produced the resolution
        (NOT back through Submit Ticket / Validation / Classification /
        Assignment Engine), unless the reopen cap has been exceeded, in
        which case it force-escalates to Tier 3.
        """
        if self.state != TicketState.RESOLVED:
            raise ValueError(f"Cannot reopen from state {self.state}")

        if self.resolved_by_tier is None or self.last_resolution_note is None:
            raise ValueError("Ticket has no prior resolution to reopen against")

        self.reopen_count += 1
        now = datetime.now(timezone.utc)

        # Decide routing: same tier that resolved it, unless cap exceeded
        if self.reopen_count > policy.max_reopen_count:
            target_tier = Tier.TIER_3
            self.state = TicketState.ESCALATED
        else:
            target_tier = self.resolved_by_tier
            self.state = TicketState.REOPENED

        # Shrink SLA on each reopen cycle, but never below the floor
        shrunk_hours = max(
            policy.min_sla_hours,
            policy.base_sla_hours * (policy.sla_shrink_factor ** self.reopen_count),
        )
        new_deadline = now + timedelta(hours=shrunk_hours)

        event = ReopenEvent(
            reopen_reason=reason,
            reopened_by=reopened_by,
            reopened_at=now,
            previous_resolution=self.last_resolution_note,
            reopen_count_after=self.reopen_count,
            new_sla_deadline=new_deadline,
            routed_to_tier=target_tier,
        )
        self.reopen_history.append(event)

        # Route ticket back to the deciding tier; agent must be re-assigned
        # by that tier's queue (kept as None here - actual agent pickup is
        # outside the scope of the state machine).
        self.current_tier = target_tier
        self.current_agent = None
        self.sla_deadline = new_deadline

        return event


# ---------------------------------------------------------------------------
# Demo / example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    policy = ReopenPolicy(max_reopen_count=2, base_sla_hours=24)

    ticket = IncidentTicket(ticket_id="INC-00123")

    # First pass: Tier 1 handles and resolves it
    ticket.assign(Tier.TIER_1, agent="agent.somchai", policy=policy)
    ticket.start_progress()
    ticket.resolve("Restarted the affected service; connectivity restored.")
    print(f"[1] state={ticket.state}, resolved_by={ticket.resolved_by_tier}")

    # Customer says it's still broken -> reopen
    event = ticket.reject_and_reopen(
        reason="ยังใช้งานไม่ได้ครับ (still not working)",
        reopened_by="customer.somsri",
        policy=policy,
    )
    print(f"[2] state={ticket.state}, routed_to={event.routed_to_tier}, "
          f"reopen_count={ticket.reopen_count}, sla_deadline={event.new_sla_deadline}")

    # Tier 1 picks it back up, escalates internally to Tier 2, resolves again
    ticket.current_agent = "agent.specialist.kanya"
    ticket.start_progress()
    ticket.resolve("Applied permanent config fix at the specialist level.")

    # Customer rejects again
    event2 = ticket.reject_and_reopen(
        reason="อาการเดิมเกิดซ้ำอีกครั้ง",
        reopened_by="customer.somsri",
        policy=policy,
    )
    print(f"[3] state={ticket.state}, routed_to={event2.routed_to_tier}, "
          f"reopen_count={ticket.reopen_count}")

    # Third resolve + reject -> exceeds max_reopen_count -> force escalate to Tier 3
    ticket.current_agent = "agent.kanya"
    ticket.start_progress()
    ticket.resolve("Escalated fix attempt, still may not hold.")
    event3 = ticket.reject_and_reopen(
        reason="ปัญหายังไม่หายขาด",
        reopened_by="customer.somsri",
        policy=policy,
    )
    print(f"[4] state={ticket.state}, routed_to={event3.routed_to_tier}, "
          f"reopen_count={ticket.reopen_count}  <-- auto-escalated (cap exceeded)")

    print("\nFull reopen audit trail:")
    for i, ev in enumerate(ticket.reopen_history, start=1):
        print(f"  #{i}: reason={ev.reopen_reason!r}, by={ev.reopened_by}, "
              f"at={ev.reopened_at:%Y-%m-%d %H:%M:%S}, routed_to={ev.routed_to_tier}, "
              f"new_sla={ev.new_sla_deadline:%Y-%m-%d %H:%M:%S}")