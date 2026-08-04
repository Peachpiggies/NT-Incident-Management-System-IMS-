"""Idempotent reference-data seed for a new NT-IMS database."""

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import (
    Department,
    Permission,
    Role,
    RolePermission,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.db.session import AsyncSessionLocal

ADMIN_EMAIL = "admin@example.com"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ChangeMe123!"

ROLES = [
    ("customer", "Customer", "External requester"),
    ("helpdesk_t1", "Helpdesk T1", "First-line helpdesk"),
    ("helpdesk_t2", "Helpdesk T2", "Second-line specialist"),
    ("manager", "Manager", "Operations manager"),
    ("admin", "Admin", "System administrator"),
]

PERMISSIONS = [
    ("ticket", "create"), ("ticket", "read_own"), ("ticket", "read_all"),
    ("ticket", "comment"), ("ticket", "internal_note"), ("ticket", "assign"),
    ("ticket", "escalate"), ("ticket", "resolve"), ("ticket", "close"),
    ("ticket", "reopen"), ("dashboard", "view"), ("report", "view"),
    ("user", "manage"), ("role", "manage"), ("department", "manage"),
    ("configuration", "manage"),
]

ROLE_PERMISSION_CODES = {
    "customer": {"ticket.create", "ticket.read_own", "ticket.comment"},
    "helpdesk_t1": {"ticket.read_all", "ticket.comment", "ticket.assign", "ticket.escalate", "ticket.resolve", "ticket.close", "ticket.reopen"},
    "helpdesk_t2": {"ticket.read_all", "ticket.comment", "ticket.internal_note", "ticket.resolve", "ticket.close", "ticket.reopen"},
    "manager": {"ticket.read_all", "ticket.assign", "ticket.resolve", "ticket.close", "ticket.reopen", "dashboard.view", "report.view", "user.manage"},
    "admin": {f"{module}.{action}" for module, action in PERMISSIONS},
}


async def _get_or_create(session, model, code: str, **values):
    existing = await session.scalar(select(model).where(model.code == code))
    if existing:
        return existing
    record = model(code=code, **values)
    session.add(record)
    await session.flush()
    return record


async def seed_database() -> None:
    async with AsyncSessionLocal() as session:
        departments = {}
        for code, name in [("HQ", "Head Office"), ("HELPDESK", "Helpdesk"), ("NETWORK", "Network"), ("SERVER", "Server"), ("SECURITY", "Security"), ("MANAGEMENT", "Management")]:
            departments[code] = await _get_or_create(session, Department, code, name=name, is_active=True)

        roles = {}
        for code, name, description in ROLES:
            roles[code] = await _get_or_create(session, Role, code, name=name, description=description, is_system=True)

        permissions = {}
        for module, action in PERMISSIONS:
            code = f"{module}.{action}"
            permissions[code] = await _get_or_create(session, Permission, code, module=module, action=action)

        for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
            for permission_code in permission_codes:
                exists = await session.scalar(select(RolePermission).where(RolePermission.role_id == roles[role_code].id, RolePermission.permission_id == permissions[permission_code].id))
                if not exists:
                    session.add(RolePermission(role_id=roles[role_code].id, permission_id=permissions[permission_code].id))

        for code, name, color, sort_order in [("NETWORK", "Network", "#2563EB", 10), ("EMAIL", "Email", "#7C3AED", 20), ("PRINTER", "Printer", "#6B7280", 30), ("SERVER", "Server", "#DC2626", 40), ("APPLICATION", "Application", "#059669", 50), ("INTERNET", "Internet", "#0891B2", 60), ("ACCOUNT", "Account", "#D97706", 70), ("HARDWARE", "Hardware", "#4B5563", 80)]:
            await _get_or_create(session, TicketCategory, code, name=name, color=color, sort_order=sort_order, is_active=True)

        for code, name, color, sla_minutes, sort_order in [("CRITICAL", "Critical", "#DC2626", 60, 10), ("HIGH", "High", "#EA580C", 240, 20), ("MEDIUM", "Medium", "#D97706", 480, 30), ("LOW", "Low", "#16A34A", 1440, 40)]:
            await _get_or_create(session, TicketPriority, code, name=name, color=color, sla_minutes=sla_minutes, sort_order=sort_order, is_active=True)

        for code, name, color, is_closed, sort_order in [("NEW", "New", "#2563EB", False, 10), ("ASSIGNED", "Assigned", "#7C3AED", False, 20), ("IN_PROGRESS", "In Progress", "#D97706", False, 30), ("PENDING", "Pending", "#6B7280", False, 40), ("RESOLVED", "Resolved", "#16A34A", False, 50), ("CLOSED", "Closed", "#374151", True, 60), ("CANCELLED", "Cancelled", "#991B1B", True, 70)]:
            await _get_or_create(session, TicketStatus, code, name=name, color=color, is_closed=is_closed, sort_order=sort_order, is_active=True)

        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if not admin:
            admin = User(username=ADMIN_USERNAME, email=ADMIN_EMAIL, first_name="IMS", last_name="Administrator", password_hash=hash_password(ADMIN_PASSWORD), department_id=departments["MANAGEMENT"].id, is_active=True)
            session.add(admin)
            await session.flush()
        admin_role = await session.scalar(select(UserRole).where(UserRole.user_id == admin.id, UserRole.role_id == roles["admin"].id))
        if not admin_role:
            session.add(UserRole(user_id=admin.id, role_id=roles["admin"].id))
        await session.commit()

    print("Seed complete")
    print(f"Admin user: {ADMIN_EMAIL}")
    print("Change the default admin password before first production use.")


if __name__ == "__main__":
    asyncio.run(seed_database())
