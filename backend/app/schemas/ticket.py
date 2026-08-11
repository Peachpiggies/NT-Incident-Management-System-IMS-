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

    source: str = Field(..., min_length=2, max_length=50)


# ==========================================================
# Create
# ==========================================================


class TicketCreate(BaseModel):
    title: str
    description: str

    source: TicketSource = TicketSource.WEB

    category_id: UUID
    subcategory_id: UUID | None = None
    service_id: UUID | None = None
    priority_id: UUID


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

    source: str | None = Field(default=None, min_length=2, max_length=50)


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

    reporter: UserSummary

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

    reporter: UserSummary

    assignee: UserSummary | None = None

    department: DepartmentSummary

    category: CategorySummary

    priority: PrioritySummary

    status: StatusSummary

    created_at: datetime

    updated_at: datetime

    resolved_at: datetime | None = None

    closed_at: datetime | None = None


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