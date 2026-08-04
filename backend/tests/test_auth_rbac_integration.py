import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.auth import RefreshRequest, UserRegisterRequest, refresh, register
from app.api.v1.dependencies import require_permission, user_has_permission
from app.db.models import (
    Base,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
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
