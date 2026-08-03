from enum import StrEnum


class Role(StrEnum):
    CUSTOMER = "customer"
    TIER1 = "tier1"
    TIER2 = "tier2"
    MANAGER = "manager"


class TicketStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ALLOWED_TRANSITIONS = {
    TicketStatus.OPEN: {TicketStatus.ASSIGNED},
    TicketStatus.ASSIGNED: {TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED},
    TicketStatus.IN_PROGRESS: {TicketStatus.ESCALATED, TicketStatus.RESOLVED},
    TicketStatus.ESCALATED: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED},
    TicketStatus.CLOSED: set(),
}
