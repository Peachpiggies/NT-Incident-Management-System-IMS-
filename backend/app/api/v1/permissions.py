"""Permission and role-permission administration APIs."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_permission
from app.db.models import ActivityLog, Permission, Role, RolePermission, User
from app.db.session import get_db

router = APIRouter(tags=["Permissions"])


class PermissionRequest(BaseModel):
    module: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_]+$")
    action: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_]+$")
    code: str = Field(min_length=5, max_length=200, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")
    description: str | None = None


class PermissionResponse(PermissionRequest):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RolePermissionResponse(BaseModel):
    id: UUID
    role_id: UUID
    permission: PermissionResponse
    created_at: datetime


async def _permission_or_404(db: AsyncSession, permission_id: UUID) -> Permission:
    permission = await db.scalar(
        select(Permission).where(
            Permission.id == permission_id, Permission.is_deleted.is_(False)
        )
    )
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found"
        )
    return permission


async def _role_or_404(db: AsyncSession, role_id: UUID) -> Role:
    role = await db.scalar(
        select(Role).where(Role.id == role_id, Role.is_deleted.is_(False))
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return role


def _validate_permission_code(payload: PermissionRequest) -> None:
    if payload.code != f"{payload.module}.{payload.action}":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Permission code must equal module.action",
        )


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Permission]:
    return list(
        (
            await db.scalars(
                select(Permission)
                .where(Permission.is_deleted.is_(False))
                .order_by(Permission.module, Permission.action)
            )
        ).all()
    )


@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_permission(
    payload: PermissionRequest,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Permission:
    _validate_permission_code(payload)
    if await db.scalar(select(Permission).where(Permission.code == payload.code)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permission code already exists",
        )
    permission = Permission(**payload.model_dump(), created_by=current_user.id)
    db.add(permission)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="permission",
            action="create",
            resource="permission",
            resource_id=permission.id,
        )
    )
    await db.commit()
    await db.refresh(permission)
    return permission


@router.get("/permissions/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Permission:
    return await _permission_or_404(db, permission_id)


@router.patch("/permissions/{permission_id}", response_model=PermissionResponse)
async def update_permission(
    permission_id: UUID,
    payload: PermissionRequest,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Permission:
    permission = await _permission_or_404(db, permission_id)
    _validate_permission_code(payload)
    duplicate = await db.scalar(
        select(Permission).where(
            Permission.code == payload.code, Permission.id != permission.id
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permission code already exists",
        )
    for field, value in payload.model_dump().items():
        setattr(permission, field, value)
    permission.updated_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="permission",
            action="update",
            resource="permission",
            resource_id=permission.id,
        )
    )
    await db.commit()
    await db.refresh(permission)
    return permission


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: UUID,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    permission = await _permission_or_404(db, permission_id)
    now = datetime.now(timezone.utc)
    permission.is_deleted = True
    permission.deleted_at = now
    permission.deleted_by = current_user.id
    assignments = list(
        (
            await db.scalars(
                select(RolePermission).where(
                    RolePermission.permission_id == permission.id,
                    RolePermission.is_deleted.is_(False),
                )
            )
        ).all()
    )
    for assignment in assignments:
        assignment.is_deleted = True
        assignment.deleted_at = now
        assignment.deleted_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="permission",
            action="delete",
            resource="permission",
            resource_id=permission.id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles/{role_id}/permissions", response_model=list[RolePermissionResponse])
async def list_role_permissions(
    role_id: UUID,
    _current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RolePermissionResponse]:
    await _role_or_404(db, role_id)
    assignments = list(
        (
            await db.scalars(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.is_deleted.is_(False),
                )
            )
        ).all()
    )
    permissions = {
        permission.id: permission
        for permission in (
            await db.scalars(
                select(Permission).where(
                    Permission.id.in_([item.permission_id for item in assignments]),
                    Permission.is_deleted.is_(False),
                )
            )
        ).all()
    }
    return [
        RolePermissionResponse(
            id=item.id,
            role_id=item.role_id,
            permission=PermissionResponse.model_validate(
                permissions[item.permission_id]
            ),
            created_at=item.created_at,
        )
        for item in assignments
        if item.permission_id in permissions
    ]


@router.post(
    "/roles/{role_id}/permissions/{permission_id}",
    response_model=RolePermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_role_permission(
    role_id: UUID,
    permission_id: UUID,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RolePermissionResponse:
    await _role_or_404(db, role_id)
    permission = await _permission_or_404(db, permission_id)
    assignment = await db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    if assignment and not assignment.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permission is already assigned",
        )
    if assignment:
        assignment.is_deleted = False
        assignment.deleted_at = None
        assignment.deleted_by = None
        assignment.updated_by = current_user.id
    else:
        assignment = RolePermission(
            role_id=role_id, permission_id=permission_id, created_by=current_user.id
        )
        db.add(assignment)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="role_permission",
            action="assign",
            resource="role",
            resource_id=role_id,
            detail={"permission_id": str(permission_id)},
        )
    )
    await db.commit()
    await db.refresh(assignment)
    return RolePermissionResponse(
        id=assignment.id,
        role_id=role_id,
        permission=PermissionResponse.model_validate(permission),
        created_at=assignment.created_at,
    )


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_role_permission(
    role_id: UUID,
    permission_id: UUID,
    current_user: Annotated[User, Depends(require_permission("role.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    assignment = await db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
            RolePermission.is_deleted.is_(False),
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission assignment not found",
        )
    assignment.is_deleted = True
    assignment.deleted_at = datetime.now(timezone.utc)
    assignment.deleted_by = current_user.id
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="role_permission",
            action="remove",
            resource="role",
            resource_id=role_id,
            detail={"permission_id": str(permission_id)},
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
