"""Problem Management API: problems (with the OPEN -> UNDER_INVESTIGATION ->
KNOWN_ERROR -> RESOLVED -> CLOSED workflow), the Known Error Database,
problem <-> incident linking, workarounds, and permanent fixes.

Mirrors the structure of app/api/v1/rca.py, which this feature links back
to via RootCause.problem_id / RCAReport.problem_id.
"""

from datetime import datetime, timezone
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
    Department,
    KnownError,
    PermanentFix,
    Problem,
    ProblemIncidentLink,
    Ticket,
    TicketCategory,
    TicketPriority,
    User,
    Workaround,
)
from app.db.session import get_db
from app.schemas.problem import (
    KnownErrorCreate,
    KnownErrorListResponse,
    KnownErrorResponse,
    KnownErrorUpdate,
    PermanentFixCreate,
    PermanentFixListResponse,
    PermanentFixResponse,
    PermanentFixUpdate,
    PermanentFixVerify,
    ProblemAssign,
    ProblemCreate,
    ProblemIncidentLinkCreate,
    ProblemIncidentLinkListResponse,
    ProblemIncidentLinkResponse,
    ProblemListResponse,
    ProblemResponse,
    ProblemStatusUpdate,
    ProblemSummary,
    ProblemUpdate,
    WorkaroundCreate,
    WorkaroundListResponse,
    WorkaroundResponse,
    WorkaroundUpdate,
)
from app.services.problem import ProblemService, required_permission_for

router = APIRouter(tags=["Problem Management"])

PROBLEM_LOAD_OPTIONS = (
    selectinload(Problem.category),
    selectinload(Problem.priority),
    selectinload(Problem.owner),
)


# ==========================================================
# Helpers
# ==========================================================


async def _get_problem_or_404(db: AsyncSession, problem_id: UUID) -> Problem:
    problem = await db.scalar(
        select(Problem).where(Problem.id == problem_id).options(*PROBLEM_LOAD_OPTIONS)
    )
    if problem is None or problem.is_deleted:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


async def _problem_response(db: AsyncSession, problem: Problem) -> ProblemResponse:
    link_count = await db.scalar(
        select(func.count())
        .select_from(ProblemIncidentLink)
        .where(
            ProblemIncidentLink.problem_id == problem.id,
            ProblemIncidentLink.is_deleted.is_(False),
        )
    )
    return ProblemResponse(
        id=problem.id,
        problem_no=problem.problem_no,
        title=problem.title,
        description=problem.description,
        category=problem.category,
        priority=problem.priority,
        status=problem.status,
        owner=problem.owner,
        related_incident_count=link_count or 0,
        created_at=problem.created_at,
        updated_at=problem.updated_at,
        resolved_at=problem.resolved_at,
        closed_at=problem.closed_at,
    )


async def _validate_references(
    db: AsyncSession,
    *,
    category_id: UUID | None,
    priority_id: UUID | None,
    department_id: UUID | None,
) -> None:
    if category_id is not None:
        category = await db.get(TicketCategory, category_id)
        if category is None or category.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid category_id")
    if priority_id is not None:
        priority = await db.get(TicketPriority, priority_id)
        if priority is None or priority.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid priority_id")
    if department_id is not None:
        department = await db.get(Department, department_id)
        if department is None or department.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid department_id")


async def _get_known_error_or_404(db: AsyncSession, known_error_id: UUID) -> KnownError:
    known_error = await db.scalar(
        select(KnownError).where(KnownError.id == known_error_id)
    )
    if known_error is None or known_error.is_deleted:
        raise HTTPException(status_code=404, detail="Known error not found")
    return known_error


async def _get_workaround_or_404(db: AsyncSession, workaround_id: UUID) -> Workaround:
    workaround = await db.scalar(
        select(Workaround)
        .where(Workaround.id == workaround_id)
        .options(selectinload(Workaround.creator))
    )
    if workaround is None or workaround.is_deleted:
        raise HTTPException(status_code=404, detail="Workaround not found")
    return workaround


async def _get_permanent_fix_or_404(db: AsyncSession, fix_id: UUID) -> PermanentFix:
    fix = await db.scalar(
        select(PermanentFix)
        .where(PermanentFix.id == fix_id)
        .options(selectinload(PermanentFix.verified_by))
    )
    if fix is None or fix.is_deleted:
        raise HTTPException(status_code=404, detail="Permanent fix not found")
    return fix


# ==========================================================
# Problems
# ==========================================================


