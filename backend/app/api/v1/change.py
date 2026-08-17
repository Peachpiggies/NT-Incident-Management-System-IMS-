"""Change Management HTTP API.

The router exposes the persisted Change Management workflow and delegates all
state transitions to ``ChangeManagementService`` so the API cannot bypass the
domain state machine in ``app.core.change_management``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import require_permission
from app.db.models import ChangeApproval, ChangeRequest, User
from app.db.session import get_db
from app.schemas.change_management import (
    ApprovalDecision,
    ChangeApprovalCreate,
    ChangeApprovalListResponse,
    ChangeApprovalResponse,
    ChangeImplementationCreate,
    ChangeRequestCreate,
    ChangeRequestUpdate,
    ChangeImplementationUpdate,
    ChangeRequestListResponse,
    ChangeRequestResponse,
    ChangeRequestSummary,
    ChangeRollbackCreate,
    ChangeStatus,
    ChangeValidationCreate,
    ChangeType,
    RiskAssessmentCreate,
    RiskAssessmentResponse,
)
from app.services.change_management import ChangeManagementService

router = APIRouter(tags=["Change Management"])


def _response(change: ChangeRequest) -> ChangeRequestResponse:
    return ChangeRequestResponse.model_validate(change)


async def _change(db: AsyncSession, change_id: UUID) -> ChangeRequest:
    return await ChangeManagementService(db).get_or_404(change_id)


@router.get("/changes", response_model=ChangeRequestListResponse)
async def list_changes(
    _current_user: Annotated[User, Depends(require_permission("change.read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: ChangeStatus | None = Query(default=None, alias="status"),
    change_type: ChangeType | None = None,
    risk_level: str | None = Query(default=None),
    requested_by_id: UUID | None = None,
    problem_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ChangeRequestListResponse:
    conditions = [ChangeRequest.is_deleted.is_(False)]
    if status_filter is not None:
        conditions.append(ChangeRequest.status == status_filter.value)
    if change_type is not None:
        conditions.append(ChangeRequest.change_type == change_type.value)
    if risk_level is not None:
        conditions.append(ChangeRequest.risk_level == risk_level.upper())
    if requested_by_id is not None:
        conditions.append(ChangeRequest.requested_by_id == requested_by_id)
    if problem_id is not None:
        conditions.append(ChangeRequest.problem_id == problem_id)

    base = select(ChangeRequest).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.order_by(ChangeRequest.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ChangeRequestListResponse(
        items=[ChangeRequestSummary.model_validate(row) for row in items],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/changes",
    response_model=ChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_change(
    payload: ChangeRequestCreate,
    current_user: Annotated[User, Depends(require_permission("change.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    service = ChangeManagementService(db)
    await service.validate_references(
        priority_id=payload.priority_id,
        service_id=payload.service_id,
        problem_id=payload.problem_id,
    )
    change = ChangeRequest(
        change_no=await service.next_change_number(),
        title=payload.title,
        description=payload.description,
        change_type=payload.change_type.value,
        status=ChangeStatus.DRAFT.value,
        priority_id=payload.priority_id,
        service_id=payload.service_id,
        problem_id=payload.problem_id,
        requested_by_id=current_user.id,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        emergency_justification=payload.emergency_justification,
        created_by=current_user.id,
    )
    db.add(change)
    await db.commit()
    return await service.get_or_404(change.id)


@router.get("/changes/{change_id}", response_model=ChangeRequestResponse)
async def get_change(
    change_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("change.read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    return await _change(db, change_id)


@router.patch("/changes/{change_id}", response_model=ChangeRequestResponse)
async def update_change(
    change_id: UUID,
    payload: ChangeRequestUpdate,
    current_user: Annotated[User, Depends(require_permission("change.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    change = await _change(db, change_id)
    if change.status != ChangeStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Only DRAFT changes can be edited")

    values = payload.model_dump(exclude_unset=True)
    new_start = values.get("planned_start", change.planned_start)
    new_end = values.get("planned_end", change.planned_end)
    if new_end <= new_start:
        raise HTTPException(status_code=422, detail="planned_end must be after planned_start")

    new_type = values.get("change_type", ChangeType(change.change_type))
    new_justification = values.get(
        "emergency_justification", change.emergency_justification
    )
    if new_type == ChangeType.EMERGENCY and not new_justification:
        raise HTTPException(
            status_code=422,
            detail="emergency_justification is required for EMERGENCY changes",
        )

    service = ChangeManagementService(db)
    await service.validate_references(
        priority_id=values.get("priority_id", change.priority_id),
        service_id=values.get("service_id", change.service_id),
        problem_id=values.get("problem_id", change.problem_id),
    )
    for field, value in values.items():
        setattr(change, field, value.value if hasattr(value, "value") else value)
    change.updated_by = current_user.id
    await db.commit()
    return await service.get_or_404(change.id)


@router.post("/changes/{change_id}/submit", response_model=ChangeRequestResponse)
async def submit_change(
    change_id: UUID,
    current_user: Annotated[User, Depends(require_permission("change.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    return await ChangeManagementService(db).submit(await _change(db, change_id), current_user)


@router.post("/changes/{change_id}/risk-assessment", response_model=RiskAssessmentResponse)
async def assess_risk(
    change_id: UUID,
    payload: RiskAssessmentCreate,
    current_user: Annotated[User, Depends(require_permission("change.assess"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RiskAssessmentResponse:
    if payload.change_request_id != change_id:
        raise HTTPException(status_code=400, detail="change_request_id mismatch")
    change = await _change(db, change_id)
    result = await ChangeManagementService(db).assess_risk(
        change,
        current_user,
        risk_level=payload.risk_level,
        impact_description=payload.impact_description,
        likelihood=payload.likelihood,
        mitigation_plan=payload.mitigation_plan,
    )
    return result


@router.post("/changes/{change_id}/approvals", response_model=ChangeRequestResponse)
async def record_approval(
    change_id: UUID,
    payload: ChangeApprovalCreate,
    current_user: Annotated[User, Depends(require_permission("change.approve"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    if payload.change_request_id != change_id:
        raise HTTPException(status_code=400, detail="change_request_id mismatch")
    return await ChangeManagementService(db).approve(
        await _change(db, change_id),
        current_user,
        decision=payload.decision,
        comments=payload.comments,
        emergency_justification=payload.emergency_justification,
    )


@router.get("/changes/{change_id}/approvals", response_model=ChangeApprovalListResponse)
async def list_approvals(
    change_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("change.read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeApprovalListResponse:
    await _change(db, change_id)
    rows = (
        await db.scalars(
            select(ChangeApproval)
            .where(
                ChangeApproval.change_request_id == change_id,
                ChangeApproval.is_deleted.is_(False),
            )
            .options(selectinload(ChangeApproval.approver))
            .order_by(ChangeApproval.created_at.asc())
        )
    ).all()
    return ChangeApprovalListResponse(
        items=[ChangeApprovalResponse.model_validate(row) for row in rows],
        total=len(rows),
    )


@router.post("/changes/{change_id}/implementation", response_model=ChangeRequestResponse)
async def create_implementation(
    change_id: UUID,
    payload: ChangeImplementationCreate,
    current_user: Annotated[User, Depends(require_permission("change.implement"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    if payload.change_request_id != change_id:
        raise HTTPException(status_code=400, detail="change_request_id mismatch")
    return await ChangeManagementService(db).create_implementation(
        await _change(db, change_id),
        current_user,
        implementation_plan=payload.implementation_plan,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
    )


@router.post("/changes/{change_id}/schedule", response_model=ChangeRequestResponse)
async def schedule_change(
    change_id: UUID,
    current_user: Annotated[User, Depends(require_permission("change.implement"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    return await ChangeManagementService(db).schedule(await _change(db, change_id), current_user)


@router.post("/changes/{change_id}/implementation/start", response_model=ChangeRequestResponse)
async def start_implementation(
    change_id: UUID,
    current_user: Annotated[User, Depends(require_permission("change.implement"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    return await ChangeManagementService(db).start(await _change(db, change_id), current_user)


@router.post("/changes/{change_id}/implementation/complete", response_model=ChangeRequestResponse)
async def complete_implementation(
    change_id: UUID,
    payload: ChangeImplementationUpdate | None,
    current_user: Annotated[User, Depends(require_permission("change.implement"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    notes = payload.notes if payload else None
    return await ChangeManagementService(db).complete(await _change(db, change_id), current_user, notes)


@router.post("/changes/{change_id}/validation", response_model=ChangeRequestResponse)
async def validate_change(
    change_id: UUID,
    payload: ChangeValidationCreate,
    current_user: Annotated[User, Depends(require_permission("change.validate"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    if payload.change_request_id != change_id:
        raise HTTPException(status_code=400, detail="change_request_id mismatch")
    return await ChangeManagementService(db).validate(
        await _change(db, change_id),
        current_user,
        success=payload.validation_result,
        notes=payload.notes,
    )


@router.post("/changes/{change_id}/rollback", response_model=ChangeRequestResponse)
async def initiate_rollback(
    change_id: UUID,
    payload: ChangeRollbackCreate,
    current_user: Annotated[User, Depends(require_permission("change.rollback"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    if payload.change_request_id != change_id:
        raise HTTPException(status_code=400, detail="change_request_id mismatch")
    return await ChangeManagementService(db).initiate_rollback(
        await _change(db, change_id),
        current_user,
        reason=payload.reason,
        rollback_plan=payload.rollback_plan,
    )


@router.post("/changes/{change_id}/rollback/complete", response_model=ChangeRequestResponse)
async def complete_rollback(
    change_id: UUID,
    current_user: Annotated[User, Depends(require_permission("change.rollback"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    return await ChangeManagementService(db).complete_rollback(
        await _change(db, change_id), current_user
    )


@router.post("/changes/{change_id}/close", response_model=ChangeRequestResponse)
async def close_change(
    change_id: UUID,
    current_user: Annotated[User, Depends(require_permission("change.close"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRequest:
    return await ChangeManagementService(db).close(await _change(db, change_id), current_user)
