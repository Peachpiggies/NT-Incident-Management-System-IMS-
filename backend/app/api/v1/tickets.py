from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_any_role, require_roles
from app.db.models import AuditEvent, Category, Notification, Ticket, TicketComment, User
from app.db.session import get_db
from app.domain import ALLOWED_TRANSITIONS, Priority, Role, TicketStatus

router = APIRouter(tags=["Tickets"])


def _audit_event(ticket_id: int, actor_id: int, action: str, detail: str | None = None) -> AuditEvent:
    return AuditEvent(ticket_id=ticket_id, actor_id=actor_id, action=action, detail=detail)


def _transition_ticket(ticket: Ticket, new_status: TicketStatus, actor_id: int, action: str, db: AsyncSession) -> None:
    allowed = ALLOWED_TRANSITIONS.get(ticket.status, set())
    if new_status not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid transition from {ticket.status} to {new_status}")
    ticket.status = new_status
    db.add(_audit_event(ticket.id, actor_id, action, f"{ticket.status.value} transition performed"))


class TicketCommentResponse(BaseModel):
    id: int
    ticket_id: int
    author_id: int
    body: str
    is_internal: bool
    created_at: str
    updated_at: str

    model_config = ConfigDict(
    from_attributes=True
)


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=5)
    description: str = Field(..., min_length=10)
    category_id: int
    priority: Priority = Priority.MEDIUM
    affected_asset_service: str | None = None


class TicketResponse(BaseModel):
    id: int
    title: str
    description: str
    priority: Priority
    status: TicketStatus
    affected_asset_service: str | None
    customer_id: int
    category_id: int
    assignee_id: int | None
    escalated_at: str | None
    resolved_at: str | None
    created_at: str
    updated_at: str

    model_config = ConfigDict(
        from_attributes=True
    )


class TicketAssigneeRequest(BaseModel):
    assignee_id: int | None = None


class TicketCommentRequest(BaseModel):
    body: str = Field(..., min_length=5)


class AuditEventResponse(BaseModel):
    id: int
    ticket_id: int
    actor_id: int
    action: str
    detail: str | None
    created_at: str
    updated_at: str

    model_config = ConfigDict(
        from_attributes=True
    )


class TicketDashboardResponse(BaseModel):
    total: int
    open: int
    assigned: int
    in_progress: int
    escalated: int
    resolved: int
    closed: int
    unassigned: int

    model_config = ConfigDict(
        from_attributes=True
    )