@router.get("/problems", response_model=ProblemListResponse)
async def list_problems(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status"),
    category_id: UUID | None = None,
    priority_id: UUID | None = None,
    department_id: UUID | None = None,
    owner_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ProblemListResponse:
    conditions = [Problem.is_deleted.is_(False)]
    for column, value in [
        (Problem.category_id, category_id),
        (Problem.priority_id, priority_id),
        (Problem.department_id, department_id),
        (Problem.owner_id, owner_id),
    ]:
        if value is not None:
            conditions.append(column == value)
    if status_filter is not None:
        conditions.append(Problem.status == status_filter.upper())

    base = select(Problem).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.options(*PROBLEM_LOAD_OPTIONS)
            .order_by(Problem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ProblemListResponse(
        items=[ProblemSummary.model_validate(p) for p in items],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/problems", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED
)
async def create_problem(
    payload: ProblemCreate,
    current_user: Annotated[User, Depends(require_permission("problem.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemResponse:
    await _validate_references(
        db,
        category_id=payload.category_id,
        priority_id=payload.priority_id,
        department_id=payload.department_id,
    )
    service = ProblemService(db)
    problem_no = await service.next_problem_number()

    problem = Problem(
        **payload.model_dump(),
        problem_no=problem_no,
        status="OPEN",
        created_by=current_user.id,
    )
    db.add(problem)
    await db.commit()
    await db.refresh(problem)
    return await _problem_response(db, await _get_problem_or_404(db, problem.id))


@router.get("/problems/{problem_id}", response_model=ProblemResponse)
async def get_problem(
    problem_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemResponse:
    problem = await _get_problem_or_404(db, problem_id)
    return await _problem_response(db, problem)


@router.put("/problems/{problem_id}", response_model=ProblemResponse)
async def update_problem(
    problem_id: UUID,
    payload: ProblemUpdate,
    current_user: Annotated[User, Depends(require_permission("problem.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemResponse:
    problem = await _get_problem_or_404(db, problem_id)
    updates = payload.model_dump(exclude_unset=True)
    await _validate_references(
        db,
        category_id=updates.get("category_id"),
        priority_id=updates.get("priority_id"),
        department_id=updates.get("department_id"),
    )
    for field, value in updates.items():
        setattr(problem, field, value)
    problem.updated_by = current_user.id
    await db.commit()
    await db.refresh(problem)
    return await _problem_response(db, await _get_problem_or_404(db, problem_id))


@router.delete("/problems/{problem_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_problem(
    problem_id: UUID,
    current_user: Annotated[User, Depends(require_permission("problem.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    problem = await _get_problem_or_404(db, problem_id)
    problem.is_deleted = True
    problem.deleted_by = current_user.id
    await db.commit()


@router.post("/problems/{problem_id}/status", response_model=ProblemResponse)
async def update_problem_status(
    problem_id: UUID,
    payload: ProblemStatusUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemResponse:
    problem = await _get_problem_or_404(db, problem_id)
    service = ProblemService(db)
    required_permission = required_permission_for(problem.status, payload.status.value)
    if required_permission is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move problem from {problem.status} to {payload.status.value}",
        )
    if not await user_has_permission(db, current_user.id, required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {required_permission}",
        )
    await service.transition(
        problem,
        payload.status.value,
        current_user,
        required_permission=required_permission,
    )
    return await _problem_response(db, await _get_problem_or_404(db, problem_id))


@router.post("/problems/{problem_id}/assign", response_model=ProblemResponse)
async def assign_problem(
    problem_id: UUID,
    payload: ProblemAssign,
    current_user: Annotated[User, Depends(require_permission("problem.assign"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemResponse:
    problem = await _get_problem_or_404(db, problem_id)
    owner = await db.get(User, payload.owner_id)
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=400, detail="Invalid owner_id")
    problem.owner_id = payload.owner_id
    problem.updated_by = current_user.id
    await db.commit()
    await db.refresh(problem)
    return await _problem_response(db, await _get_problem_or_404(db, problem_id))


# ==========================================================
# Known Errors
# ==========================================================


@router.get("/problems/{problem_id}/known-errors", response_model=KnownErrorListResponse)
async def list_known_errors(
    problem_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnownErrorListResponse:
    await _get_problem_or_404(db, problem_id)
    items = (
        await db.scalars(
            select(KnownError)
            .where(
                KnownError.problem_id == problem_id, KnownError.is_deleted.is_(False)
            )
            .order_by(KnownError.created_at.desc())
        )
    ).all()
    return KnownErrorListResponse(
        items=items, total=len(items), page=1, page_size=len(items) or 1
    )


@router.post(
    "/problems/{problem_id}/known-errors",
    response_model=KnownErrorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_known_error(
    problem_id: UUID,
    payload: KnownErrorCreate,
    current_user: Annotated[
        User, Depends(require_permission("problem.known_error_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnownError:
    if payload.problem_id != problem_id:
        raise HTTPException(status_code=400, detail="problem_id mismatch")
    await _get_problem_or_404(db, problem_id)
    if payload.workaround_id is not None:
        workaround = await db.get(Workaround, payload.workaround_id)
        if (
            workaround is None
            or workaround.is_deleted
            or workaround.problem_id != problem_id
        ):
            raise HTTPException(status_code=400, detail="Invalid workaround_id")

    known_error = KnownError(**payload.model_dump(), created_by=current_user.id)
    db.add(known_error)
    await db.commit()
    await db.refresh(known_error)
    return known_error


@router.put("/known-errors/{known_error_id}", response_model=KnownErrorResponse)
async def update_known_error(
    known_error_id: UUID,
    payload: KnownErrorUpdate,
    current_user: Annotated[
        User, Depends(require_permission("problem.known_error_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnownError:
    known_error = await _get_known_error_or_404(db, known_error_id)
    if payload.workaround_id is not None:
        workaround = await db.get(Workaround, payload.workaround_id)
        if (
            workaround is None
            or workaround.is_deleted
            or workaround.problem_id != known_error.problem_id
        ):
            raise HTTPException(status_code=400, detail="Invalid workaround_id")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(known_error, field, value)
    known_error.updated_by = current_user.id
    await db.commit()
    await db.refresh(known_error)
    return known_error


@router.delete("/known-errors/{known_error_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_known_error(
    known_error_id: UUID,
    current_user: Annotated[
        User, Depends(require_permission("problem.known_error_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    known_error = await _get_known_error_or_404(db, known_error_id)
    known_error.is_deleted = True
    known_error.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Problem <-> Incident linking
# ==========================================================


@router.get(
    "/problems/{problem_id}/incidents", response_model=ProblemIncidentLinkListResponse
)
async def list_problem_incidents(
    problem_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemIncidentLinkListResponse:
    await _get_problem_or_404(db, problem_id)
    items = (
        await db.scalars(
            select(ProblemIncidentLink)
            .where(
                ProblemIncidentLink.problem_id == problem_id,
                ProblemIncidentLink.is_deleted.is_(False),
            )
            .options(selectinload(ProblemIncidentLink.linked_by))
            .order_by(ProblemIncidentLink.linked_at.desc())
        )
    ).all()
    return ProblemIncidentLinkListResponse(items=items, total=len(items))


@router.post(
    "/problems/{problem_id}/incidents",
    response_model=ProblemIncidentLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_problem_incident(
    problem_id: UUID,
    payload: ProblemIncidentLinkCreate,
    current_user: Annotated[
        User, Depends(require_permission("problem.link_incident"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProblemIncidentLink:
    if payload.problem_id != problem_id:
        raise HTTPException(status_code=400, detail="problem_id mismatch")
    await _get_problem_or_404(db, problem_id)
    ticket = await db.get(Ticket, payload.ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status_code=400, detail="Invalid ticket_id")

    existing = await db.scalar(
        select(ProblemIncidentLink).where(
            ProblemIncidentLink.problem_id == problem_id,
            ProblemIncidentLink.ticket_id == payload.ticket_id,
            ProblemIncidentLink.is_deleted.is_(False),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Incident already linked")

    link = ProblemIncidentLink(
        problem_id=problem_id,
        ticket_id=payload.ticket_id,
        note=payload.note,
        linked_by_id=current_user.id,
        created_by=current_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return await db.scalar(
        select(ProblemIncidentLink)
        .where(ProblemIncidentLink.id == link.id)
        .options(selectinload(ProblemIncidentLink.linked_by))
    )


@router.delete(
    "/problems/{problem_id}/incidents/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_problem_incident(
    problem_id: UUID,
    ticket_id: UUID,
    current_user: Annotated[
        User, Depends(require_permission("problem.link_incident"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    link = await db.scalar(
        select(ProblemIncidentLink).where(
            ProblemIncidentLink.problem_id == problem_id,
            ProblemIncidentLink.ticket_id == ticket_id,
            ProblemIncidentLink.is_deleted.is_(False),
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    link.is_deleted = True
    link.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Workarounds
# ==========================================================


@router.get("/problems/{problem_id}/workarounds", response_model=WorkaroundListResponse)
async def list_workarounds(
    problem_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkaroundListResponse:
    await _get_problem_or_404(db, problem_id)
    items = (
        await db.scalars(
            select(Workaround)
            .where(
                Workaround.problem_id == problem_id, Workaround.is_deleted.is_(False)
            )
            .options(selectinload(Workaround.creator))
            .order_by(Workaround.created_at.desc())
        )
    ).all()
    return WorkaroundListResponse(items=items, total=len(items))


@router.post(
    "/problems/{problem_id}/workarounds",
    response_model=WorkaroundResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workaround(
    problem_id: UUID,
    payload: WorkaroundCreate,
    current_user: Annotated[
        User, Depends(require_permission("problem.workaround_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workaround:
    if payload.problem_id != problem_id:
        raise HTTPException(status_code=400, detail="problem_id mismatch")
    await _get_problem_or_404(db, problem_id)

    workaround = Workaround(**payload.model_dump(), created_by=current_user.id)
    db.add(workaround)
    await db.commit()
    await db.refresh(workaround)
    return await _get_workaround_or_404(db, workaround.id)


@router.put("/workarounds/{workaround_id}", response_model=WorkaroundResponse)
async def update_workaround(
    workaround_id: UUID,
    payload: WorkaroundUpdate,
    current_user: Annotated[
        User, Depends(require_permission("problem.workaround_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workaround:
    workaround = await _get_workaround_or_404(db, workaround_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workaround, field, value)
    workaround.updated_by = current_user.id
    await db.commit()
    await db.refresh(workaround)
    return await _get_workaround_or_404(db, workaround_id)


@router.delete("/workarounds/{workaround_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workaround(
    workaround_id: UUID,
    current_user: Annotated[
        User, Depends(require_permission("problem.workaround_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    workaround = await _get_workaround_or_404(db, workaround_id)
    workaround.is_deleted = True
    workaround.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Permanent Fixes
# ==========================================================


@router.get(
    "/problems/{problem_id}/permanent-fixes", response_model=PermanentFixListResponse
)
async def list_permanent_fixes(
    problem_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PermanentFixListResponse:
    await _get_problem_or_404(db, problem_id)
    items = (
        await db.scalars(
            select(PermanentFix)
            .where(
                PermanentFix.problem_id == problem_id,
                PermanentFix.is_deleted.is_(False),
            )
            .options(selectinload(PermanentFix.verified_by))
            .order_by(PermanentFix.created_at.desc())
        )
    ).all()
    return PermanentFixListResponse(items=items, total=len(items))


@router.post(
    "/problems/{problem_id}/permanent-fixes",
    response_model=PermanentFixResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_permanent_fix(
    problem_id: UUID,
    payload: PermanentFixCreate,
    current_user: Annotated[
        User, Depends(require_permission("problem.permanent_fix_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PermanentFix:
    if payload.problem_id != problem_id:
        raise HTTPException(status_code=400, detail="problem_id mismatch")
    await _get_problem_or_404(db, problem_id)

    fix = PermanentFix(**payload.model_dump(), created_by=current_user.id)
    db.add(fix)
    await db.commit()
    await db.refresh(fix)
    return await _get_permanent_fix_or_404(db, fix.id)


@router.put("/permanent-fixes/{fix_id}", response_model=PermanentFixResponse)
async def update_permanent_fix(
    fix_id: UUID,
    payload: PermanentFixUpdate,
    current_user: Annotated[
        User, Depends(require_permission("problem.permanent_fix_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PermanentFix:
    fix = await _get_permanent_fix_or_404(db, fix_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(fix, field, value)
    fix.updated_by = current_user.id
    await db.commit()
    await db.refresh(fix)
    return await _get_permanent_fix_or_404(db, fix_id)


@router.delete("/permanent-fixes/{fix_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permanent_fix(
    fix_id: UUID,
    current_user: Annotated[
        User, Depends(require_permission("problem.permanent_fix_manage"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    fix = await _get_permanent_fix_or_404(db, fix_id)
    fix.is_deleted = True
    fix.deleted_by = current_user.id
    await db.commit()


@router.post("/permanent-fixes/{fix_id}/verify", response_model=PermanentFixResponse)
async def verify_permanent_fix(
    fix_id: UUID,
    payload: PermanentFixVerify,
    current_user: Annotated[
        User, Depends(require_permission("problem.permanent_fix_verify"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PermanentFix:
    """Dedicated endpoint (rather than a field on PermanentFixUpdate) so a
    caller with plain `permanent_fix_manage` access can't self-verify or
    impersonate another verifier -- only `permanent_fix_verify` holders can
    set verified_by/verified_at, and it's always the caller's own identity."""
    fix = await _get_permanent_fix_or_404(db, fix_id)
    fix.verified_by_id = current_user.id
    fix.verified_at = datetime.now(timezone.utc)
    fix.updated_by = current_user.id
    await db.commit()
    await db.refresh(fix)
    return await _get_permanent_fix_or_404(db, fix_id)
