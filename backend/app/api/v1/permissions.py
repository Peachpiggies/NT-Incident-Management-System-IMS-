from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.db.models import Permission, User
from app.db.session import get_db

router = APIRouter(tags=["Permissions"])


class PermissionResponse(BaseModel):
    id: UUID
    module: str
    action: str
    code: str
    description: str | None

    model_config = ConfigDict(from_attributes=True)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _current_user: Annotated[User, Depends(get_current_user)],
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