async def _get_ticket_or_404(ticket_id: int, db: AsyncSession) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    current_user: Annotated[User, Depends(require_roles(Role.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    category = await db.get(Category, payload.category_id)
    if not category or not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ticket category")

    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        priority=payload.priority,
        status=TicketStatus.OPEN,
        customer_id=current_user.id,
        affected_asset_service=payload.affected_asset_service,
    )
    db.add(ticket)
    await db.flush()
    db.add(_audit_event(ticket.id, current_user.id, "ticket:create", "Ticket created"))
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/tickets", response_model=list[TicketResponse])
async def list_tickets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Ticket]:
    if current_user.role == Role.CUSTOMER:
        result = await db.execute(select(Ticket).where(Ticket.customer_id == current_user.id))
    else:
        result = await db.execute(select(Ticket).order_by(Ticket.created_at.desc()))
    return result.scalars().all()


@router.get("/tickets/dashboard", response_model=TicketDashboardResponse)
async def ticket_dashboard(
    current_user: Annotated[User, Depends(require_roles(Role.MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketDashboardResponse:
    total = await db.execute(select(func.count()).select_from(Ticket))
    open_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.OPEN))
    assigned_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.ASSIGNED))
    in_progress_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.IN_PROGRESS))
    escalated_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.ESCALATED))
    resolved_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.RESOLVED))
    closed_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.CLOSED))
    unassigned_count = await db.execute(select(func.count()).select_from(Ticket).where(Ticket.assignee_id == None))

    return TicketDashboardResponse(
        total=total.scalar_one(),
        open=open_count.scalar_one(),
        assigned=assigned_count.scalar_one(),
        in_progress=in_progress_count.scalar_one(),
        escalated=escalated_count.scalar_one(),
        resolved=resolved_count.scalar_one(),
        closed=closed_count.scalar_one(),
        unassigned=unassigned_count.scalar_one(),
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return ticket


@router.get("/tickets/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_ticket_comments(
    ticket_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketComment]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    query = select(TicketComment).where(TicketComment.ticket_id == ticket_id)
    if current_user.role == Role.CUSTOMER:
        query = query.where(TicketComment.is_internal == False)

    result = await db.execute(query.order_by(TicketComment.created_at.asc()))
    return result.scalars().all()


@router.post("/tickets/{ticket_id}/comments", response_model=TicketCommentResponse, status_code=status.HTTP_201_CREATED)
async def add_ticket_comment(
    ticket_id: int,
    payload: TicketCommentRequest,
    current_user: Annotated[User, Depends(require_roles(Role.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketComment:
    ticket = await _get_ticket_or_404(ticket_id, db)
    if ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=payload.body,
        is_internal=False,
    )
    db.add(comment)
    db.add(_audit_event(ticket.id, current_user.id, "ticket:comment_own", f"Comment added by customer {current_user.id}"))
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/tickets/{ticket_id}/history", response_model=list[AuditEventResponse])
async def get_ticket_history(
    ticket_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AuditEvent]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(select(AuditEvent).where(AuditEvent.ticket_id == ticket_id).order_by(AuditEvent.created_at.asc()))
    return result.scalars().all()


@router.post("/tickets/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: int,
    payload: TicketAssigneeRequest,
    current_user: Annotated[User, Depends(require_any_role([Role.TIER1, Role.MANAGER]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    _transition_ticket(ticket, TicketStatus.ASSIGNED, current_user.id, "ticket:assign", db)
    ticket.assignee_id = payload.assignee_id or current_user.id
    notification = Notification(
        user_id=ticket.assignee_id,
        ticket_id=ticket.id,
        message=f"Ticket #{ticket.id} was assigned to you.",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/escalate", response_model=TicketResponse)
async def escalate_ticket(
    ticket_id: int,
    current_user: Annotated[User, Depends(require_roles(Role.TIER1))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    _transition_ticket(ticket, TicketStatus.ESCALATED, current_user.id, "ticket:escalate", db)
    ticket.escalated_at = datetime.now(timezone.utc)
    notification = Notification(
        user_id=current_user.id,
        ticket_id=ticket.id,
        message=f"Ticket #{ticket.id} was escalated.",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/receive_escalated", response_model=TicketResponse)
async def receive_escalated_ticket(
    ticket_id: int,
    current_user: Annotated[User, Depends(require_roles(Role.TIER2))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    _transition_ticket(ticket, TicketStatus.IN_PROGRESS, current_user.id, "ticket:receive_escalated", db)
    ticket.assignee_id = current_user.id
    notification = Notification(
        user_id=ticket.customer_id,
        ticket_id=ticket.id,
        message=f"Your ticket #{ticket.id} is now in progress.",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_ticket(
    ticket_id: int,
    current_user: Annotated[User, Depends(require_any_role([Role.TIER1, Role.TIER2]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    _transition_ticket(ticket, TicketStatus.RESOLVED, current_user.id, "ticket:resolve", db)
    ticket.resolved_at = datetime.now(timezone.utc)
    notification = Notification(
        user_id=ticket.customer_id,
        ticket_id=ticket.id,
        message=f"Your ticket #{ticket.id} has been resolved.",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/close", response_model=TicketResponse)
async def close_ticket(
    ticket_id: int,
    current_user: Annotated[User, Depends(require_any_role([Role.TIER1, Role.TIER2, Role.MANAGER]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    _transition_ticket(ticket, TicketStatus.CLOSED, current_user.id, "ticket:close", db)
    notification = Notification(
        user_id=ticket.customer_id,
        ticket_id=ticket.id,
        message=f"Your ticket #{ticket.id} has been closed.",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/reopen", response_model=TicketResponse)
async def reopen_ticket(
    ticket_id: int,
    current_user: Annotated[User, Depends(require_any_role([Role.TIER1, Role.TIER2, Role.MANAGER]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    if ticket.status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only resolved or closed tickets can be reopened")

    ticket.status = TicketStatus.ASSIGNED
    ticket.assignee_id = current_user.id
    ticket.resolved_at = None
    ticket.escalated_at = None
    db.add(_audit_event(ticket.id, current_user.id, "ticket:reopen", f"Reopened by {current_user.role.value} {current_user.id}"))
    notification = Notification(
        user_id=ticket.customer_id,
        ticket_id=ticket.id,
        message=f"Your ticket #{ticket.id} has been reopened.",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/internal-note")
async def add_internal_note(
    ticket_id: int,
    payload: TicketCommentRequest,
    current_user: Annotated[User, Depends(require_roles(Role.TIER2))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=payload.body,
        is_internal=True,
    )
    db.add(comment)
    db.add(_audit_event(ticket.id, current_user.id, "ticket:internal_note", f"Internal note added by {current_user.role.value} {current_user.id}"))
    await db.commit()
    return {"message": "Internal note added"}
