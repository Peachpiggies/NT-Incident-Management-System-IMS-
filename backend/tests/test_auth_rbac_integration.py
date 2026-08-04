import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.auth import RefreshRequest, UserRegisterRequest, refresh, register
from app.api.v1.dependencies import (
    require_permission,
    require_ticket_read,
    ticket_read_scope,
    user_has_permission,
)
from app.db.models import (
    Base,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    Ticket,
    User,
    UserRole,
)


async def _session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'integration.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_auth_rotation_and_reuse_revokes_all_sessions(tmp_path) -> None:
    async def scenario() -> None:
        engine, sessions = await _session_factory(tmp_path)
        async with sessions() as session:
            customer = Role(code="customer", name="Customer", is_system=True)
            session.add(customer)
            await session.commit()
            created = await register(
                UserRegisterRequest(
                    email="customer@example.com",
                    full_name="Test Customer",
                    password="secure-password-123",
                ),
                session,
            )
            first_refresh = created.refresh_token
            rotated = await refresh(
                RefreshRequest(refresh_token=first_refresh), session
            )
            assert rotated.refresh_token != first_refresh
            with pytest.raises(HTTPException, match="reuse detected"):
                await refresh(RefreshRequest(refresh_token=first_refresh), session)
            active = await session.scalars(
                select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
            )
            assert list(active) == []
        await engine.dispose()

    asyncio.run(scenario())


def test_database_permission_check_allows_only_granted_user(tmp_path) -> None:
    async def scenario() -> None:
        engine, sessions = await _session_factory(tmp_path)
        async with sessions() as session:
            role = Role(code="dispatcher", name="Dispatcher", is_system=False)
            permission = Permission(
                module="ticket", action="assign", code="ticket.assign"
            )
            allowed = User(
                username="allowed",
                email="allowed@example.com",
                first_name="Allowed",
                last_name="User",
                password_hash="hash",
            )
            denied = User(
                username="denied",
                email="denied@example.com",
                first_name="Denied",
                last_name="User",
                password_hash="hash",
            )
            session.add_all([role, permission, allowed, denied])
            await session.flush()
            session.add_all(
                [
                    RolePermission(role_id=role.id, permission_id=permission.id),
                    UserRole(user_id=allowed.id, role_id=role.id),
                ]
            )
            await session.commit()

            assert await user_has_permission(session, allowed.id, "ticket.assign")
            assert not await user_has_permission(session, denied.id, "ticket.assign")
            dependency = require_permission("ticket.assign")
            assert await dependency(allowed, session) == allowed
            with pytest.raises(HTTPException, match="Missing permission"):
                await dependency(denied, session)
        await engine.dispose()

    asyncio.run(scenario())


def test_ticket_read_policy_requires_permission_and_ownership(tmp_path) -> None:
    async def scenario() -> None:
        engine, sessions = await _session_factory(tmp_path)
        async with sessions() as session:
            own_role = Role(code="own_reader", name="Own reader", is_system=False)
            all_role = Role(code="all_reader", name="All reader", is_system=False)
            own_permission = Permission(
                module="ticket", action="read_own", code="ticket.read_own"
            )
            all_permission = Permission(
                module="ticket", action="read_all", code="ticket.read_all"
            )
            owner = User(
                username="owner",
                email="owner@example.com",
                first_name="Owner",
                last_name="User",
                password_hash="hash",
            )
            own_reader = User(
                username="own-reader",
                email="own-reader@example.com",
                first_name="Own",
                last_name="Reader",
                password_hash="hash",
            )
            all_reader = User(
                username="all-reader",
                email="all-reader@example.com",
                first_name="All",
                last_name="Reader",
                password_hash="hash",
            )
            no_reader = User(
                username="no-reader",
                email="no-reader@example.com",
                first_name="No",
                last_name="Reader",
                password_hash="hash",
            )
            session.add_all(
                [
                    own_role,
                    all_role,
                    own_permission,
                    all_permission,
                    owner,
                    own_reader,
                    all_reader,
                    no_reader,
                ]
            )
            await session.flush()
            session.add_all(
                [
                    RolePermission(
                        role_id=own_role.id, permission_id=own_permission.id
                    ),
                    RolePermission(
                        role_id=all_role.id, permission_id=all_permission.id
                    ),
                    UserRole(user_id=owner.id, role_id=own_role.id),
                    UserRole(user_id=own_reader.id, role_id=own_role.id),
                    UserRole(user_id=all_reader.id, role_id=all_role.id),
                ]
            )
            ticket = Ticket(
                ticket_no="IMS-TEST-READ",
                title="Read policy ticket",
                description="Ticket used to test read policy.",
                requester_id=owner.id,
                category_id=uuid4(),
                priority_id=uuid4(),
                status_id=uuid4(),
            )
            session.add(ticket)
            await session.commit()

            assert await ticket_read_scope(session, owner.id) == "own"
            assert await ticket_read_scope(session, all_reader.id) == "all"
            await require_ticket_read(session, owner, ticket)
            await require_ticket_read(session, all_reader, ticket)
            with pytest.raises(HTTPException, match="Forbidden"):
                await require_ticket_read(session, own_reader, ticket)
            with pytest.raises(HTTPException, match="Missing permission"):
                await require_ticket_read(session, no_reader, ticket)
        await engine.dispose()

    asyncio.run(scenario())
