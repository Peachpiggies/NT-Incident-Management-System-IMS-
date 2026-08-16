"""Notification Engine: a single dispatch path shared by every trigger
(ticket events via `NotificationRule`, SLA escalations via
`SLAEscalationTrigger`) and every channel (in-app, email, SMS, websocket).

Call `dispatch()` for rule-driven notifications (arbitrary `event_type`
strings like "ticket.assigned"). Call `dispatch_escalation()` from the SLA
scheduler, which already knows its own recipients/channels per trigger and
doesn't need rule matching.

Both funnel into `_deliver()`, which is the one place a channel is actually
sent on and a NotificationHistory row is written -- this is what "one
dispatch path" means here: rule matching and escalation triggers decide WHO
gets notified and HOW, but not-WHAT-happens-when-you-actually-send lives in
exactly one function per channel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    EscalationNotification,
    Notification,
    NotificationHistory,
    NotificationRule,
    SLAEscalationTrigger,
    Ticket,
    User,
    UserRole,
)
from app.services.realtime import connection_manager
from app.services.senders import email_sender, sms_sender

logger = logging.getLogger(__name__)

CHANNEL_IN_APP = "in_app"
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"
CHANNEL_WEBSOCKET = "websocket"

STATUS_SENT = "sent"
STATUS_FAILED = "failed"


async def _resolve_recipients(
    db: AsyncSession, *, role_ids: list, user_ids: list
) -> list[User]:
    ids: set[UUID] = {UUID(str(uid)) for uid in user_ids}
    if role_ids:
        role_uuids = [UUID(str(rid)) for rid in role_ids]
        rows = await db.scalars(
            select(UserRole.user_id).where(
                UserRole.role_id.in_(role_uuids), UserRole.is_deleted.is_(False)
            )
        )
        ids.update(rows.all())
    if not ids:
        return []
    users = (
        await db.scalars(
            select(User).where(
                User.id.in_(ids), User.is_active.is_(True), User.is_deleted.is_(False)
            )
        )
    ).all()
    return list(users)


async def _deliver(
    db: AsyncSession,
    *,
    channel: str,
    recipient: User,
    title: str,
    message: str,
    link: str | None,
    notification_id: UUID | None,
    escalation_notification_id: UUID | None,
) -> NotificationHistory:
    """Send on exactly one channel to exactly one recipient, and record the
    outcome as a NotificationHistory row. Never raises -- delivery failures
    on one channel/recipient must not stop the others."""

    status = STATUS_FAILED
    error_message: str | None = None
    sent_at: datetime | None = None
    created_notification_id = notification_id

    try:
        if channel == CHANNEL_IN_APP:
            in_app_notification = Notification(
                user_id=recipient.id,
                title=title,
                message=message,
                type="info",
            )
            db.add(in_app_notification)
            await db.flush()
            created_notification_id = created_notification_id or (
                in_app_notification.id if escalation_notification_id is None else None
            )
            status, sent_at = STATUS_SENT, datetime.now(timezone.utc)

        elif channel == CHANNEL_EMAIL:
            result = email_sender.send(recipient.email, title, message)
            if result.ok:
                status, sent_at = STATUS_SENT, datetime.now(timezone.utc)
            else:
                error_message = result.error

        elif channel == CHANNEL_SMS:
            if not recipient.phone:
                error_message = "Recipient has no phone number on file"
            else:
                result = sms_sender.send(recipient.phone, f"{title}: {message}")
                if result.ok:
                    status, sent_at = STATUS_SENT, datetime.now(timezone.utc)
                else:
                    error_message = result.error

        elif channel == CHANNEL_WEBSOCKET:
            delivered = await connection_manager.send_to_user(
                recipient.id,
                {"title": title, "message": message, "link": link},
            )
            if delivered:
                status, sent_at = STATUS_SENT, datetime.now(timezone.utc)
            else:
                error_message = "Recipient has no live websocket connection"

        else:
            error_message = f"Unknown channel: {channel}"

    except Exception as exc:  # noqa: BLE001 - one bad recipient/channel must not abort dispatch
        logger.exception("Notification delivery failed channel=%s user=%s", channel, recipient.id)
        error_message = str(exc)

    history = NotificationHistory(
        notification_id=created_notification_id,
        escalation_notification_id=escalation_notification_id,
        channel=channel,
        recipient_user_id=recipient.id,
        status=status,
        error_message=error_message,
        sent_at=sent_at,
    )
    db.add(history)
    return history


async def dispatch(
    db: AsyncSession,
    event_type: str,
    *,
    title: str,
    message: str,
    link: str | None = None,
    extra_user_ids: list[UUID] | None = None,
) -> list[NotificationHistory]:
    """Match `event_type` against active NotificationRules and deliver on
    each rule's configured channels to each rule's resolved recipients.
    Commits before returning."""

    rules = (
        await db.scalars(
            select(NotificationRule).where(
                NotificationRule.event_type == event_type,
                NotificationRule.is_active.is_(True),
                NotificationRule.is_deleted.is_(False),
            )
        )
    ).all()

    history: list[NotificationHistory] = []
    for rule in rules:
        recipients = await _resolve_recipients(
            db, role_ids=rule.recipient_role_ids, user_ids=list(rule.recipient_user_ids)
        )
        if extra_user_ids:
            existing_ids = {u.id for u in recipients}
            extra = (
                await db.scalars(
                    select(User).where(
                        User.id.in_(extra_user_ids), User.id.notin_(existing_ids)
                    )
                )
            ).all()
            recipients.extend(extra)

        for recipient in recipients:
            for channel in rule.channels:
                entry = await _deliver(
                    db,
                    channel=channel,
                    recipient=recipient,
                    title=title,
                    message=message,
                    link=link,
                    notification_id=None,
                    escalation_notification_id=None,
                )
                history.append(entry)

    await db.commit()
    return history


async def dispatch_escalation(
    db: AsyncSession,
    *,
    trigger: SLAEscalationTrigger,
    ticket: Ticket,
) -> list[EscalationNotification]:
    """Deliver an already-fired SLA escalation on each of the trigger's
    configured channels, to the trigger's configured recipients. Unlike
    `dispatch()`, there's no rule matching here -- `SLAEscalationTrigger`
    already carries its own channels/recipients (see the trigger's model
    docstring). Commits before returning."""

    recipients = await _resolve_recipients(
        db, role_ids=trigger.notify_role_ids, user_ids=list(trigger.notify_user_ids)
    )
    message = (
        f"SLA {trigger.trigger_on.lower()} on ticket {ticket.ticket_no}: "
        f"{trigger.metric_type or 'response/resolution'} target"
    )
    title = f"SLA {trigger.trigger_on.title()}: {ticket.ticket_no}"

    created: list[EscalationNotification] = []
    for channel in trigger.channels:
        escalation_notification = EscalationNotification(
            ticket_id=ticket.id,
            escalation_trigger_id=trigger.id,
            channel=channel,
            recipient_user_ids=[str(u.id) for u in recipients],
            message=message,
            status=STATUS_FAILED,
        )
        db.add(escalation_notification)
        await db.flush()

        any_sent = False
        for recipient in recipients:
            entry = await _deliver(
                db,
                channel=channel,
                recipient=recipient,
                title=title,
                message=message,
                link=f"/tickets/{ticket.id}",
                notification_id=None,
                escalation_notification_id=escalation_notification.id,
            )
            if entry.status == STATUS_SENT:
                any_sent = True

        if any_sent:
            escalation_notification.status = STATUS_SENT
            escalation_notification.sent_at = datetime.now(timezone.utc)
        elif not recipients:
            escalation_notification.status = STATUS_FAILED
        created.append(escalation_notification)

    await db.commit()
    return created
