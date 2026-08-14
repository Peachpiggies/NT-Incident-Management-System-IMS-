"""
Incident Management - Resolution Flow (4.7)
=============================================

Implements the gate between IN_PROGRESS and RESOLVED:

    IN_PROGRESS
         |
         v
    Resolution Preparation   <-- Agent must fill in the Resolution Requirement
         |                       (Resolution Code, Summary, Root Cause,
         |                        Fix Description) before the transition
         |                       to RESOLVED is allowed.
         v
      RESOLVED

Design goals:
  - Agent cannot press "Resolve" and skip documentation.
  - Resolution Code is a closed enum (not free text) so it can be
    aggregated for Management Analytics later.
  - The resulting Resolution object becomes the structured
    `previous_resolution` that 4.6 Reopen Flow references when a
    customer rejects and the ticket is reopened.

This module depends on incident_reopen_flow.py (same folder) for the
IncidentTicket / TicketState / Tier / ReopenPolicy classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from incident_reopen import IncidentTicket, TicketState


# ---------------------------------------------------------------------------
# Resolution Code (closed vocabulary, for analytics / reporting)
# ---------------------------------------------------------------------------

class ResolutionCode(str, Enum):
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    HARDWARE_REPLACEMENT = "HARDWARE_REPLACEMENT"
    SOFTWARE_PATCH = "SOFTWARE_PATCH"
    SERVICE_RESTART = "SERVICE_RESTART"
    NETWORK_FIX = "NETWORK_FIX"
    USER_ERROR = "USER_ERROR"
    PERMISSION_CHANGE = "PERMISSION_CHANGE"
    THIRD_PARTY_VENDOR_FIX = "THIRD_PARTY_VENDOR_FIX"
    NO_FAULT_FOUND = "NO_FAULT_FOUND"
    WORKAROUND_APPLIED = "WORKAROUND_APPLIED"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Resolution Requirement (what the agent must submit)
# ---------------------------------------------------------------------------

@dataclass
class Resolution:
    """
    Structured resolution record. This becomes the ticket's
    `previous_resolution` once RESOLVED, and is what Reopen Flow (4.6)
    reads back when a customer rejects the resolution.
    """

    resolution_code: ResolutionCode
    resolution_summary: str
    root_cause: str
    fix_description: str
    resolved_by: str
    workaround: Optional[str] = None          # optional: temporary mitigation, if any
    resolved_at: datetime = field(default_factory=datetime.now)

    def is_workaround_only(self) -> bool:
        """
        True if this resolution was only a workaround (no permanent fix).
        Useful for Reopen Flow / analytics: workaround-only resolutions
        have a materially higher chance of being reopened.
        """
        return (
            self.resolution_code == ResolutionCode.WORKAROUND_APPLIED
            or bool(self.workaround)
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ResolutionValidationError(Exception):
    """Raised when the Resolution Requirement is incomplete."""

    def __init__(self, missing_fields: list[str]):
        self.missing_fields = missing_fields
        super().__init__(
            f"Cannot move to RESOLVED - missing required fields: "
            f"{', '.join(missing_fields)}"
        )


REQUIRED_TEXT_FIELDS = ("resolution_summary", "root_cause", "fix_description", "resolved_by")


def validate_resolution(resolution: Resolution) -> None:
    """
    Enforce the Resolution Requirement. Raises ResolutionValidationError
    if any required field is missing/blank. resolution_code is required
    by the dataclass type system already (must be a valid ResolutionCode
    member); everything else is checked for non-empty content here.
    """
    missing = [
        field_name
        for field_name in REQUIRED_TEXT_FIELDS
        if not getattr(resolution, field_name, "").strip()
    ]

    # Extra business rule: if the agent selected WORKAROUND_APPLIED as the
    # code, the workaround field itself must not be empty.
    if resolution.resolution_code == ResolutionCode.WORKAROUND_APPLIED and not (
        resolution.workaround and resolution.workaround.strip()
    ):
        missing.append("workaround")

    if missing:
        raise ResolutionValidationError(missing)


# ---------------------------------------------------------------------------
# Resolution Preparation -> RESOLVED transition
# ---------------------------------------------------------------------------

def prepare_and_resolve(ticket: IncidentTicket, resolution: Resolution) -> Resolution:
    """
    Runs the Resolution Preparation gate and, if valid, moves the ticket
    from IN_PROGRESS to RESOLVED, attaching the structured Resolution
    record.

    This replaces a bare `ticket.resolve("some string")` call with a
    validated, structured transition:

        IN_PROGRESS -> Resolution Preparation -> RESOLVED
    """
    if ticket.state != TicketState.IN_PROGRESS:
        raise ValueError(
            f"Ticket {ticket.ticket_id} must be IN_PROGRESS to enter "
            f"Resolution Preparation (current state: {ticket.state})"
        )

    # --- Resolution Preparation step ---
    validate_resolution(resolution)

    # --- transition to RESOLVED ---
    # Build a single-line note for backward compatibility with the
    # existing IncidentTicket.resolve(note) signature, while also
    # storing the full structured Resolution on the ticket.
    summary_note = (
        f"[{resolution.resolution_code.value}] {resolution.resolution_summary} "
        f"(root cause: {resolution.root_cause})"
    )
    ticket.resolve(summary_note)

    # attach structured resolution for downstream use (analytics, reopen flow)
    ticket.structured_resolution = resolution  # type: ignore[attr-defined]

    return resolution


# ---------------------------------------------------------------------------
# Demo / example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from incident_reopen import Tier, ReopenPolicy

    policy = ReopenPolicy()
    ticket = IncidentTicket(ticket_id="INC-00456")
    ticket.assign(Tier.TIER_2, agent="agent.kanya", policy=policy)
    ticket.start_progress()

    # --- Case 1: Agent tries to resolve without filling requirement ---
    incomplete = Resolution(
        resolution_code=ResolutionCode.CONFIGURATION_CHANGE,
        resolution_summary="",         # left blank - should fail
        root_cause="Incorrect VLAN configuration",
        fix_description="",            # left blank - should fail
        resolved_by="agent.kanya",
    )
    try:
        prepare_and_resolve(ticket, incomplete)
    except ResolutionValidationError as e:
        print(f"[BLOCKED] {e}")

    print(f"Ticket state still: {ticket.state}\n")

    # --- Case 2: Agent fills in the full Resolution Requirement ---
    complete = Resolution(
        resolution_code=ResolutionCode.CONFIGURATION_CHANGE,
        resolution_summary="Restored VLAN configuration and verified connectivity.",
        root_cause="Incorrect VLAN configuration",
        fix_description="Corrected VLAN ID on switch port 12 and re-applied trunk config.",
        resolved_by="agent.kanya",
    )
    prepare_and_resolve(ticket, complete)
    print(f"Ticket state now: {ticket.state}")
    print(f"resolved_by_tier: {ticket.resolved_by_tier}")
    print(f"last_resolution_note: {ticket.last_resolution_note}")
    print(f"structured_resolution.resolution_code: "
          f"{ticket.structured_resolution.resolution_code}")  # type: ignore[attr-defined]

    # --- Case 3: Workaround-only resolution, flagged for reopen risk ---
    ticket2 = IncidentTicket(ticket_id="INC-00789")
    ticket2.assign(Tier.TIER_1, agent="agent.somchai", policy=policy)
    ticket2.start_progress()

    workaround_res = Resolution(
        resolution_code=ResolutionCode.WORKAROUND_APPLIED,
        resolution_summary="Restarted the service to restore access temporarily.",
        root_cause="Root cause not yet identified; under investigation.",
        fix_description="No permanent fix applied yet.",
        workaround="Restarted affected service; issue may recur within 24h.",
        resolved_by="agent.somchai",
    )
    prepare_and_resolve(ticket2, workaround_res)
    print(f"\nTicket 2 state: {ticket2.state}, is_workaround_only: "
          f"{ticket2.structured_resolution.is_workaround_only()}")  # type: ignore[attr-defined]