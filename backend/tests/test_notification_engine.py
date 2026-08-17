"""Notification Engine tests: rule-matched dispatch across in-app/email/SMS,
graceful degradation when a channel is unconfigured, the rules CRUD API,
and SLA-escalation-triggered dispatch."""

import asyncio
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.models import (
    Base,
    Department,
    Notification,
    NotificationHistory,
    NotificationRule,
    Permission,
    Role,
    RolePermission,
    SLAEscalationTrigger,
    SLAPolicy,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.services import notification_engine

PASSWORD = "Secure-password-123!"


@dataclass
class Seed:
    recipient: User
    manager: User


async def _create_harness(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'notif.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as db:
        manager_role = Role(code="notif-manager", name="Notif Manager", is_system=True)
        agent_role = Role(code="notif-agent", name="Notif Agent", is_system=True)
        permission = Permission(
            module="notification", action="manage", code="notification.manage"
        )
        department = Department(code="OPS2", name="Operations 2")

        recipient = User(
            username="notif-recipient",
            email="notif-recipient@example.com",
            first_name="Rec",
            last_name="Ipient",
            phone="+15550001111",
            password_hash=hash_password(PASSWORD),
            department=department,
        )
        manager = User(
            username="notif-manager",
            email="notif-manager@example.com",
            first_name="Man",
            last_name="Ager",
            password_hash=hash_password(PASSWORD),
            department=department,
        )

        db.add_all([manager_role, agent_role, permission, department, recipient, manager])
        await db.flush()

        db.add_all(
            [
                UserRole(user_id=recipient.id, role_id=agent_role.id),
                UserRole(user_id=manager.id, role_id=manager_role.id),
                RolePermission(role_id=manager_role.id, permission_id=permission.id),
            ]
        )
        await db.commit()
        return engine, sessions, Seed(recipient, manager)


def _token(client, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ==========================================================
# dispatch() core behavior
# ==========================================================


def test_dispatch_delivers_in_app_and_reports_unconfigured_channels(tmp_path):
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    async def scenario():
        async with sessions() as db:
            db.add(
                NotificationRule(
                    name="Test event",
                    event_type="test.event",
                    channels=["in_app", "email", "sms"],
                    recipient_role_ids=[],
                    recipient_user_ids=[str(seed.recipient.id)],
                    is_active=True,
                )
            )
            await db.commit()

            history = await notification_engine.dispatch(
                db,
                "test.event",
                title="Hello",
                message="World",
            )

            by_channel = {h.channel: h for h in history}
            assert by_channel["in_app"].status == "sent"
            # SMTP/Twilio are unconfigured in the test environment, so both
            # should fail cleanly (not raise, not silently pretend success).
            assert by_channel["email"].status == "failed"
            assert by_channel["email"].error_message
            assert by_channel["sms"].status == "failed"
            assert by_channel["sms"].error_message

            notifications = (
                await db.scalars(
                    select(Notification).where(Notification.user_id == seed.recipient.id)
                )
            ).all()
            assert len(notifications) == 1
            assert notifications[0].title == "Hello"

    asyncio.run(scenario())
    asyncio.run(engine.dispose())


def test_dispatch_sms_reports_missing_phone_number(tmp_path):
    engine, sessions, _seed = asyncio.run(_create_harness(tmp_path))

    async def scenario():
        async with sessions() as db:
            no_phone_user = User(
                username="no-phone",
                email="no-phone@example.com",
                first_name="No",
                last_name="Phone",
                password_hash=hash_password(PASSWORD),
            )
            db.add(no_phone_user)
            await db.flush()
            db.add(
                NotificationRule(
                    name="SMS only",
                    event_type="test.sms_only",
                    channels=["sms"],
                    recipient_role_ids=[],
                    recipient_user_ids=[str(no_phone_user.id)],
                    is_active=True,
                )
            )
            await db.commit()

            history = await notification_engine.dispatch(
                db, "test.sms_only", title="T", message="M"
            )
            assert len(history) == 1
            assert history[0].status == "failed"
            assert "phone" in history[0].error_message.lower()

    asyncio.run(scenario())
    asyncio.run(engine.dispose())


def test_dispatch_ignores_inactive_rules(tmp_path):
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    async def scenario():
        async with sessions() as db:
            db.add(
                NotificationRule(
                    name="Disabled",
                    event_type="test.disabled",
                    channels=["in_app"],
                    recipient_role_ids=[],
                    recipient_user_ids=[str(seed.recipient.id)],
                    is_active=False,
                )
            )
            await db.commit()
            history = await notification_engine.dispatch(
                db, "test.disabled", title="T", message="M"
            )
            assert history == []

    asyncio.run(scenario())
    asyncio.run(engine.dispose())


def test_sms_sender_succeeds_when_twilio_configured(tmp_path, monkeypatch):
    """With Twilio credentials set and the HTTP call mocked out, the SMS
    channel should report success rather than 'not configured'."""
    from app.core.config import settings
    from app.services import senders

    monkeypatch.setattr(settings, "twilio_account_sid", "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "twilio_from_number", "+15551234567")

    class _FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(senders.urllib.request, "urlopen", lambda *a, **k: _FakeResponse())

    result = senders.sms_sender.send("+15559998888", "test body")
    assert result.ok is True
    assert result.error is None


# ==========================================================
# Notification Rules API
# ==========================================================


def test_notification_rules_crud_requires_permission(tmp_path):
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    from fastapi.testclient import TestClient

    from app.api.v1.dependencies import get_db
    from app.main import app

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            agent_token = _token(client, seed.recipient.email)
            manager_token = _token(client, seed.manager.email)

            # Agent (no notification.manage) is forbidden
            forbidden = client.post(
                "/api/v1/notifications/rules",
                headers=_headers(agent_token),
                json={
                    "name": "Agent rule",
                    "event_type": "test.agent",
                    "channels": ["in_app"],
                },
            )
            assert forbidden.status_code == 403

            created = client.post(
                "/api/v1/notifications/rules",
                headers=_headers(manager_token),
                json={
                    "name": "Manager rule",
                    "event_type": "test.manager",
                    "channels": ["email", "sms"],
                    "recipient_user_ids": [str(seed.recipient.id)],
                },
            )
            assert created.status_code == 201, created.text
            rule_id = created.json()["id"]
            assert set(created.json()["channels"]) == {"email", "sms"}

            listed = client.get(
                "/api/v1/notifications/rules", headers=_headers(manager_token)
            )
            assert listed.status_code == 200
            assert listed.json()["total"] == 1

            updated = client.put(
                f"/api/v1/notifications/rules/{rule_id}",
                headers=_headers(manager_token),
                json={"is_active": False},
            )
            assert updated.status_code == 200
            assert updated.json()["is_active"] is False

            deleted = client.delete(
                f"/api/v1/notifications/rules/{rule_id}", headers=_headers(manager_token)
            )
            assert deleted.status_code == 204

            after_delete = client.get(
                "/api/v1/notifications/rules", headers=_headers(manager_token)
            )
            assert after_delete.json()["total"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_notification_history_is_scoped_to_caller(tmp_path):
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    from fastapi.testclient import TestClient

    from app.api.v1.dependencies import get_db
    from app.main import app

    async def seed_history():
        async with sessions() as db:
            db.add_all(
                [
                    NotificationHistory(
                        channel="email",
                        recipient_user_id=seed.recipient.id,
                        status="sent",
                    ),
                    NotificationHistory(
                        channel="sms",
                        recipient_user_id=seed.manager.id,
                        status="failed",
                        error_message="no phone",
                    ),
                ]
            )
            await db.commit()

    asyncio.run(seed_history())

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            recipient_token = _token(client, seed.recipient.email)
            response = client.get(
                "/api/v1/notifications/history", headers=_headers(recipient_token)
            )
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert response.json()["items"][0]["channel"] == "email"
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


# ==========================================================
# SLA escalation -> notification dispatch wiring
# ==========================================================


def test_dispatch_escalation_delivers_to_configured_channels(tmp_path):
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    async def scenario():
        async with sessions() as db:
            status_row = TicketStatus(code="NEW2", name="New", is_active=True)
            category = TicketCategory(code="NET2", name="Network", is_active=True)
            priority = TicketPriority(code="HIGH2", name="High", is_active=True)
            policy = SLAPolicy(code="DEFAULT2", name="Default", is_active=True)
            db.add_all([status_row, category, priority, policy])
            await db.flush()

            ticket = Ticket(
                ticket_no="INC-9001",
                title="Server down",
                description="Prod server down",
                category_id=category.id,
                priority_id=priority.id,
                status_id=status_row.id,
                requester_id=seed.recipient.id,
            )
            db.add(ticket)
            await db.flush()

            trigger = SLAEscalationTrigger(
                policy_id=policy.id,
                trigger_on="BREACH",
                notify_user_ids=[str(seed.recipient.id)],
                notify_role_ids=[],
                channels=["in_app", "sms"],
                is_active=True,
            )
            db.add(trigger)
            await db.commit()
            await db.refresh(trigger)
            await db.refresh(ticket)

            created = await notification_engine.dispatch_escalation(
                db, trigger=trigger, ticket=ticket
            )
            assert len(created) == 2
            by_channel = {e.channel: e for e in created}
            assert by_channel["in_app"].status == "sent"
            # SMS unconfigured in test env -> no successful delivery for that channel
            assert by_channel["sms"].status == "failed"

            history = (
                await db.scalars(
                    select(NotificationHistory).where(
                        NotificationHistory.escalation_notification_id.in_(
                            [e.id for e in created]
                        )
                    )
                )
            ).all()
            assert len(history) == 2

    asyncio.run(scenario())
    asyncio.run(engine.dispose())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
