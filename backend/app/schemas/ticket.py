"""
Ticket schemas.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import TicketSource

from app.schemas.common import (
    CategorySummary,
    DepartmentSummary,
    PrioritySummary,
    StatusSummary,
    UserSummary,
)


# ==========================================================
# Workflow enums
# ==========================================================
# NOTE: these mirror TicketEscalation.escalation_type and the MDDR checkpoint
# columns on Ticket (app/services/ticket_workflow.py). The comment update-type
# enum (NOTE / TECHNICAL_UPDATE) lives in app.schemas.comment instead, since
# comments already have their own schema module.


class TicketEscalationType(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    TECHNICAL = "TECHNICAL"


class TicketMDDRCheckpoint(str, Enum):
    OCCURRED = "occurred_at"
    DETECTED = "detected_at"
    DIAGNOSED = "diagnosed_at"
    RESOLVED = "resolved_at"


# ==========================================================
# Base
# ==========================================================


class TicketBase(BaseModel):

    title: str = Field(..., min_length=5, max_length=255)

    description: str = Field(..., min_length=10)

    category_id: UUID

    subcategory_id: UUID | None = None

    service_id: UUID | None = None

    priority_id: UUID

    department_id: UUID | None = None

    source: TicketSource = TicketSource.WEB


# ==========================================================
# Create
# ==========================================================


class TicketCreate(TicketBase):
    pass


# ==========================================================
# Update
# ==========================================================


class TicketUpdate(BaseModel):

    title: str | None = Field(default=None, min_length=5, max_length=255)

    description: str | None = Field(default=None, min_length=10)

    category_id: UUID | None = None

    subcategory_id: UUID | None = None

    service_id: UUID | None = None

    priority_id: UUID | None = None

    department_id: UUID | None = None

    source: TicketSource | None = None


# ==========================================================
# Assignment
# ==========================================================


class TicketAssign(BaseModel):

    assignee_id: UUID

    reason: str | None = Field(default=None, max_length=2000)


# ==========================================================
# Status
# ==========================================================


class TicketStatusUpdate(BaseModel):

    status_id: UUID

    remark: str | None = Field(default=None, max_length=2000)

    # TODO: ideally derived server-side from the target TicketStatus's own
    # metadata (e.g. a `is_closed`/`is_terminal` flag) rather than trusted
    # from the client. Left as a client-supplied flag for now since that
    # metadata isn't visible in the schema I have -- flag if TicketStatus
    # already has such a field and I'll switch this to a server-side lookup.
    is_closed_status: bool = False


# ==========================================================
# Priority
# ==========================================================


class TicketPriorityUpdate(BaseModel):

    priority_id: UUID


# ==========================================================
# Escalation (T1 -> T2 -> T3)
# ==========================================================


class TicketEscalate(BaseModel):

    escalation_type: TicketEscalationType

    # Required for FUNCTIONAL (which team). Optional for TECHNICAL only in
    # the sense that the API still requires it there too -- see the
    # validator below; it's Optional here purely because FUNCTIONAL doesn't
    # need the caller to specify a tier (it defaults to the current one).
    to_tier: int | None = Field(default=None, ge=1, le=3)

    to_department_id: UUID | None = None

    reason_code: str | None = Field(default=None, max_length=50)

    comment: str | None = Field(default=None, max_length=4000)

    allow_tier_skip: bool = False

    @model_validator(mode="after")
    def _check_required_fields(self) -> "TicketEscalate":
        if self.escalation_type == TicketEscalationType.FUNCTIONAL and self.to_department_id is None:
            raise ValueError("to_department_id is required for a functional escalation")
        if self.escalation_type == TicketEscalationType.TECHNICAL and self.to_tier is None:
            raise ValueError("to_tier is required for a technical escalation")
        return self


# ==========================================================
# MDDR checkpoints
# ==========================================================


class TicketCheckpointUpdate(BaseModel):

    checkpoint: TicketMDDRCheckpoint

    at: datetime | None = None


# ==========================================================
# Search
# ==========================================================


class TicketFilter(BaseModel):

    keyword: str | None = None

    status_id: UUID | None = None

    priority_id: UUID | None = None

    category_id: UUID | None = None

    assignee_id: UUID | None = None

    department_id: UUID | None = None

    page: int = 1

    size: int = 20


# ==========================================================
# Summary
# ==========================================================


class TicketSummary(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    ticket_no: str

    title: str

    status: StatusSummary

    priority: PrioritySummary

    requester: UserSummary

    assignee: UserSummary | None = None

    created_at: datetime


# ==========================================================
# Detail
# ==========================================================


class TicketDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_no: str
    title: str
    description: str

    requester: UserSummary
    requester_id: UUID

    assignee: UserSummary | None = None
    assigned_to: UUID | None = None

    department: DepartmentSummary | None = None
    department_id: UUID | None = None

    category: CategorySummary
    category_id: UUID

    priority: PrioritySummary
    priority_id: UUID

    status: StatusSummary
    status_id: UUID

    # keep the rest of your existing fields unchanged


# ==========================================================
# Assignment history
# ==========================================================


class TicketAssignmentSummary(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    ticket_id: UUID

    assigned_from: UUID | None = None

    assigned_to: UUID

    reason: str | None = None

    assigned_at: datetime


# ==========================================================
# Escalation history
# ==========================================================


class TicketEscalationSummary(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    ticket_id: UUID

    escalation_type: str

    from_tier: int

    to_tier: int

    from_department: DepartmentSummary | None = None

    to_department: DepartmentSummary | None = None

    from_user: UserSummary | None = None

    reason_code: str | None = None

    comment: str | None = None

    escalated_by: UUID | None = None

    escalated_at: datetime


# ==========================================================
# SLA
# ==========================================================


class TicketSlaStatus(BaseModel):

    ticket_id: UUID

    sla_breached: bool


# ==========================================================
# Response
# ==========================================================

# NOTE: `TicketResponse` intentionally has no `success`/`message`/`data`
# envelope. Every endpoint in `app.api.v1.tickets` returns the `Ticket`
# ORM object directly (e.g. `create_ticket() -> Ticket: ... return ticket`)
# and `TicketPage.items` is typed as `list[TicketResponse]`, so this needs
# to be the flat ticket-detail shape, not a wrapper around it.

TicketResponse = TicketDetail


class TicketListResponse(BaseModel):

    success: bool = True

    total: int

    page: int

    size: int

    data: list[TicketSummary]