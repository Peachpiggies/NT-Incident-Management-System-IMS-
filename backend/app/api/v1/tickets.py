from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_any_role, require_roles
from app.db.models import Ticket
from app.db.session import get_db
from app.domain import Priority, Role, TicketStatus

router = APIRouter(tags=["Tickets"])


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

    class Config:
        orm_mode = True


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    current_user=Depends(require_roles(Role.CUSTOMER)),
    db: Annotated[AsyncSession, Depends(get_db)] = Depends(get_db),
) -> TicketResponse:
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
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/tickets", response_model=list[TicketResponse])
async def list_tickets(
    current_user=Depends(get_current_user),
    db: Annotated[AsyncSession, Depends(get_db)] = Depends(get_db),
) -> list[Ticket]:
    if current_user.role == Role.CUSTOMER:
        result = await db.execute(select(Ticket).where(Ticket.customer_id == current_user.id))
    else:
        result = await db.execute(select(Ticket).order_by(Ticket.created_at.desc()))
    return result.scalars().all()


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: int,
    current_user=Depends(get_current_user),
    db: Annotated[AsyncSession, Depends(get_db)] = Depends(get_db),
) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return ticket
