from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.db.models import Notification, NotificationHistory, NotificationRule, User
from app.db.session import get_db

from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationHistoryListResponse,
    NotificationHistoryResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationRuleCreate,
    NotificationRuleListResponse,
    NotificationRuleResponse,
    NotificationRuleUpdate,
    UnreadCountResponse,
)

router = APIRouter(tags=["Notifications"])


# ==========================================================
# List
# ==========================================================


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationListResponse:
    """List the current user's notifications, paginated."""

    base_filters = (
        Notification.user_id == current_user.id,
        Notification.is_deleted.is_(False),
    )

    total = await db.scalar(
        select(func.count()).select_from(Notification).where(*base_filters)
    )

    unread_count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(*base_filters, Notification.is_read.is_(False))
    )

    items = (
        await db.scalars(
            select(Notification)
            .where(*base_filters)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        total=total or 0,
        unread_count=unread_count or 0,
        page=page,
        page_size=page_size,
    )


# ==========================================================
# Unread Count
# ==========================================================


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UnreadCountResponse:
    """Get the current user's unread notification count (e.g. for a badge)."""

    unread_count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_deleted.is_(False),
            Notification.is_read.is_(False),
        )
    )

    return UnreadCountResponse(unread_count=unread_count or 0)


# ==========================================================
# Mark One Read
# ==========================================================


@router.post(
    "/notifications/{notification_id}/read", response_model=NotificationResponse
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Notification:
    """Mark a single notification as read."""

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


# ==========================================================
# Mark All Read
# ==========================================================


@router.post("/notifications/read-all", response_model=MarkAllReadResponse)
async def mark_all_notifications_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MarkAllReadResponse:
    """Mark all of the current user's unread notifications as read."""

    now = datetime.now(timezone.utc)

    unread = (
        await db.scalars(
            select(Notification).where(
                Notification.user_id == current_user.id,
                Notification.is_deleted.is_(False),
                Notification.is_read.is_(False),
            )
        )
    ).all()

    for notification in unread:
        notification.is_read = True
        notification.read_at = now
        notification.updated_by = current_user.id

    await db.commit()

    return MarkAllReadResponse(updated_count=len(unread))


# ==========================================================
# Dismiss (soft delete)
# ==========================================================


@router.delete(
    "/notifications/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def dismiss_notification(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft-delete (dismiss) a notification."""

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

# ==========================================================
# Notification Rules
# ==========================================================


@router.get("/notifications/rules", response_model=NotificationRuleListResponse)
async def list_notification_rules(
    current_user: Annotated[User, Depends(require_permission("notification.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationRuleListResponse:
    base = select(NotificationRule).where(NotificationRule.is_deleted.is_(False))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.order_by(NotificationRule.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return NotificationRuleListResponse(
        items=items, total=total or 0, page=page, page_size=page_size
    )


@router.post(
    "/notifications/rules",
    response_model=NotificationRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification_rule(
    payload: NotificationRuleCreate,
    current_user: Annotated[User, Depends(require_permission("notification.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationRule:
    rule = NotificationRule(
        name=payload.name,
        event_type=payload.event_type,
        channels=[c.value for c in payload.channels],
        recipient_role_ids=[str(rid) for rid in payload.recipient_role_ids],
        recipient_user_ids=[str(uid) for uid in payload.recipient_user_ids],
        template_id=payload.template_id,
        is_active=payload.is_active,
        created_by=current_user.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/notifications/rules/{rule_id}", response_model=NotificationRuleResponse)
async def update_notification_rule(
    rule_id: UUID,
    payload: NotificationRuleUpdate,
    current_user: Annotated[User, Depends(require_permission("notification.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationRule:
    rule = await db.get(NotificationRule, rule_id)
    if rule is None or rule.is_deleted:
        raise HTTPException(status_code=404, detail="Notification rule not found")

    updates = payload.model_dump(exclude_unset=True)
    if "channels" in updates and updates["channels"] is not None:
        updates["channels"] = [c.value if hasattr(c, "value") else c for c in updates["channels"]]
    if "recipient_role_ids" in updates and updates["recipient_role_ids"] is not None:
        updates["recipient_role_ids"] = [str(rid) for rid in updates["recipient_role_ids"]]
    if "recipient_user_ids" in updates and updates["recipient_user_ids"] is not None:
        updates["recipient_user_ids"] = [str(uid) for uid in updates["recipient_user_ids"]]
    for field, value in updates.items():
        setattr(rule, field, value)
    rule.updated_by = current_user.id
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete(
    "/notifications/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_notification_rule(
    rule_id: UUID,
    current_user: Annotated[User, Depends(require_permission("notification.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    rule = await db.get(NotificationRule, rule_id)
    if rule is None or rule.is_deleted:
        raise HTTPException(status_code=404, detail="Notification rule not found")
    rule.is_deleted = True
    rule.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Notification History
# ==========================================================


@router.get("/notifications/history", response_model=NotificationHistoryListResponse)
async def list_notification_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> NotificationHistoryListResponse:
    """The caller's own delivery history across all channels. A holder of
    `notification.manage` may additionally pass no filter and still only
    sees their own rows here -- there's no separate "view everyone's
    history" endpoint yet, by design: delivery logs contain contact details
    (phone/email) and are treated as personal data."""
    base = select(NotificationHistory).where(
        NotificationHistory.recipient_user_id == current_user.id,
        NotificationHistory.is_deleted.is_(False),
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.order_by(NotificationHistory.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return NotificationHistoryListResponse(
        items=items, total=total or 0, page=page, page_size=page_size
    )
