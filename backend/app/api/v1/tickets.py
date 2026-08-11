"""UUID-based ticket workflow API.

Workflow state is configuration data (`ticket_statuses`), so this module never
uses the retired Python enums or integer ticket/customer identifiers.
"""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    require_ticket_read,
    ticket_read_scope,
    user_has_permission,
)

from app.db.models import (
    Department,
    Notification,
    Ticket,
    TicketCategory,
    TicketComment,
    TicketCommentMention,
    TicketHistory,
    TicketNumberSequence,
    TicketPriority,
    TicketService,
    TicketStatus,
    TicketSubcategory,
    User,
)

from app.db.session import get_db
from app.services.assignment import AssignmentService
from app.services.workflow import TicketWorkflowService, commit_ticket_transaction

router = APIRouter(tags=["Tickets"])


class TicketAssigneeRequest(BaseModel):
    assignee_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)


class TicketDepartmentAssignmentRequest(BaseModel):
    department_id: UUID
    reason: str | None = Field(default=None, max_length=2000)


class TicketCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=10000)
    mentioned_user_ids: list[UUID] = Field(default_factory=list, max_length=20)


class TicketCommentResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    user_id: UUID
    comment: str
    is_internal: bool
    created_at: datetime
    updated_at: datetime
    mentioned_user_ids: list[UUID] = Field(default_factory=list)

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


class TicketPage(BaseModel):
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


QUEUE_STATUS_CODES = {
    "new": "NEW",
    "assigned": "ASSIGNED",
    "in_progress": "IN_PROGRESS",
    "pending": "PENDING",
    "escalated": "ESCALATED",
}


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


async def _active_department_or_400(
    db: AsyncSession, department_id: UUID | None
) -> None:
    if department_id is not None:
        await _active_master_or_400(db, Department, department_id, "department")


async def _validate_classification(
    db: AsyncSession,
    category_id: UUID,
    subcategory_id: UUID | None,
    service_id: UUID | None,
) -> None:
    """Ensure every optional classification level belongs to its parent."""
    if service_id and subcategory_id is None:
        raise HTTPException(status_code=400, detail="A service requires a subcategory")
    if subcategory_id:
        subcategory = await _active_master_or_400(
            db, TicketSubcategory, subcategory_id, "ticket subcategory"
        )
        if subcategory.category_id != category_id:
            raise HTTPException(
                status_code=400, detail="Subcategory does not belong to category"
            )
    if service_id:
        service = await _active_master_or_400(
            db, TicketService, service_id, "ticket service"
        )
        if service.subcategory_id != subcategory_id:
            raise HTTPException(
                status_code=400, detail="Service does not belong to subcategory"
            )


async def _assert_ticket_editable(ticket: Ticket, db: AsyncSession) -> None:
    current_status = await db.get(TicketStatus, ticket.status_id)
    if current_status and current_status.is_closed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed tickets cannot be edited",
        )


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


async def _next_ticket_number(db: AsyncSession) -> str:
    """Atomically allocate a daily incident number on PostgreSQL or SQLite."""
    business_date = datetime.now(timezone.utc).date()
    dialect_name = db.get_bind().dialect.name
    insert = postgres_insert if dialect_name == "postgresql" else sqlite_insert
    statement = (
        insert(TicketNumberSequence)
        .values(business_date=business_date, last_value=1)
        .on_conflict_do_update(
            index_elements=[TicketNumberSequence.business_date],
            set_={"last_value": TicketNumberSequence.last_value + 1},
        )
        .returning(TicketNumberSequence.last_value)
    )
    sequence = await db.scalar(statement)
    return f"INC-{business_date:%Y%m%d}-{sequence:06d}"


async def _ticket_page(
    db: AsyncSession,
    current_user: User,
    *,
    q: str | None,
    status_id: UUID | None,
    status_code: str | None,
    category_id: UUID | None,
    subcategory_id: UUID | None,
    service_id: UUID | None,
    priority_id: UUID | None,
    department_id: UUID | None,
    assignee_id: UUID | None,
    requester_id: UUID | None,
    limit: int,
    offset: int,
    sort_by: Literal["created_at", "updated_at", "ticket_no", "due_at"],
    sort_order: Literal["asc", "desc"],
) -> TicketPage:
    conditions = [Ticket.is_deleted.is_(False)]
    statement = select(Ticket)
    count_statement = select(func.count()).select_from(Ticket)
    if status_code:
        statement = statement.join(TicketStatus, Ticket.status_id == TicketStatus.id)
        count_statement = count_statement.join(
            TicketStatus, Ticket.status_id == TicketStatus.id
        )
        conditions.append(TicketStatus.code == status_code.upper())
    for column, value in [
        (Ticket.status_id, status_id),
        (Ticket.category_id, category_id),
        (Ticket.subcategory_id, subcategory_id),
        (Ticket.service_id, service_id),
        (Ticket.priority_id, priority_id),
        (Ticket.department_id, department_id),
        (Ticket.assigned_to, assignee_id),
        (Ticket.requester_id, requester_id),
    ]:
        if value is not None:
            conditions.append(column == value)
    if q:
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                Ticket.ticket_no.ilike(term),
                Ticket.title.ilike(term),
                Ticket.description.ilike(term),
            )
        )
    if await ticket_read_scope(db, current_user.id) == "own":
        conditions.append(Ticket.requester_id == current_user.id)
    sort_column = getattr(Ticket, sort_by)
    order = asc(sort_column) if sort_order == "asc" else desc(sort_column)
    items = list(
        (
            await db.scalars(
                statement.where(*conditions)
                .order_by(order, Ticket.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    total = await db.scalar(count_statement.where(*conditions))
    return TicketPage(items=items, total=total or 0, limit=limit, offset=offset)


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


async def _validate_mentioned_users(
    db: AsyncSession, mentioned_user_ids: list[UUID]
) -> list[UUID]:
    unique_ids = list(dict.fromkeys(mentioned_user_ids))
    if not unique_ids:
        return []
    found_ids = set(
        (
            await db.scalars(
                select(User.id).where(
                    User.id.in_(unique_ids),
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
            )
        ).all()
    )
    if len(found_ids) != len(unique_ids):
        raise HTTPException(status_code=400, detail="Mentioned user is invalid or inactive")
    return unique_ids


async def _set_comment_mentions(
    db: AsyncSession, comment: TicketComment, mentioned_user_ids: list[UUID], actor_id: UUID
) -> None:
    requested_ids = set(await _validate_mentioned_users(db, mentioned_user_ids))
    existing = list(
        (
            await db.scalars(
                select(TicketCommentMention).where(
                    TicketCommentMention.comment_id == comment.id
                )
            )
        ).all()
    )
    existing_by_user = {mention.user_id: mention for mention in existing}
    for mention in existing:
        if mention.user_id not in requested_ids and not mention.is_deleted:
            mention.is_deleted = True
            mention.deleted_by = actor_id
    for user_id in requested_ids:
        mention = existing_by_user.get(user_id)
        if mention is None:
            db.add(
                TicketCommentMention(
                    comment_id=comment.id, user_id=user_id, created_by=actor_id
                )
            )
        elif mention.is_deleted:
            mention.is_deleted = False
            mention.deleted_at = None
            mention.deleted_by = None
            mention.updated_by = actor_id


async def _comment_response(db: AsyncSession, comment: TicketComment) -> TicketCommentResponse:
    mentioned_user_ids = list(
        (
            await db.scalars(
                select(TicketCommentMention.user_id).where(
                    TicketCommentMention.comment_id == comment.id,
                    TicketCommentMention.is_deleted.is_(False),
                )
            )
        ).all()
    )
    return TicketCommentResponse(
        id=comment.id,
        ticket_id=comment.ticket_id,
        user_id=comment.user_id,
        comment=comment.comment,
        is_internal=comment.is_internal,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        mentioned_user_ids=mentioned_user_ids,
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
    await _validate_classification(
        db, payload.category_id, payload.subcategory_id, payload.service_id
    )
    priority = await _active_master_or_400(
        db, TicketPriority, payload.priority_id, "ticket priority"
    )
    await _active_department_or_400(
        db, payload.department_id or current_user.department_id
    )
    initial_status = await _status_by_code(db, "NEW")
    ticket_id = uuid4()
    ticket = Ticket(
        id=ticket_id,
        ticket_no=await _next_ticket_number(db),
        title=payload.title,
        description=payload.description,
        requester_id=current_user.id,
        department_id=payload.department_id or current_user.department_id,
        category_id=payload.category_id,
        subcategory_id=payload.subcategory_id,
        service_id=payload.service_id,
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
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    current_user: Annotated[User, Depends(require_permission("ticket.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    await _assert_ticket_editable(ticket, db)
    updates = payload.model_dump(exclude_unset=True)
    if "category_id" in updates and updates["category_id"] is not None:
        await _active_master_or_400(
            db, TicketCategory, updates["category_id"], "ticket category"
        )
    classification_category_id = updates.get("category_id", ticket.category_id)
    classification_subcategory_id = updates.get("subcategory_id", ticket.subcategory_id)
    classification_service_id = updates.get("service_id", ticket.service_id)
    if any(key in updates for key in ("category_id", "subcategory_id", "service_id")):
        await _validate_classification(
            db,
            classification_category_id,
            classification_subcategory_id,
            classification_service_id,
        )
    if "priority_id" in updates and updates["priority_id"] is not None:
        await _active_master_or_400(
            db, TicketPriority, updates["priority_id"], "ticket priority"
        )
        if (
            ticket.requester_id == current_user.id
            and await ticket_read_scope(db, current_user.id) == "own"
            and ticket.assigned_to is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customers cannot change priority after assignment",
            )
    if "department_id" in updates:
        await _active_department_or_400(db, updates["department_id"])
    for field, value in updates.items():
        if field == "source" and value is not None:
            value = value.upper()
        old_value = getattr(ticket, field)
        if old_value != value:
            setattr(ticket, field, value)
            db.add(
                _history(
                    ticket,
                    current_user.id,
                    "ticket.update",
                    field=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(value) if value is not None else None,
                )
            )
    ticket.updated_by = current_user.id
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.get("/tickets", response_model=TicketPage)
async def list_tickets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, min_length=1, max_length=200),
    status_id: UUID | None = None,
    category_id: UUID | None = None,
    subcategory_id: UUID | None = None,
    service_id: UUID | None = None,
    priority_id: UUID | None = None,
    department_id: UUID | None = None,
    assignee_id: UUID | None = None,
    requester_id: UUID | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "ticket_no", "due_at"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> TicketPage:
    return await _ticket_page(
        db,
        current_user,
        q=q,
        status_id=status_id,
        status_code=None,
        category_id=category_id,
        subcategory_id=subcategory_id,
        service_id=service_id,
        priority_id=priority_id,
        department_id=department_id,
        assignee_id=assignee_id,
        requester_id=requester_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/tickets/search", response_model=TicketPage)
async def search_tickets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "ticket_no", "due_at"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> TicketPage:
    return await _ticket_page(
        db,
        current_user,
        q=q,
        status_id=None,
        status_code=None,
        category_id=None,
        subcategory_id=None,
        service_id=None,
        priority_id=None,
        department_id=None,
        assignee_id=None,
        requester_id=None,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/tickets/queues/{queue}", response_model=TicketPage)
async def queue_tickets(
    queue: Literal["new", "assigned", "in_progress", "pending", "escalated"],
    current_user: Annotated[User, Depends(require_permission("ticket.read_all"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "ticket_no", "due_at"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> TicketPage:
    return await _ticket_page(
        db,
        current_user,
        q=q,
        status_id=None,
        status_code=QUEUE_STATUS_CODES[queue],
        category_id=None,
        subcategory_id=None,
        service_id=None,
        priority_id=None,
        department_id=None,
        assignee_id=None,
        requester_id=None,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


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


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    ticket.is_deleted = True
    ticket.deleted_at = datetime.now(timezone.utc)
    ticket.deleted_by = current_user.id
    ticket.updated_by = current_user.id
    db.add(
        _history(
            ticket,
            current_user.id,
            "ticket.delete",
            remark="Ticket soft deleted",
        )
    )
    await commit_ticket_transaction(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tickets/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_ticket_comments(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketCommentResponse]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    statement = select(TicketComment).where(
        TicketComment.ticket_id == ticket.id, TicketComment.is_deleted.is_(False)
    )
    if not await user_has_permission(db, current_user.id, "ticket.internal_note"):
        statement = statement.where(TicketComment.is_internal.is_(False))
    comments = list(
        (await db.scalars(statement.order_by(TicketComment.created_at.asc()))).all()
    )
    return [await _comment_response(db, comment) for comment in comments]


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
) -> TicketCommentResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    comment = TicketComment(
        ticket_id=ticket.id,
        user_id=current_user.id,
        comment=payload.comment,
        created_by=current_user.id,
    )
    db.add(comment)
    await db.flush()
    mentioned_user_ids = await _validate_mentioned_users(
        db, payload.mentioned_user_ids
    )
    await _set_comment_mentions(db, comment, mentioned_user_ids, current_user.id)
    for user_id in mentioned_user_ids:
        if user_id != current_user.id:
            db.add(
                _notification(
                    user_id,
                    ticket,
                    "You were mentioned",
                    f"You were mentioned on {ticket.ticket_no}.",
                    "ticket_mention",
                )
            )
    db.add(
        _history(
            ticket, current_user.id, "ticket.comment", remark="Public comment added"
        )
    )
    await commit_ticket_transaction(db)
    await db.refresh(comment)
    return await _comment_response(db, comment)


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
) -> TicketCommentResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)
    comment = TicketComment(
        ticket_id=ticket.id,
        user_id=current_user.id,
        comment=payload.comment,
        is_internal=True,
        created_by=current_user.id,
    )
    db.add(comment)
    await db.flush()
    mentioned_user_ids = await _validate_mentioned_users(
        db, payload.mentioned_user_ids
    )
    await _set_comment_mentions(db, comment, mentioned_user_ids, current_user.id)
    for user_id in mentioned_user_ids:
        if user_id != current_user.id:
            db.add(
                _notification(
                    user_id,
                    ticket,
                    "You were mentioned in an internal note",
                    f"You were mentioned on {ticket.ticket_no}.",
                    "ticket_mention",
                )
            )
    db.add(
        _history(
            ticket,
            current_user.id,
            "ticket.internal_note",
            remark="Internal note added",
        )
    )
    await commit_ticket_transaction(db)
    await db.refresh(comment)
    return await _comment_response(db, comment)


async def _comment_for_edit(
    ticket_id: UUID, comment_id: UUID, current_user: User, db: AsyncSession
) -> tuple[Ticket, TicketComment]:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await require_ticket_read(db, current_user, ticket)
    comment = await db.get(TicketComment, comment_id)
    if comment is None or comment.ticket_id != ticket_id or comment.is_deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
    can_manage = await user_has_permission(db, current_user.id, "ticket.comment_manage")
    if comment.user_id != current_user.id and not can_manage:
        raise HTTPException(status_code=403, detail="Forbidden")
    if comment.is_internal and not await user_has_permission(
        db, current_user.id, "ticket.internal_note"
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    return ticket, comment


@router.patch(
    "/tickets/{ticket_id}/comments/{comment_id}", response_model=TicketCommentResponse
)
async def edit_ticket_comment(
    ticket_id: UUID,
    comment_id: UUID,
    payload: TicketCommentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCommentResponse:
    ticket, comment = await _comment_for_edit(ticket_id, comment_id, current_user, db)
    comment.comment = payload.comment
    comment.updated_by = current_user.id
    mentioned_user_ids = await _validate_mentioned_users(
        db, payload.mentioned_user_ids
    )
    await _set_comment_mentions(db, comment, mentioned_user_ids, current_user.id)
    db.add(
        _history(ticket, current_user.id, "ticket.comment_edit", remark="Comment edited")
    )
    await commit_ticket_transaction(db)
    await db.refresh(comment)
    return await _comment_response(db, comment)


@router.delete(
    "/tickets/{ticket_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_ticket_comment(
    ticket_id: UUID,
    comment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    ticket, comment = await _comment_for_edit(ticket_id, comment_id, current_user, db)
    comment.is_deleted = True
    comment.deleted_at = datetime.now(timezone.utc)
    comment.deleted_by = current_user.id
    comment.updated_by = current_user.id
    db.add(
        _history(ticket, current_user.id, "ticket.comment_delete", remark="Comment deleted")
    )
    await commit_ticket_transaction(db)


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


@router.post("/tickets/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: UUID,
    payload: TicketAssigneeRequest,
    current_user: Annotated[User, Depends(require_permission("ticket.assign"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    assignee_id = payload.assignee_id or current_user.id
    assignee = await AssignmentService(db).assign_user(
        ticket, assignee_id, current_user, reason=payload.reason
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
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/assign-department", response_model=TicketResponse)
async def assign_ticket_department(
    ticket_id: UUID,
    payload: TicketDepartmentAssignmentRequest,
    current_user: Annotated[User, Depends(require_permission("ticket.assign"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    department = await AssignmentService(db).assign_department(
        ticket, payload.department_id, current_user, reason=payload.reason
    )
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket routed",
            f"{ticket.ticket_no} was routed to {department.name}.",
            "ticket_assignment",
        )
    )
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/start", response_model=TicketResponse)
async def start_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.start"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await TicketWorkflowService(db).transition_to_code(
        ticket, "IN_PROGRESS", current_user, action="ticket.start"
    )
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/pending", response_model=TicketResponse)
async def pending_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.pending"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await TicketWorkflowService(db).transition_to_code(
        ticket, "PENDING", current_user, action="ticket.pending"
    )
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/escalate", response_model=TicketResponse)
async def escalate_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.escalate"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    await TicketWorkflowService(db).transition_to_code(
        ticket,
        "ESCALATED",
        current_user,
        action="ticket.escalate",
        remark="Escalated for Tier 2 handling",
    )
    await commit_ticket_transaction(db)
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
    await TicketWorkflowService(db).transition_to_code(
        ticket, "IN_PROGRESS", current_user, action="ticket.receive_escalated"
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
    await commit_ticket_transaction(db)
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
    await TicketWorkflowService(db).transition_to_code(
        ticket, "RESOLVED", current_user, action="ticket.resolve"
    )
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket resolved",
            f"{ticket.ticket_no} has been resolved.",
            "ticket_update",
        )
    )
    await commit_ticket_transaction(db)
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
    await TicketWorkflowService(db).transition_to_code(
        ticket, "CLOSED", current_user, action="ticket.close"
    )
    db.add(
        _notification(
            ticket.requester_id,
            ticket,
            "Ticket closed",
            f"{ticket.ticket_no} has been closed.",
            "ticket_update",
        )
    )
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/reopen", response_model=TicketResponse)
async def reopen_ticket(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.reopen"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Ticket:
    ticket = await _get_ticket_or_404(ticket_id, db)
    ticket.resolved_at = None
    ticket.closed_at = None
    await TicketWorkflowService(db).transition_to_code(
        ticket,
        "ASSIGNED" if ticket.assigned_to else "NEW",
        current_user,
        action="ticket.reopen",
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
    await commit_ticket_transaction(db)
    await db.refresh(ticket)
    return ticket