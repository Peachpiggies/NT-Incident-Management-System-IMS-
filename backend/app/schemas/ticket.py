"""
Ticket schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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

    priority_id: UUID

    department_id: UUID


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

    priority_id: UUID | None = None

    department_id: UUID | None = None


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

    ticket_number: str

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

    ticket_number: str

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


class TicketResponse(BaseModel):

    success: bool = True

    message: str

    data: TicketDetail


class TicketListResponse(BaseModel):

    success: bool = True

    total: int

    page: int

    size: int

    data: list[TicketSummary]