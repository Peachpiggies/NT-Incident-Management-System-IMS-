from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.db.models import Notification, User
from app.db.session import get_db

router = APIRouter(tags=["Notifications"])


class NotificationResponse(BaseModel):
    id: UUID
    title: str
    message: str
    type: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Notification]:
    return (
        await db.scalars(
            select(Notification)
            .where(
                Notification.user_id == current_user.id,
                Notification.is_deleted.is_(False),
            )
            .order_by(Notification.created_at.desc())
        )
    ).all()


@router.post(
    "/notifications/{notification_id}/read", response_model=NotificationResponse
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Notification:
    notification = await db.get(Notification, notification_id)
    if (
        not notification
        or notification.user_id != current_user.id
        or notification.is_deleted
    ):
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    notification.updated_by = current_user.id
    await db.commit()
    await db.refresh(notification)
    return notification


@router.delete(
    "/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def dismiss_notification(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    notification = await db.get(Notification, notification_id)
    if (
        not notification
        or notification.user_id != current_user.id
        or notification.is_deleted
    ):
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_deleted = True
    notification.deleted_at = datetime.now(timezone.utc)
    notification.deleted_by = current_user.id
    await db.commit()
