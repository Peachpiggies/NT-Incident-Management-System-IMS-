"""HTTP-level contracts for UUID, PBAC, auth and ticket workflows."""

import asyncio
from dataclasses import dataclass

from app.api.v1.dependencies import get_db
from app.core.security import hash_password
from app.db.models import (
    Base,
    Permission,
    Role,
    RolePermission,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

PASSWORD = "Secure-password-123!"


@dataclass
class Seed:
    admin: User
    customer_a: User
    customer_b: User
    agent: User
    category: TicketCategory
    priority: TicketPriority


async def _create_harness(
    tmp_path,
) -> tuple[object, async_sessionmaker[AsyncSession], Seed]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        admin_role = Role(code="admin", name="Admin", is_system=True)
        customer_role = Role(code="customer", name="Customer", is_system=True)
        agent_role = Role(code="agent", name="Agent", is_system=True)
        permissions = [
            Permission(module="ticket", action=action, code=f"ticket.{action}")
            for action in [
                "create",
                "read_own",
                "read_all",
                "comment",
                "assign",
                "resolve",
                "close",
                "update",
                "delete",
            ]
        ] + [
            Permission(module="user", action="manage", code="user.manage"),
            Permission(module="role", action="manage", code="role.manage"),
            Permission(module="department", action="manage", code="department.manage"),
        ]
        admin = User(
            username="admin",
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            password_hash=hash_password(PASSWORD),
        )
        customer_a = User(
            username="customer-a",
            email="customer-a@example.com",
            first_name="Customer",
            last_name="A",
            password_hash=hash_password(PASSWORD),
        )
        customer_b = User(
            username="customer-b",
            email="customer-b@example.com",
            first_name="Customer",
            last_name="B",
            password_hash=hash_password(PASSWORD),
        )
        agent = User(
            username="agent",
            email="agent@example.com",
            first_name="Agent",
            last_name="User",
            password_hash=hash_password(PASSWORD),
        )
        category = TicketCategory(code="NETWORK", name="Network", is_active=True)
        priority = TicketPriority(code="HIGH", name="High", is_active=True)
        statuses = [
            TicketStatus(
                code=code, name=code.title(), is_active=True, is_closed=code == "CLOSED"
            )
            for code in [
                "NEW",
                "ASSIGNED",
                "IN_PROGRESS",
                "PENDING",
                "RESOLVED",
                "CLOSED",
            ]
        ]
        db.add_all(
            [
                admin_role,
                customer_role,
                agent_role,
                *permissions,
                admin,
                customer_a,
                customer_b,
                agent,
                category,
                priority,
                *statuses,
            ]
        )
        await db.flush()
        db.add_all(
            [
                UserRole(user_id=admin.id, role_id=admin_role.id),
                UserRole(user_id=customer_a.id, role_id=customer_role.id),
                UserRole(user_id=customer_b.id, role_id=customer_role.id),
                UserRole(user_id=agent.id, role_id=agent_role.id),
            ]
        )
        for permission in permissions:
            db.add(RolePermission(role_id=admin_role.id, permission_id=permission.id))
            if permission.code in {
                "ticket.create",
                "ticket.read_own",
                "ticket.comment",
                "ticket.update",
            }:
                db.add(
                    RolePermission(
                        role_id=customer_role.id, permission_id=permission.id
                    )
                )
            if permission.code in {
                "ticket.read_all",
                "ticket.assign",
                "ticket.resolve",
                "ticket.close",
                "ticket.update",
            }:
                db.add(
                    RolePermission(role_id=agent_role.id, permission_id=permission.id)
                )
        await db.commit()
        return (
            engine,
            sessions,
            Seed(admin, customer_a, customer_b, agent, category, priority),
        )


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_session_and_refresh_reuse_http_contract(tmp_path) -> None:
    engine, sessions, _seed = asyncio.run(_create_harness(tmp_path))

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@example.com",
                    "full_name": "New User",
                    "password": PASSWORD,
                },
            )
            assert registered.status_code == 201
            refresh_token = registered.json()["refresh_token"]
            rotated = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert rotated.status_code == 200
            assert (
                client.post(
                    "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
                ).status_code
                == 401
            )

            access = _token(client, "new@example.com")
            changed = client.post(
                "/api/v1/auth/change-password",
                headers=_headers(access),
                json={
                    "current_password": PASSWORD,
                    "new_password": "Another-password-456!",
                },
            )
            assert changed.status_code == 204
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={"email": "new@example.com", "password": PASSWORD},
                ).status_code
                == 401
            )
            relogin = client.post(
                "/api/v1/auth/login",
                json={"email": "new@example.com", "password": "Another-password-456!"},
            )
            assert relogin.status_code == 200
            assert (
                client.post(
                    "/api/v1/auth/logout",
                    json={"refresh_token": relogin.json()["refresh_token"]},
                ).status_code
                == 204
            )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_permission_ownership_management_and_ticket_workflow_http(tmp_path) -> None:
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            admin_token = _token(client, seed.admin.email)
            customer_a_token = _token(client, seed.customer_a.email)
            customer_b_token = _token(client, seed.customer_b.email)
            agent_token = _token(client, seed.agent.email)

            department = client.post(
                "/api/v1/departments",
                headers=_headers(admin_token),
                json={"code": "OPS", "name": "Operations"},
            )
            assert department.status_code == 201
            role = client.post(
                "/api/v1/roles",
                headers=_headers(admin_token),
                json={"code": "observer", "name": "Observer"},
            )
            assert role.status_code == 201
            permission = client.post(
                "/api/v1/permissions",
                headers=_headers(admin_token),
                json={"module": "report", "action": "view", "code": "report.view"},
            )
            assert permission.status_code == 201
            assert (
                client.post(
                    f"/api/v1/roles/{role.json()['id']}/permissions/{permission.json()['id']}",
                    headers=_headers(admin_token),
                ).status_code
                == 201
            )

            created = client.post(
                "/api/v1/tickets",
                headers=_headers(customer_a_token),
                json={
                    "title": "Network outage",
                    "description": "Network connection has been unavailable.",
                    "category_id": str(seed.category.id),
                    "priority_id": str(seed.priority.id),
                },
            )
            assert created.status_code == 201, created.text
            ticket = created.json()
            assert ticket["id"] and ticket["ticket_no"].startswith("IMS-")
            assert (
                client.get(
                    f"/api/v1/tickets/{ticket['id']}",
                    headers=_headers(customer_b_token),
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"/api/v1/tickets/{ticket['id']}", headers=_headers(agent_token)
                ).status_code
                == 200
            )

            assigned = client.post(
                f"/api/v1/tickets/{ticket['id']}/assign",
                headers=_headers(agent_token),
                json={"assignee_id": str(seed.agent.id)},
            )
            assert assigned.status_code == 200
            assert (
                client.post(
                    f"/api/v1/tickets/{ticket['id']}/resolve",
                    headers=_headers(agent_token),
                ).status_code
                == 200
            )
            history = client.get(
                f"/api/v1/tickets/{ticket['id']}/history",
                headers=_headers(customer_a_token),
            )
            assert history.status_code == 200
            assert {entry["action"] for entry in history.json()} >= {
                "ticket.create",
                "ticket.assign",
                "ticket.resolve",
            }
            assert (
                client.delete(
                    f"/api/v1/tickets/{ticket['id']}", headers=_headers(admin_token)
                ).status_code
                == 204
            )
            assert (
                client.get(
                    f"/api/v1/tickets/{ticket['id']}", headers=_headers(agent_token)
                ).status_code
                == 404
            )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
