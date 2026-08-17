"""Root Cause Analysis API: root causes, contributing factors, impact
analysis, and the RCA report publishing workflow (submit -> approve /
reject).

Visibility rule: APPROVED RCA reports are readable by anyone authenticated.
DRAFT / IN_REVIEW reports are only visible to whoever prepared them or a
holder of `rca.approve` -- mirrors app/api/v1/knowledge_base.py.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    user_has_permission,
)
from app.db.models import (
    ContributingFactor,
    ImpactAnalysis,
    RCAReport,
    RootCause,
    Ticket,
    User,
)
from app.db.session import get_db
from app.schemas.rca import (
    ContributingFactorCreate,
    ContributingFactorListResponse,
    ContributingFactorResponse,
    ContributingFactorUpdate,
    ImpactAnalysisCreate,
    ImpactAnalysisListResponse,
    ImpactAnalysisResponse,
    ImpactAnalysisUpdate,
    RCAReportApprove,
    RCAReportCreate,
    RCAReportListResponse,
    RCAReportReject,
    RCAReportResponse,
    RCAReportSubmit,
    RCAReportUpdate,
    RootCauseCreate,
    RootCauseListResponse,
    RootCauseResponse,
    RootCauseUpdate,
)
from app.services.rca import RCAService

router = APIRouter(tags=["Root Cause Analysis"])

REPORT_LOAD_OPTIONS = (
    selectinload(RCAReport.root_cause).selectinload(RootCause.identified_by),
    selectinload(RCAReport.prepared_by),
    selectinload(RCAReport.approved_by),
)


# ==========================================================
# Helpers
# ==========================================================


async def _get_root_cause_or_404(db: AsyncSession, root_cause_id: UUID) -> RootCause:
    root_cause = await db.scalar(
        select(RootCause)
        .where(RootCause.id == root_cause_id)
        .options(selectinload(RootCause.identified_by))
    )
    if root_cause is None or root_cause.is_deleted:
        raise HTTPException(status_code=404, detail="Root cause not found")
    return root_cause


async def _get_report_or_404(db: AsyncSession, report_id: UUID) -> RCAReport:
    report = await db.scalar(
        select(RCAReport).where(RCAReport.id == report_id).options(*REPORT_LOAD_OPTIONS)
    )
    if report is None or report.is_deleted:
        raise HTTPException(status_code=404, detail="RCA report not found")
    return report


async def _visible_report_or_404(
    db: AsyncSession, user: User, report: RCAReport
) -> RCAReport:
    if report.status == "APPROVED":
        return report
    if report.prepared_by_id == user.id:
        return report
    if await user_has_permission(db, user.id, "rca.approve"):
        return report
    raise HTTPException(status_code=404, detail="RCA report not found")


async def _validate_anchor_matches_root_cause(
    db: AsyncSession, root_cause: RootCause, ticket_id: UUID | None, problem_id: UUID | None
) -> None:
    if ticket_id is not None and ticket_id != root_cause.ticket_id:
        raise HTTPException(
            status_code=400, detail="ticket_id does not match the root cause's ticket"
        )
    if problem_id is not None and problem_id != root_cause.problem_id:
        raise HTTPException(
            status_code=400, detail="problem_id does not match the root cause's problem"
        )


# ==========================================================
# Root Causes
# ==========================================================


@router.get("/rca/root-causes", response_model=RootCauseListResponse)
async def list_root_causes(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_id: UUID | None = None,
    problem_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> RootCauseListResponse:
    conditions = [RootCause.is_deleted.is_(False)]
    if ticket_id is not None:
        conditions.append(RootCause.ticket_id == ticket_id)
    if problem_id is not None:
        conditions.append(RootCause.problem_id == problem_id)

    base = select(RootCause).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.options(selectinload(RootCause.identified_by))
            .order_by(RootCause.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return RootCauseListResponse(items=items, total=total or 0)


@router.post(
    "/rca/root-causes", response_model=RootCauseResponse, status_code=status.HTTP_201_CREATED
)
async def create_root_cause(
    payload: RootCauseCreate,
    current_user: Annotated[User, Depends(require_permission("rca.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RootCause:
    if payload.ticket_id is not None:
        ticket = await db.get(Ticket, payload.ticket_id)
        if ticket is None or ticket.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid ticket_id")

    root_cause = RootCause(
        **payload.model_dump(),
        identified_by_id=current_user.id,
        created_by=current_user.id,
    )
    db.add(root_cause)
    await db.commit()
    await db.refresh(root_cause)
    return await _get_root_cause_or_404(db, root_cause.id)


@router.get("/rca/root-causes/{root_cause_id}", response_model=RootCauseResponse)
async def get_root_cause(
    root_cause_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RootCause:
    return await _get_root_cause_or_404(db, root_cause_id)


@router.put("/rca/root-causes/{root_cause_id}", response_model=RootCauseResponse)
async def update_root_cause(
    root_cause_id: UUID,
    payload: RootCauseUpdate,
    current_user: Annotated[User, Depends(require_permission("rca.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RootCause:
    root_cause = await _get_root_cause_or_404(db, root_cause_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(root_cause, field, value)
    root_cause.updated_by = current_user.id
    await db.commit()
    await db.refresh(root_cause)
    return await _get_root_cause_or_404(db, root_cause_id)


@router.delete("/rca/root-causes/{root_cause_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_root_cause(
    root_cause_id: UUID,
    current_user: Annotated[User, Depends(require_permission("rca.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    root_cause = await _get_root_cause_or_404(db, root_cause_id)
    root_cause.is_deleted = True
    root_cause.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Contributing Factors
# ==========================================================


@router.get(
    "/rca/root-causes/{root_cause_id}/contributing-factors",
    response_model=ContributingFactorListResponse,
)
async def list_contributing_factors(
    root_cause_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContributingFactorListResponse:
    await _get_root_cause_or_404(db, root_cause_id)
    items = (
        await db.scalars(
            select(ContributingFactor)
            .where(
                ContributingFactor.root_cause_id == root_cause_id,
                ContributingFactor.is_deleted.is_(False),
            )
            .order_by(ContributingFactor.created_at)
        )
    ).all()
    return ContributingFactorListResponse(items=items, total=len(items))


@router.post(
    "/rca/root-causes/{root_cause_id}/contributing-factors",
    response_model=ContributingFactorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contributing_factor(
    root_cause_id: UUID,
    payload: ContributingFactorCreate,
    current_user: Annotated[User, Depends(require_permission("rca.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContributingFactor:
    if payload.root_cause_id != root_cause_id:
        raise HTTPException(status_code=400, detail="root_cause_id mismatch")
    await _get_root_cause_or_404(db, root_cause_id)

    factor = ContributingFactor(**payload.model_dump(), created_by=current_user.id)
    db.add(factor)
    await db.commit()
    await db.refresh(factor)
    return factor


@router.put(
    "/rca/contributing-factors/{factor_id}", response_model=ContributingFactorResponse
)
async def update_contributing_factor(
    factor_id: UUID,
    payload: ContributingFactorUpdate,
    current_user: Annotated[User, Depends(require_permission("rca.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContributingFactor:
    factor = await db.get(ContributingFactor, factor_id)
    if factor is None or factor.is_deleted:
        raise HTTPException(status_code=404, detail="Contributing factor not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(factor, field, value)
    factor.updated_by = current_user.id
    await db.commit()
    await db.refresh(factor)
    return factor


@router.delete(
    "/rca/contributing-factors/{factor_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_contributing_factor(
    factor_id: UUID,
    current_user: Annotated[User, Depends(require_permission("rca.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    factor = await db.get(ContributingFactor, factor_id)
    if factor is None or factor.is_deleted:
        raise HTTPException(status_code=404, detail="Contributing factor not found")
    factor.is_deleted = True
    factor.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Impact Analysis
# ==========================================================


@router.get(
    "/rca/root-causes/{root_cause_id}/impact-analyses",
    response_model=ImpactAnalysisListResponse,
)
async def list_impact_analyses(
    root_cause_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImpactAnalysisListResponse:
    await _get_root_cause_or_404(db, root_cause_id)
    items = (
        await db.scalars(
            select(ImpactAnalysis)
            .where(
                ImpactAnalysis.root_cause_id == root_cause_id,
                ImpactAnalysis.is_deleted.is_(False),
            )
            .order_by(ImpactAnalysis.created_at)
        )
    ).all()
    return ImpactAnalysisListResponse(items=items, total=len(items))


@router.post(
    "/rca/root-causes/{root_cause_id}/impact-analyses",
    response_model=ImpactAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_impact_analysis(
    root_cause_id: UUID,
    payload: ImpactAnalysisCreate,
    current_user: Annotated[User, Depends(require_permission("rca.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImpactAnalysis:
    if payload.root_cause_id != root_cause_id:
        raise HTTPException(status_code=400, detail="root_cause_id mismatch")
    await _get_root_cause_or_404(db, root_cause_id)

    impact = ImpactAnalysis(**payload.model_dump(), created_by=current_user.id)
    db.add(impact)
    await db.commit()
    await db.refresh(impact)
    return impact


@router.put("/rca/impact-analyses/{impact_id}", response_model=ImpactAnalysisResponse)
async def update_impact_analysis(
    impact_id: UUID,
    payload: ImpactAnalysisUpdate,
    current_user: Annotated[User, Depends(require_permission("rca.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImpactAnalysis:
    impact = await db.get(ImpactAnalysis, impact_id)
    if impact is None or impact.is_deleted:
        raise HTTPException(status_code=404, detail="Impact analysis not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(impact, field, value)
    impact.updated_by = current_user.id
    await db.commit()
    await db.refresh(impact)
    return impact


@router.delete("/rca/impact-analyses/{impact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_impact_analysis(
    impact_id: UUID,
    current_user: Annotated[User, Depends(require_permission("rca.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    impact = await db.get(ImpactAnalysis, impact_id)
    if impact is None or impact.is_deleted:
        raise HTTPException(status_code=404, detail="Impact analysis not found")
    impact.is_deleted = True
    impact.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# RCA Report
# ==========================================================


@router.get("/rca/reports", response_model=RCAReportListResponse)
async def list_rca_reports(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_id: UUID | None = None,
    problem_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> RCAReportListResponse:
    can_approve = await user_has_permission(db, current_user.id, "rca.approve")

    conditions = [RCAReport.is_deleted.is_(False)]
    if not can_approve:
        conditions.append(
            (RCAReport.status == "APPROVED") | (RCAReport.prepared_by_id == current_user.id)
        )
    if ticket_id is not None:
        conditions.append(RCAReport.ticket_id == ticket_id)
    if problem_id is not None:
        conditions.append(RCAReport.problem_id == problem_id)
    if status_filter is not None:
        conditions.append(RCAReport.status == status_filter)

    base = select(RCAReport).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.options(*REPORT_LOAD_OPTIONS)
            .order_by(RCAReport.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return RCAReportListResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.post(
    "/rca/reports", response_model=RCAReportResponse, status_code=status.HTTP_201_CREATED
)
async def create_rca_report(
    payload: RCAReportCreate,
    current_user: Annotated[User, Depends(require_permission("rca.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReport:
    root_cause = await _get_root_cause_or_404(db, payload.root_cause_id)
    await _validate_anchor_matches_root_cause(
        db, root_cause, payload.ticket_id, payload.problem_id
    )

    report = RCAReport(
        **payload.model_dump(),
        status="DRAFT",
        prepared_by_id=current_user.id,
        created_by=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return await _get_report_or_404(db, report.id)


@router.get("/rca/reports/{report_id}", response_model=RCAReportResponse)
async def get_rca_report(
    report_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReport:
    report = await _get_report_or_404(db, report_id)
    return await _visible_report_or_404(db, current_user, report)


@router.put("/rca/reports/{report_id}", response_model=RCAReportResponse)
async def update_rca_report(
    report_id: UUID,
    payload: RCAReportUpdate,
    current_user: Annotated[User, Depends(require_permission("rca.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReport:
    report = await _get_report_or_404(db, report_id)
    if report.status != "DRAFT":
        raise HTTPException(
            status_code=409, detail="Only a DRAFT report can be edited; reject it first"
        )
    if report.prepared_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the preparer may edit this report")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(report, field, value)
    report.updated_by = current_user.id
    await db.commit()
    await db.refresh(report)
    return await _get_report_or_404(db, report_id)


@router.delete("/rca/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rca_report(
    report_id: UUID,
    current_user: Annotated[User, Depends(require_permission("rca.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    report = await _get_report_or_404(db, report_id)
    report.is_deleted = True
    report.deleted_by = current_user.id
    await db.commit()


@router.post("/rca/reports/{report_id}/submit", response_model=RCAReportResponse)
async def submit_rca_report(
    report_id: UUID,
    payload: RCAReportSubmit,
    current_user: Annotated[User, Depends(require_permission("rca.submit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReport:
    report = await _get_report_or_404(db, report_id)
    if report.prepared_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the preparer may submit this report")
    service = RCAService(db)
    await service.transition(
        report, "IN_REVIEW", current_user, required_permission="rca.submit"
    )
    return await _get_report_or_404(db, report_id)


@router.post("/rca/reports/{report_id}/approve", response_model=RCAReportResponse)
async def approve_rca_report(
    report_id: UUID,
    payload: RCAReportApprove,
    current_user: Annotated[User, Depends(require_permission("rca.approve"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReport:
    report = await _get_report_or_404(db, report_id)
    service = RCAService(db)
    await service.transition(
        report, "APPROVED", current_user, required_permission="rca.approve", approve=True
    )
    return await _get_report_or_404(db, report_id)


@router.post("/rca/reports/{report_id}/reject", response_model=RCAReportResponse)
async def reject_rca_report(
    report_id: UUID,
    payload: RCAReportReject,
    current_user: Annotated[User, Depends(require_permission("rca.approve"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReport:
    report = await _get_report_or_404(db, report_id)
    service = RCAService(db)
    await service.transition(
        report, "DRAFT", current_user, required_permission="rca.approve"
    )
    return await _get_report_or_404(db, report_id)


@router.get("/tickets/{ticket_id}/rca-reports", response_model=RCAReportListResponse)
async def list_ticket_rca_reports(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RCAReportListResponse:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status_code=404, detail="Ticket not found")

    can_approve = await user_has_permission(db, current_user.id, "rca.approve")
    conditions = [RCAReport.ticket_id == ticket_id, RCAReport.is_deleted.is_(False)]
    if not can_approve:
        conditions.append(
            (RCAReport.status == "APPROVED") | (RCAReport.prepared_by_id == current_user.id)
        )
    items = (
        await db.scalars(
            select(RCAReport)
            .where(*conditions)
            .options(*REPORT_LOAD_OPTIONS)
            .order_by(RCAReport.updated_at.desc())
        )
    ).all()
    return RCAReportListResponse(items=items, total=len(items), page=1, page_size=len(items) or 1)
