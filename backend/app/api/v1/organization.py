"""Department, role and user-role administration APIs."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_permission
from app.db.models import ActivityLog, Department, Role, RolePermission, User, UserRole
from app.db.session import get_db
from app.schemas.references.department import DepartmentCreate, DepartmentResponse
from app.schemas.references.role import RoleCreate, RoleResponse, RoleRequest, UserRoleResponse

router = APIRouter(tags=["Organization"])


async def _department_or_404(db: AsyncSession, department_id: UUID) -> Department:
    department = await db.scalar(
        select(Department).where(
            Department.id == department_id, Department.is_deleted.is_(False)
        )
    )
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )
    return department


async def _role_or_404(db: AsyncSession, role_id: UUID) -> Role:
    role = await db.scalar(
        select(Role).where(Role.id == role_id, Role.is_deleted.is_(False))
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return role


async def _user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id, User.is_deleted.is_(False))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


async def _validate_parent(
    db: AsyncSession, department_id: UUID | None, parent_id: UUID | None
) -> None:
    if parent_id is None:
        return
    if parent_id == department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A department cannot be its own parent",
        )
    parent = await _department_or_404(db, parent_id)
    if not parent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent department is inactive",
        )


@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    _current_user: Annotated[User, Depends(require_permission("department.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Department]:
    return list(
        (
            await db.scalars(
                select(Department)
                .where(Department.is_deleted.is_(False))
                .order_by(Department.code)
            )
        ).all()
    )


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    payload: DepartmentCreate,
    current_user: Annotated[User, Depends(require_permission("department.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Department:
    if await db.scalar(select(Department).where(Department.code == payload.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department code already exists",
        )
    await _validate_parent(db, None, payload.parent_department_id)
    department = Department(**payload.model_dump(), created_by=current_user.id)
    db.add(department)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="department",
            action="create",
            resource="department",
            resource_id=department.id,
        )
    )
    await db.commit()
    await db.refresh(department)
    return department


@router.get("/departments/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("department.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Department:
    return await _department_or_404(db, department_id)


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: UUID,
    payload: DepartmentCreate,
    current_user: Annotated[User, Depends(require_permission("department.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Department:
    department = await _department_or_404(db, department_id)
    duplicate = await db.scalar(
        select(Department).where(
            Department.code == payload.code, Department.id != department.id
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department code already exists",
        )
    await _validate_parent(db, department.id, payload.parent_department_id)
    for field, value in payload.model_dump().items():
        setattr(department, field, value)
    department.updated_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="department",
            action="update",
            resource="department",
            resource_id=department.id,
        )
    )
    await db.commit()
    await db.refresh(department)
    return department


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: UUID,
    current_user: Annotated[User, Depends(require_permission("department.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    department = await _department_or_404(db, department_id)
    has_children = await db.scalar(
        select(Department.id)
        .where(
            Department.parent_department_id == department.id,
            Department.is_deleted.is_(False),
        )
        .limit(1)
    )
    has_users = await db.scalar(
        select(User.id)
        .where(User.department_id == department.id, User.is_deleted.is_(False))
        .limit(1)
    )
    if has_children or has_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Department is still in use"
        )
    department.is_deleted = True
    department.deleted_at = datetime.now(timezone.utc)
    department.deleted_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="department",
            action="delete",
            resource="department",
            resource_id=department.id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    _current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Role]:
    return list(
        (
            await db.scalars(
                select(Role).where(Role.is_deleted.is_(False)).order_by(Role.code)
            )
        ).all()
    )


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Role:
    if await db.scalar(select(Role).where(Role.code == payload.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Role code already exists"
        )
    role = Role(**payload.model_dump(), is_system=False, created_by=current_user.id)
    db.add(role)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="role",
            action="create",
            resource="role",
            resource_id=role.id,
        )
    )
    await db.commit()
    await db.refresh(role)
    return role


@router.get("/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Role:
    return await _role_or_404(db, role_id)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    payload: RoleCreate,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Role:
    role = await _role_or_404(db, role_id)
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be modified",
        )
    duplicate = await db.scalar(
        select(Role).where(Role.code == payload.code, Role.id != role.id)
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Role code already exists"
        )
    for field, value in payload.model_dump().items():
        setattr(role, field, value)
    role.updated_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="role",
            action="update",
            resource="role",
            resource_id=role.id,
        )
    )
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    role = await _role_or_404(db, role_id)
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be deleted",
        )
    now = datetime.now(timezone.utc)
    role.is_deleted = True
    role.deleted_at = now
    role.deleted_by = current_user.id
    assignments = list(
        (
            await db.scalars(
                select(UserRole).where(
                    UserRole.role_id == role.id, UserRole.is_deleted.is_(False)
                )
            )
        ).all()
    )
    permissions = list(
        (
            await db.scalars(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.is_deleted.is_(False),
                )
            )
        ).all()
    )
    for assignment in [*assignments, *permissions]:
        assignment.is_deleted = True
        assignment.deleted_at = now
        assignment.deleted_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="role",
            action="delete",
            resource="role",
            resource_id=role.id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/roles", response_model=list[UserRoleResponse])
async def list_user_roles(
    user_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserRoleResponse]:
    await _user_or_404(db, user_id)
    assignments = list(
        (
            await db.scalars(
                select(UserRole).where(
                    UserRole.user_id == user_id, UserRole.is_deleted.is_(False)
                )
            )
        ).all()
    )
    roles = {
        role.id: role
        for role in (
            await db.scalars(
                select(Role).where(
                    Role.id.in_([item.role_id for item in assignments]),
                    Role.is_deleted.is_(False),
                )
            )
        ).all()
    }
    return [
        UserRoleResponse(
            id=item.id,
            user_id=item.user_id,
            role=RoleResponse.model_validate(roles[item.role_id]),
            created_at=item.created_at,
        )
        for item in assignments
        if item.role_id in roles
    ]


@router.post(
    "/users/{user_id}/roles/{role_id}",
    response_model=UserRoleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_user_role(
    user_id: UUID,
    role_id: UUID,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRoleResponse:
    await _user_or_404(db, user_id)
    role = await _role_or_404(db, role_id)
    assignment = await db.scalar(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
    )
    if assignment and not assignment.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Role is already assigned"
        )
    if assignment:
        assignment.is_deleted = False
        assignment.deleted_at = None
        assignment.deleted_by = None
        assignment.updated_by = current_user.id
    else:
        assignment = UserRole(
            user_id=user_id, role_id=role_id, created_by=current_user.id
        )
        db.add(assignment)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="user_role",
            action="assign",
            resource="user",
            resource_id=user_id,
            detail={"role_id": str(role_id)},
        )
    )
    await db.commit()
    await db.refresh(assignment)
    return UserRoleResponse(
        id=assignment.id,
        user_id=user_id,
        role=RoleResponse.model_validate(role),
        created_at=assignment.created_at,
    )


@router.delete(
    "/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_user_role(
    user_id: UUID,
    role_id: UUID,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    assignment = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.is_deleted.is_(False),
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role assignment not found"
        )
    assignment.is_deleted = True
    assignment.deleted_at = datetime.now(timezone.utc)
    assignment.deleted_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="user_role",
            action="remove",
            resource="user",
            resource_id=user_id,
            detail={"role_id": str(role_id)},
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)