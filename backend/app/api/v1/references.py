"""Reference lookup endpoints for ticket priorities and statuses.

`TicketPriority` and `TicketStatus` are fixed-vocabulary configuration
tables (see app/db/models.py), the same shape as `TicketCategory` in
categories.py -- so these routes intentionally mirror that file's
pattern (list/create/update/soft-delete, `configuration.manage` gated
writes, public reads for any authenticated user).

Previously these tables had schemas (app/schemas/references/priority.py,
status.py) but no routes, so there was no way for a client to populate a
priority/status dropdown -- they were only ever visible nested inside a
ticket response. This module closes that gap.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.db.models import TicketPriority, TicketStatus, User
from app.db.session import get_db
from app.schemas.references.priority import PriorityCreate, PriorityResponse
from app.schemas.references.status import StatusCreate, StatusResponse

router = APIRouter(tags=["References"])


async def _assert_code_available(
    db: AsyncSession,
    model,
    code: str,
    *,
    exclude_id: UUID | None = None,
    label: str,
) -> None:
    conditions = [model.code == code]
    if exclude_id is not None:
        conditions.append(model.id != exclude_id)
    if await db.scalar(select(model).where(*conditions)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"{label} code already exists"
        )


# ==========================================================
# Priorities
# ==========================================================


@router.get("/priorities", response_model=list[PriorityResponse])
async def list_priorities(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[TicketPriority]:
    conditions = []
    if not include_inactive:
        conditions.append(TicketPriority.is_active.is_(True))
    return list(
        (
            await db.scalars(
                select(TicketPriority)
                .where(*conditions)
                .order_by(TicketPriority.sort_order, TicketPriority.name)
            )
        ).all()
    )


@router.post(
    "/priorities", response_model=PriorityResponse, status_code=status.HTTP_201_CREATED
)
async def create_priority(
    payload: PriorityCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketPriority:
    await _assert_code_available(db, TicketPriority, payload.code, label="Priority")
    record = TicketPriority(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/priorities/{priority_id}", response_model=PriorityResponse)
async def update_priority(
    priority_id: UUID,
    payload: PriorityCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketPriority:
    record = await db.get(TicketPriority, priority_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Priority not found")
    await _assert_code_available(
        db, TicketPriority, payload.code, exclude_id=priority_id, label="Priority"
    )
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete(
    "/priorities/{priority_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_priority(
    priority_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    record = await db.get(TicketPriority, priority_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Priority not found")
    record.is_active = False
    record.updated_by = current_user.id
    await db.commit()


# ==========================================================
# Statuses
# ==========================================================


@router.get("/statuses", response_model=list[StatusResponse])
async def list_statuses(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[TicketStatus]:
    conditions = []
    if not include_inactive:
        conditions.append(TicketStatus.is_active.is_(True))
    return list(
        (
            await db.scalars(
                select(TicketStatus)
                .where(*conditions)
                .order_by(TicketStatus.sort_order, TicketStatus.name)
            )
        ).all()
    )


@router.post(
    "/statuses", response_model=StatusResponse, status_code=status.HTTP_201_CREATED
)
async def create_status(
    payload: StatusCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketStatus:
    await _assert_code_available(db, TicketStatus, payload.code, label="Status")
    record = TicketStatus(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/statuses/{status_id}", response_model=StatusResponse)
async def update_status(
    status_id: UUID,
    payload: StatusCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketStatus:
    record = await db.get(TicketStatus, status_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Status not found")
    await _assert_code_available(
        db, TicketStatus, payload.code, exclude_id=status_id, label="Status"
    )
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete(
    "/statuses/{status_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_status(
    status_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    record = await db.get(TicketStatus, status_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Status not found")
    record.is_active = False
    record.updated_by = current_user.id
    await db.commit()
