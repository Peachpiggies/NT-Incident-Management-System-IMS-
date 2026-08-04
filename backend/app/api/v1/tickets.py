"""UUID-based ticket workflow API.

Workflow state is configuration data (`ticket_statuses`), so this module never
uses the retired Python enums or integer ticket/customer identifiers.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    require_ticket_read,
    ticket_read_scope,
    user_has_permission,
)
from app.db.models import (
    Notification,
    Ticket,
    TicketAssignment,
    TicketCategory,
    TicketComment,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    User,
)
from app.db.session import get_db

router = APIRouter(tags=["Tickets"])


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10)
    category_id: UUID
    priority_id: UUID
    department_id: UUID | None = None
    source: str = Field(default="WEB", max_length=30)


class TicketResponse(BaseModel):
    id: UUID
    ticket_no: str
    title: str
    description: str
    requester_id: UUID
    department_id: UUID | None
    category_id: UUID
    priority_id: UUID
    status_id: UUID
    assigned_to: UUID | None
    source: str
    due_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketAssigneeRequest(BaseModel):
    assignee_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)


class TicketCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=10000)


class TicketCommentResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    user_id: UUID
    comment: str
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketHistoryResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    action: str
    field: str | None
    old_value: str | None
    new_value: str | None
    performed_by: UUID | None
    performed_at: datetime
    remark: str | None

    model_config = ConfigDict(from_attributes=True)


class TicketDashboardResponse(BaseModel):
    total: int
    unassigned: int
    by_status: dict[str, int]


async def _get_ticket_or_404(ticket_id: UUID, db: AsyncSession) -> Ticket:
    ticket = await db.scalar(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.is_deleted.is_(False))
    )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )
    return ticket


async def _active_master_or_400(db: AsyncSession, model, record_id: UUID, label: str):
    record = await db.scalar(
        select(model).where(
            model.id == record_id,
            model.is_active.is_(True),
            model.is_deleted.is_(False),
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {label}"
        )
    return record


async def _status_by_code(db: AsyncSession, code: str) -> TicketStatus:
    record = await db.scalar(
        select(TicketStatus).where(
            TicketStatus.code == code,
            TicketStatus.is_active.is_(True),
            TicketStatus.is_deleted.is_(False),
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket status {code} is not configured",
        )
    return record


def _history(
    ticket: Ticket,
    actor_id: UUID,
    action: str,
    *,
    field: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    remark: str | None = None,
) -> TicketHistory:
    return TicketHistory(
        ticket_id=ticket.id,
        performed_by=actor_id,
        action=action,
        field=field,
        old_value=old_value,
        new_value=new_value,
        remark=remark,
    )


def _notification(
    user_id: UUID, ticket: Ticket, title: str, message: str, notification_type: str
) -> Notification:
    return Notification(
        user_id=user_id, title=title, message=message, type=notification_type
    )


@router.post(
    "/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED
)
async def create_ticket(
    payload: TicketCreate,
    current_user: Annotated[User, Depends(require_permission("ticket.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    await _active_master_or_400(
        db, TicketCategory, payload.category_id, "ticket category"
    )
    priority = await _active_master_or_400(
        db, TicketPriority, payload.priority_id, "ticket priority"
    )
    initial_status = await _status_by_code(db, "NEW")
    ticket_id = uuid4()
    ticket = Ticket(
        id=ticket_id,
        ticket_no=f"IMS-{datetime.now(timezone.utc):%Y%m%d}-{str(ticket_id)[:8].upper()}",
        title=payload.title,
        description=payload.description,
        requester_id=current_user.id,
        department_id=payload.department_id or current_user.department_id,
        category_id=payload.category_id,
        priority_id=priority.id,
        status_id=initial_status.id,
        source=payload.source.upper(),
        created_by=current_user.id,
    )
    db.add(ticket)
    await db.flush()
    db.add(
        _history(
            ticket,
            current_user.id,
            "ticket.create",
            new_value=initial_status.code,
            remark="Ticket created",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/tickets", response_model=list[TicketResponse])
async def list_tickets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Ticket]:
    statement = select(Ticket).where(Ticket.is_deleted.is_(False))
    if await ticket_read_scope(db, current_user.id) == "own":
        statement = statement.where(Ticket.requester_id == current_user.id)
    return list((await db.scalars(statement.order_by(Ticket.created_at.desc()))).all())


@router.get("/tickets/dashboard", response_model=TicketDashboardResponse)
async def ticket_dashboard(
    current_user: Annotated[User, Depends(require_permission("dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketDashboardResponse:
    total = await db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.is_deleted.is_(False))
    )
    unassigned = await db.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.is_deleted.is_(False), Ticket.assigned_to.is_(None))
    )
    rows = await db.execute(
        select(TicketStatus.code, func.count(Ticket.id))
        .outerjoin(
            Ticket, (Ticket.status_id == TicketStatus.id) & Ticket.is_deleted.is_(False)
        )
        .where(TicketStatus.is_deleted.is_(False))
        .group_by(TicketStatus.code)
    )
    return TicketDashboardResponse(
        total=total or 0, unassigned=unassigned or 0, by_status=dict(rows.all())
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    return ticket


@router.get("/tickets/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_ticket_comments(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketComment]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    statement = select(TicketComment).where(
        TicketComment.ticket_id == ticket.id, TicketComment.is_deleted.is_(False)
    )
    if not await user_has_permission(db, current_user.id, "ticket.internal_note"):
        statement = statement.where(TicketComment.is_internal.is_(False))
    return list(
        (await db.scalars(statement.order_by(TicketComment.created_at.asc()))).all()
    )


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_comment(
    ticket_id: UUID,
    payload: TicketCommentRequest,
    current_user: Annotated[User, Depends(require_permission("ticket.comment"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketComment:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    comment = TicketComment(
        ticket_id=ticket.id,
        user_id=current_user.id,
        comment=payload.comment,
        created_by=current_user.id,
    )
    db.add(comment)
    db.add(
        _history(
            ticket, current_user.id, "ticket.comment", remark="Public comment added"
        )
    )
    await db.commit()
    await db.refresh(comment)
    return comment


@router.post(
    "/tickets/{ticket_id}/internal-note",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_internal_note(
    ticket_id: UUID,
    payload: TicketCommentRequest,
    current_user: Annotated[User, Depends(require_permission("ticket.internal_note"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketComment:
    ticket = await _get_ticket_or_404(ticket_id, db)
    comment = TicketComment(
        ticket_id=ticket.id,
        user_id=current_user.id,
        comment=payload.comment,
        is_internal=True,
        created_by=current_user.id,
    )
    db.add(comment)
    db.add(
        _history(
            ticket,
            current_user.id,
            "ticket.internal_note",
            remark="Internal note added",
        )
    )
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/tickets/{ticket_id}/history", response_model=list[TicketHistoryResponse])
async def get_ticket_history(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketHistory]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    return list(
        (
            await db.scalars(
                select(TicketHistory)
                .where(
                    TicketHistory.ticket_id == ticket.id,
                    TicketHistory.is_deleted.is_(False),
                )
                .order_by(TicketHistory.performed_at.asc())
            )
        ).all()
    )


async def _set_status(
    ticket: Ticket,
    code: str,
    actor: User,
    db: AsyncSession,
    action: str,
    *,
    remark: str | None = None,
) -> None:
    next_status = await _status_by_code(db, code)
    previous = await db.get(TicketStatus, ticket.status_id)
    ticket.status_id = next_status.id
    ticket.updated_by = actor.id
    db.add(
        _history(
            ticket,
            actor.id,
            action,
            field="status",
            old_value=previous.code if previous else None,
            new_value=next_status.code,
            remark=remark,
        )
    )


@router.post("/tickets/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: UUID,
    payload: TicketAssigneeRequest,
    current_user: Annotated[User, Depends(require_permission("ticket.assign"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    assignee_id = payload.assignee_id or current_user.id
    assignee = await db.get(User, assignee_id)
    if assignee is None or not assignee.is_active or assignee.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee"
        )
    previous_assignee = ticket.assigned_to
    ticket.assigned_to = assignee.id
    ticket.updated_by = current_user.id
    await _set_status(
        ticket, "ASSIGNED", current_user, db, "ticket.assign", remark=payload.reason
    )
    db.add(
        TicketAssignment(
            ticket_id=ticket.id,
            assigned_from=previous_assignee,
            assigned_to=assignee.id,
            reason=payload.reason,
            created_by=current_user.id,
        )
    )
    db.add(
        _notification(
            assignee.id,
            ticket,
            "Ticket assigned",
            f"{ticket.ticket_no} was assigned to you.",
            "ticket_assignment",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/escalate", response_model=TicketResponse)
async def escalate_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.escalate"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await _set_status(
        ticket,
        "PENDING",
        current_user,
        db,
        "ticket.escalate",
        remark="Escalated for Tier 2 handling",
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/receive_escalated", response_model=TicketResponse)
async def receive_escalated_ticket(
    ticket_id: UUID,
    current_user: Annotated[
        User, Depends(require_permission("ticket.receive_escalated"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    ticket.assigned_to = current_user.id
    await _set_status(
        ticket, "IN_PROGRESS", current_user, db, "ticket.receive_escalated"
    )
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket in progress",
            f"{ticket.ticket_no} is now in progress.",
            "ticket_update",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.resolve"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    ticket.resolved_at = datetime.now(timezone.utc)
    await _set_status(ticket, "RESOLVED", current_user, db, "ticket.resolve")
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket resolved",
            f"{ticket.ticket_no} has been resolved.",
            "ticket_update",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/close", response_model=TicketResponse)
async def close_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.close"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    ticket.closed_at = datetime.now(timezone.utc)
    await _set_status(ticket, "CLOSED", current_user, db, "ticket.close")
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket closed",
            f"{ticket.ticket_no} has been closed.",
            "ticket_update",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/reopen", response_model=TicketResponse)
async def reopen_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.reopen"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    current_status = await db.get(TicketStatus, ticket.status_id)
    if current_status is None or current_status.code not in {"RESOLVED", "CLOSED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only resolved or closed tickets can be reopened",
        )
    ticket.resolved_at = None
    ticket.closed_at = None
    await _set_status(
        ticket,
        "ASSIGNED" if ticket.assigned_to else "NEW",
        current_user,
        db,
        "ticket.reopen",
    )
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket reopened",
            f"{ticket.ticket_no} has been reopened.",
            "ticket_update",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket
