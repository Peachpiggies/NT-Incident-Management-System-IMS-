"""FastAPI routes exposing the ticket workflow service layer.

Uses the project's real schemas (app.schemas.ticket, app.schemas.comment) --
this supersedes the earlier draft that used placeholder schema names.

Each endpoint owns its transaction: it calls into `ticket_workflow`, and only
commits after every mutation succeeds. On a `TicketWorkflowError` it rolls
back and raises a typed `HTTPException`. Response schemas are constructed
explicitly with `.model_validate(...)` *inside* the endpoint, before
returning -- not left to FastAPI's automatic `response_model` conversion --
so any lazy-loaded relationship (e.g. `TicketComment.user` for
`CommentResponse.author`) resolves while the DB session from `get_db` is
still open, avoiding a DetachedInstanceError.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.permissions import make_permission_checker
from app.db.models import Ticket, User
from app.schemas.comment import CommentCreate, CommentResponse
from app.schemas.ticket import (
    TicketAssign,
    TicketAssignmentSummary,
    TicketCheckpointUpdate,
    TicketDetail,
    TicketEscalate,
    TicketEscalationSummary,
    TicketSlaStatus,
    TicketStatusUpdate,
)
from app.services import ticket_workflow

router = APIRouter(prefix="/tickets", tags=["ticket-workflow"])


def get_ticket_or_404(ticket_id: UUID, db: Session = Depends(get_db)) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


def _handle_workflow_errors(exc: ticket_workflow.TicketWorkflowError) -> HTTPException:
    if isinstance(exc, ticket_workflow.MissingTransitionPermission):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, ticket_workflow.InvalidCheckpointOrder):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(
        exc,
        (ticket_workflow.InvalidStatusTransition, ticket_workflow.InvalidTierTransition),
    ):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/{ticket_id}/assign", response_model=TicketAssignmentSummary)
def assign_ticket(
    body: TicketAssign,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketAssignmentSummary:
    try:
        assignment = ticket_workflow.assign_ticket(
            db,
            ticket,
            assigned_to=body.assignee_id,
            actor_id=current_user.id,
            reason=body.reason,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(assignment)
    return TicketAssignmentSummary.model_validate(assignment)


@router.post("/{ticket_id}/escalate", response_model=TicketEscalationSummary)
def escalate_ticket(
    body: TicketEscalate,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketEscalationSummary:
    try:
        escalation = ticket_workflow.escalate_ticket(
            db,
            ticket,
            escalation_type=body.escalation_type.value,
            to_tier=body.to_tier,
            to_department_id=body.to_department_id,
            reason_code=body.reason_code,
            comment=body.comment,
            escalated_by=current_user.id,
            allow_tier_skip=body.allow_tier_skip,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(escalation)
    return TicketEscalationSummary.model_validate(escalation)


@router.post("/{ticket_id}/status", response_model=TicketDetail)
def transition_status(
    body: TicketStatusUpdate,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketDetail:
    has_permission = make_permission_checker(db, current_user.id)
    try:
        ticket_workflow.transition_status(
            db,
            ticket,
            to_status_id=body.status_id,
            performed_by=current_user.id,
            remark=body.remark,
            has_permission=has_permission,
            is_closed_status=body.is_closed_status,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(ticket)
    return TicketDetail.model_validate(ticket)


@router.post("/{ticket_id}/checkpoints", response_model=TicketDetail)
def record_checkpoint(
    body: TicketCheckpointUpdate,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketDetail:
    try:
        ticket_workflow.record_checkpoint(
            db,
            ticket,
            checkpoint=body.checkpoint.value,
            at=body.at,
            performed_by=current_user.id,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(ticket)
    return TicketDetail.model_validate(ticket)


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    body: CommentCreate,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommentResponse:
    try:
        comment = ticket_workflow.add_update(
            db,
            ticket,
            user_id=current_user.id,
            comment=body.content,
            update_type=body.update_type.value,
            is_internal=body.is_internal,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(comment)
    return CommentResponse.model_validate(comment)


@router.post("/{ticket_id}/sla/evaluate", response_model=TicketSlaStatus)
def evaluate_sla(
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketSlaStatus:
    breached = ticket_workflow.evaluate_sla(db, ticket, performed_by=current_user.id)
    db.commit()
    return TicketSlaStatus(ticket_id=ticket.id, sla_breached=breached)