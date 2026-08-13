"""PBAC-protected user management with UUID-only contracts."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.core.security import hash_password
from app.db.models import ActivityLog, Department, RefreshToken, Role, User, UserRole
from app.db.session import get_db
from app.schemas.references.department import DepartmentSummary
from app.schemas.references.role import RoleSummary
from app.schemas.references.user import (

    UserCreateRequest,

    UserResponse,

    UserUpdateRequest

)

router = APIRouter(tags=["Users"])


async def _get_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id, User.is_deleted.is_(False))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


async def _active_department_or_400(
    db: AsyncSession, department_id: UUID | None
) -> None:
    if department_id is None:
        return
    department = await db.scalar(
        select(Department).where(
            Department.id == department_id,
            Department.is_active.is_(True),
            Department.is_deleted.is_(False),
        )
    )
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department"
        )


async def _roles_or_400(db: AsyncSession, role_ids: list[UUID]) -> list[Role]:
    unique_ids = set(role_ids)
    if len(unique_ids) != len(role_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate role ID"
        )
    roles = list(
        (
            await db.scalars(
                select(Role).where(Role.id.in_(unique_ids), Role.is_deleted.is_(False))
            )
        ).all()
    )
    if len(roles) != len(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role"
        )
    return roles


async def _replace_roles(
    db: AsyncSession, user: User, role_ids: list[UUID], actor_id: UUID
) -> None:
    """Synchronize `user_roles` without losing the audit trail to soft deletes."""
    roles = await _roles_or_400(db, role_ids)
    assignments = list(
        (await db.scalars(select(UserRole).where(UserRole.user_id == user.id))).all()
    )
    by_role_id = {assignment.role_id: assignment for assignment in assignments}
    requested = {role.id for role in roles}
    now = datetime.now(timezone.utc)

    for assignment in assignments:
        if assignment.role_id not in requested and not assignment.is_deleted:
            assignment.is_deleted = True
            assignment.deleted_at = now
            assignment.deleted_by = actor_id
            assignment.updated_by = actor_id

    for role in roles:
        assignment = by_role_id.get(role.id)
        if assignment is None:
            db.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        elif assignment.is_deleted:
            assignment.is_deleted = False
            assignment.deleted_at = None
            assignment.deleted_by = None
            assignment.updated_by = actor_id


async def _response(db: AsyncSession, user: User) -> UserResponse:
    department = (
        await db.scalar(
            select(Department).where(
                Department.id == user.department_id, Department.is_deleted.is_(False)
            )
        )
        if user.department_id
        else None
    )
    roles = list(
        (
            await db.scalars(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(
                    UserRole.user_id == user.id,
                    UserRole.is_deleted.is_(False),
                    Role.is_deleted.is_(False),
                )
                .order_by(Role.code)
            )
        ).all()
    )
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        employee_code=user.employee_code,
        phone=user.phone,
        department=DepartmentSummary.model_validate(department) if department else None,
        roles=[RoleSummary.model_validate(role) for role in roles],
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _assert_unique(
    db: AsyncSession,
    payload: UserCreateRequest | UserUpdateRequest,
    user_id: UUID | None = None,
) -> None:
    if payload.email is not None:
        statement = select(User).where(User.email == payload.email.lower())
        if user_id:
            statement = statement.where(User.id != user_id)
        if await db.scalar(statement):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
            )
    if payload.username is not None:
        statement = select(User).where(User.username == payload.username)
        if user_id:
            statement = statement.where(User.id != user_id)
        if await db.scalar(statement):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
            )


@router.get("/users/me", response_model=UserResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return await _response(db, current_user)


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserResponse]:
    users = list(
        (
            await db.scalars(
                select(User).where(User.is_deleted.is_(False)).order_by(User.username)
            )
        ).all()
    )
    return [await _response(db, user) for user in users]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return await _response(db, await _get_user_or_404(db, user_id))


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    await _assert_unique(db, payload)
    await _active_department_or_400(db, payload.department_id)
    user = User(
        username=payload.username,
        email=payload.email.lower(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=hash_password(payload.password),
        employee_code=payload.employee_code,
        phone=payload.phone,
        department_id=payload.department_id,
        created_by=current_user.id,
    )
    db.add(user)
    await db.flush()
    await _replace_roles(db, user, payload.role_ids, current_user.id)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="user",
            action="create",
            resource="user",
            resource_id=user.id,
        )
    )
    await db.commit()
    await db.refresh(user)
    return await _response(db, user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    user = await _get_user_or_404(db, user_id)
    await _assert_unique(db, payload, user.id)
    changes = payload.model_dump(exclude_unset=True, exclude={"role_ids"})
    if "email" in changes and changes["email"] is not None:
        changes["email"] = changes["email"].lower()
    if "department_id" in changes:
        await _active_department_or_400(db, changes["department_id"])
    for field, value in changes.items():
        setattr(user, field, value)
    if payload.role_ids is not None:
        await _replace_roles(db, user, payload.role_ids, current_user.id)
    user.updated_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="user",
            action="update",
            resource="user",
            resource_id=user.id,
        )
    )
    await db.commit()
    await db.refresh(user)
    return await _response(db, user)


async def _set_active(
    user: User, is_active: bool, actor: User, db: AsyncSession
) -> UserResponse:
    if user.id == actor.id and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    user.is_active = is_active
    user.updated_by = actor.id
    if not is_active:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
    db.add(
        ActivityLog(
            user_id=actor.id,
            module="user",
            action="activate" if is_active else "deactivate",
            resource="user",
            resource_id=user.id,
        )
    )
    await db.commit()
    await db.refresh(user)
    return await _response(db, user)


@router.post("/users/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return await _set_active(
        await _get_user_or_404(db, user_id), True, current_user, db
    )


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return await _set_active(
        await _get_user_or_404(db, user_id), False, current_user, db
    )
