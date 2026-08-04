from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models import Permission, RolePermission, User, UserRole
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: Annotated[str, Security(oauth2_scheme)], db: Annotated[AsyncSession, Depends(get_db)]) -> User:
    user = await db.get(User, decode_access_token(token))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user


async def user_has_permission(db: AsyncSession, user_id, permission_code: str) -> bool:
    statement = (
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, Permission.code == permission_code, Permission.is_deleted.is_(False), RolePermission.is_deleted.is_(False), UserRole.is_deleted.is_(False))
        .limit(1)
    )
    return (await db.scalar(statement)) is not None


def require_permission(permission_code: str):
    """Authorize against database permissions, not a hard-coded role list."""
    async def permission_dependency(current_user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]) -> User:
        if not await user_has_permission(db, current_user.id, permission_code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission_code}")
        return current_user

    return permission_dependency
