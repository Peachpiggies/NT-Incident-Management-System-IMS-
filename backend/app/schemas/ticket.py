"""
Ticket schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import TicketSource

from app.schemas.common import (
    CategorySummary,
    DepartmentSummary,
    PrioritySummary,
    StatusSummary,
    UserSummary,
)


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


# ==========================================================
# Status
# ==========================================================


class TicketStatusUpdate(BaseModel):

    status_id: UUID


# ==========================================================
# Priority
# ==========================================================


class TicketPriorityUpdate(BaseModel):

    priority_id: UUID


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