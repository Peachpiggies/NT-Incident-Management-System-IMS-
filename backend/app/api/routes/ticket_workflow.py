"""FastAPI routes exposing the ticket workflow service layer.

Assumes two dependencies already exist elsewhere in the app (they're implied
by the `RefreshToken`/`LoginHistory` tables but weren't part of this task):

    app.api.deps.get_db()            -> yields a `Session`
    app.api.deps.get_current_user()  -> resolves the JWT/session and
                                         returns the authenticated `User`

If those live at different import paths, only the two imports below need to
change -- nothing else in this file depends on how auth is implemented.

Each endpoint owns its transaction: it calls into `ticket_workflow`, and only
commits after every mutation succeeds. If anything raises, FastAPI's default
exception handling combined with the session lifecycle in `get_db` should
roll back (a `get_db` that does `try/finally: session.close()` without an
explicit commit-on-success is safe here since we commit explicitly below).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.permissions import make_permission_checker
from app.db.models import Ticket, User
from app.schemas.ticket import (
    AssignTicketRequest,
    CheckpointRequest,
    CommentRequest,
    EscalateTicketRequest,
    SlaEvaluationResponse,
    StatusTransitionRequest,
    TicketAssignmentRead,
    TicketCommentRead,
    TicketEscalationRead,
    TicketRead,
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


@router.post("/{ticket_id}/assign", response_model=TicketAssignmentRead)
def assign_ticket(
    body: AssignTicketRequest,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketAssignmentRead:
    try:
        assignment = ticket_workflow.assign_ticket(
            db,
            ticket,
            assigned_to=body.assigned_to,
            actor_id=current_user.id,
            reason=body.reason,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(assignment)
    return TicketAssignmentRead.model_validate(assignment)


@router.post("/{ticket_id}/escalate", response_model=TicketEscalationRead)
def escalate_ticket(
    body: EscalateTicketRequest,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketEscalationRead:
    try:
        escalation = ticket_workflow.escalate_ticket(
            db,
            ticket,
            escalation_type=body.escalation_type,
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
    return TicketEscalationRead.model_validate(escalation)


@router.post("/{ticket_id}/status", response_model=TicketRead)
def transition_status(
    body: StatusTransitionRequest,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    has_permission = make_permission_checker(db, current_user.id)
    try:
        ticket_workflow.transition_status(
            db,
            ticket,
            to_status_id=body.to_status_id,
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
    return TicketRead.model_validate(ticket)


@router.post("/{ticket_id}/checkpoints", response_model=TicketRead)
def record_checkpoint(
    body: CheckpointRequest,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    try:
        ticket_workflow.record_checkpoint(
            db,
            ticket,
            checkpoint=body.checkpoint,
            at=body.at,
            performed_by=current_user.id,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.post("/{ticket_id}/comments", response_model=TicketCommentRead, status_code=status.HTTP_201_CREATED)
def add_comment(
    body: CommentRequest,
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketCommentRead:
    try:
        comment = ticket_workflow.add_update(
            db,
            ticket,
            user_id=current_user.id,
            comment=body.comment,
            update_type=body.update_type,
            is_internal=body.is_internal,
        )
    except ticket_workflow.TicketWorkflowError as exc:
        db.rollback()
        raise _handle_workflow_errors(exc) from exc
    db.commit()
    db.refresh(comment)
    return TicketCommentRead.model_validate(comment)


@router.post("/{ticket_id}/sla/evaluate", response_model=SlaEvaluationResponse)
def evaluate_sla(
    ticket: Ticket = Depends(get_ticket_or_404),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SlaEvaluationResponse:
    breached = ticket_workflow.evaluate_sla(db, ticket, performed_by=current_user.id)
    db.commit()
    return SlaEvaluationResponse(ticket_id=ticket.id, sla_breached=breached)