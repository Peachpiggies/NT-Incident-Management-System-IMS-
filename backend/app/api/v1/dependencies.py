from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models import Permission, RolePermission, Ticket, User, UserRole
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Security(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await db.get(User, decode_access_token(token))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return user


async def user_has_permission(
    db: AsyncSession, user_id: UUID, permission_code: str
) -> bool:
    statement = (
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            Permission.code == permission_code,
            Permission.is_deleted.is_(False),
            RolePermission.is_deleted.is_(False),
            UserRole.is_deleted.is_(False),
        )
        .limit(1)
    )
    return (await db.scalar(statement)) is not None


async def ticket_read_scope(db: AsyncSession, user_id: UUID) -> Literal["all", "own"]:
    """Return the ticket visibility granted by PBAC, or reject the request.

    Ownership is a resource attribute, not a role.  A caller can read an owned
    ticket only with ``ticket.read_own``; viewing another user's ticket always
    requires ``ticket.read_all``.
    """
    if await user_has_permission(db, user_id, "ticket.read_all"):
        return "all"
    if await user_has_permission(db, user_id, "ticket.read_own"):
        return "own"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Missing permission: ticket.read_own or ticket.read_all",
    )


async def require_ticket_read(db: AsyncSession, user: User, ticket: Ticket) -> None:
    """Enforce the read policy for one ticket without consulting a user role."""
    scope = await ticket_read_scope(db, user.id)
    if scope == "all" or ticket.requester_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def require_permission(permission_code: str):
    """Authorize against database permissions, not a hard-coded role list."""

    async def permission_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if not await user_has_permission(db, current_user.id, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_code}",
            )
        return current_user

    return permission_dependency
