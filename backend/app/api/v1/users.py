from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.core.security import hash_password
from app.db.models import Role, User, UserRole
from app.db.session import get_db

router = APIRouter(tags=["Users"])


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    department_id: UUID | None
    is_active: bool
    role_codes: list[str] = Field(default_factory=list)


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str
    first_name: str
    last_name: str
    password: str = Field(..., min_length=12)
    department_id: UUID | None = None
    role_codes: list[str] = Field(default_factory=lambda: ["customer"])


class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = Field(default=None, min_length=12)
    department_id: UUID | None = None
    is_active: bool | None = None
    role_codes: list[str] | None = None


async def _response(db: AsyncSession, user: User) -> UserResponse:
    codes = (
        await db.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, UserRole.is_deleted.is_(False))
        )
    ).all()
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        department_id=user.department_id,
        is_active=user.is_active,
        role_codes=codes,
    )


async def _assign_roles(db: AsyncSession, user: User, codes: list[str]) -> None:
    roles = (
        await db.scalars(
            select(Role).where(Role.code.in_(codes), Role.is_deleted.is_(False))
        )
    ).all()
    if len(roles) != len(set(codes)):
        raise HTTPException(status_code=400, detail="Unknown role code")
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))


async def _replace_roles(
    db: AsyncSession, user: User, codes: list[str], actor_id: UUID
) -> None:
    """Soft-delete previous assignments so the audit trail remains intact."""
    existing = (
        await db.scalars(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.is_deleted.is_(False)
            )
        )
    ).all()
    for assignment in existing:
        assignment.is_deleted = True
        assignment.deleted_at = datetime.now(timezone.utc)
        assignment.deleted_by = actor_id
        assignment.updated_by = actor_id
    await _assign_roles(db, user, codes)


@router.get("/users/me", response_model=UserResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return await _response(db, current_user)


@router.get("/roles")
async def list_roles(db: Annotated[AsyncSession, Depends(get_db)]) -> list[str]:
    return (
        await db.scalars(
            select(Role.code).where(Role.is_deleted.is_(False)).order_by(Role.code)
        )
    ).all()


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserResponse]:
    return [
        await _response(db, user)
        for user in (
            await db.scalars(select(User).where(User.is_deleted.is_(False)))
        ).all()
    ]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    if await db.scalar(
        select(User).where(
            (User.email == payload.email.lower()) | (User.username == payload.username)
        )
    ):
        raise HTTPException(status_code=409, detail="Email or username already exists")
    data = payload.model_dump(exclude={"password", "role_codes"})
    user = User(
        **data,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        created_by=current_user.id,
    )
    db.add(user)
    await db.flush()
    await _assign_roles(db, user, payload.role_codes)
    await db.commit()
    return await _response(db, user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    current_user: Annotated[User, Depends(require_permission("user.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    user = await db.get(User, user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True, exclude={"password", "role_codes"})
    if "email" in updates and updates["email"] is not None:
        email = updates["email"].lower()
        duplicate = await db.scalar(
            select(User).where(User.email == email, User.id != user.id)
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Email already exists")
        updates["email"] = email
    if "username" in updates and updates["username"] is not None:
        duplicate = await db.scalar(
            select(User).where(User.username == updates["username"], User.id != user.id)
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Username already exists")
    for key, value in updates.items():
        setattr(user, key, value)
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role_codes is not None:
        await _replace_roles(db, user, payload.role_codes, current_user.id)
    user.updated_by = current_user.id
    await db.commit()
    return await _response(db, user)
