"""Administration API for the database-driven ticket state machine."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_permission
from app.db.models import TicketStatus, TicketStatusTransition, User
from app.db.session import get_db

router = APIRouter(tags=["Workflow"])


class TransitionRequest(BaseModel):
    from_status_id: UUID
    to_status_id: UUID
    required_permission: str | None = None
    is_active: bool = True


class TransitionResponse(TransitionRequest):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


async def _active_status_or_400(db: AsyncSession, status_id: UUID) -> None:
    record = await db.scalar(
        select(TicketStatus).where(
            TicketStatus.id == status_id,
            TicketStatus.is_active.is_(True),
            TicketStatus.is_deleted.is_(False),
        )
    )
    if record is None:
        raise HTTPException(status_code=400, detail="Invalid ticket status")


@router.get("/workflow/transitions", response_model=list[TransitionResponse])
async def list_transitions(
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketStatusTransition]:
    return list(
        (
            await db.scalars(
                select(TicketStatusTransition)
                .where(TicketStatusTransition.is_deleted.is_(False))
                .order_by(TicketStatusTransition.created_at)
            )
        ).all()
    )


@router.post(
    "/workflow/transitions",
    response_model=TransitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transition(
    payload: TransitionRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketStatusTransition:
    if payload.from_status_id == payload.to_status_id:
        raise HTTPException(status_code=400, detail="A transition must change status")
    await _active_status_or_400(db, payload.from_status_id)
    await _active_status_or_400(db, payload.to_status_id)
    existing = await db.scalar(
        select(TicketStatusTransition).where(
            TicketStatusTransition.from_status_id == payload.from_status_id,
            TicketStatusTransition.to_status_id == payload.to_status_id,
        )
    )
    if existing and not existing.is_deleted:
        raise HTTPException(status_code=409, detail="Transition already exists")
    if existing:
        existing.is_deleted = False
        existing.deleted_at = None
        existing.deleted_by = None
        for field, value in payload.model_dump().items():
            setattr(existing, field, value)
        existing.updated_by = current_user.id
        record = existing
    else:
        record = TicketStatusTransition(
            **payload.model_dump(), created_by=current_user.id
        )
        db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/workflow/transitions/{transition_id}", response_model=TransitionResponse)
async def update_transition(
    transition_id: UUID,
    payload: TransitionRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketStatusTransition:
    record = await db.get(TicketStatusTransition, transition_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="Transition not found")
    if payload.from_status_id == payload.to_status_id:
        raise HTTPException(status_code=400, detail="A transition must change status")
    await _active_status_or_400(db, payload.from_status_id)
    await _active_status_or_400(db, payload.to_status_id)
    for field, value in payload.model_dump().items():
        setattr(record, field, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete(
    "/workflow/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_transition(
    transition_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    record = await db.get(TicketStatusTransition, transition_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="Transition not found")
    record.is_deleted = True
    record.deleted_by = current_user.id
    await db.commit()
