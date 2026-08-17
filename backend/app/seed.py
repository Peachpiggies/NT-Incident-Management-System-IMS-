"""Idempotent reference-data seed for a new NT-IMS database."""

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import (
    Department,
    KBArticleStatus,
    KBArticleStatusTransition,
    KBCategory,
    NotificationRule,
    Permission,
    Role,
    RolePermission,
    TicketCategory,
    TicketPriority,
    TicketService,
    TicketStatus,
    TicketStatusTransition,
    TicketSubcategory,
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
    ("ticket", "create"),
    ("ticket", "read_own"),
    ("ticket", "read_all"),
    ("ticket", "comment"),
    ("ticket", "attachment_add"),
    ("ticket", "update"),
    ("ticket", "delete"),
    ("ticket", "internal_note"),
    ("ticket", "assign"),
    ("ticket", "claim"),
    ("ticket", "start"),
    ("ticket", "pending"),
    ("ticket", "escalate"),
    ("ticket", "receive_escalated"),
    ("ticket", "resolve"),
    ("ticket", "close"),
    ("ticket", "reopen"),
    ("dashboard", "view"),
    ("report", "view"),
    ("user", "manage"),
    ("role", "manage"),
    ("department", "manage"),
    ("configuration", "manage"),
    ("kb", "create"),
    ("kb", "update"),
    ("kb", "delete"),
    ("kb", "submit"),
    ("kb", "review"),
    ("kb", "archive"),
    ("kb", "restore"),
    ("kb", "link_incident"),
    ("notification", "manage"),
    ("rca", "create"),
    ("rca", "update"),
    ("rca", "delete"),
    ("rca", "submit"),
    ("rca", "approve"),
]

ROLE_PERMISSION_CODES = {
    "customer": {
        "ticket.create",
        "ticket.read_own",
        "ticket.comment",
        "ticket.attachment_add",
        "ticket.update",
    },
    "helpdesk_t1": {
        "ticket.read_all",
        "ticket.comment",
        "ticket.attachment_add",
        "ticket.update",
        "ticket.assign",
        "ticket.claim",
        "ticket.start",
        "ticket.pending",
        "ticket.escalate",
        "ticket.resolve",
        "ticket.close",
        "ticket.reopen",
        "kb.create",
        "kb.update",
        "kb.submit",
        "kb.link_incident",
    },
    "helpdesk_t2": {
        "ticket.read_all",
        "ticket.comment",
        "ticket.attachment_add",
        "ticket.update",
        "ticket.internal_note",
        "ticket.receive_escalated",
        "ticket.start",
        "ticket.pending",
        "ticket.resolve",
        "ticket.close",
        "ticket.reopen",
        "kb.create",
        "kb.update",
        "kb.submit",
        "kb.link_incident",
        "rca.create",
        "rca.update",
        "rca.submit",
    },
    "manager": {
        "ticket.read_all",
        "ticket.assign",
        "ticket.resolve",
        "ticket.close",
        "ticket.reopen",
        "ticket.update",
        "ticket.delete",
        "dashboard.view",
        "report.view",
        "user.manage",
        "kb.review",
        "kb.archive",
        "kb.restore",
        "kb.delete",
        "kb.link_incident",
        "notification.manage",
        "rca.approve",
        "rca.delete",
    },
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
        for code, name in [
            ("HQ", "Head Office"),
            ("HELPDESK", "Helpdesk"),
            ("NETWORK", "Network"),
            ("SERVER", "Server"),
            ("SECURITY", "Security"),
            ("MANAGEMENT", "Management"),
        ]:
            departments[code] = await _get_or_create(
                session, Department, code, name=name, is_active=True
            )

        roles = {}
        for code, name, description in ROLES:
            roles[code] = await _get_or_create(
                session, Role, code, name=name, description=description, is_system=True
            )

        permissions = {}
        for module, action in PERMISSIONS:
            code = f"{module}.{action}"
            permissions[code] = await _get_or_create(
                session, Permission, code, module=module, action=action
            )

        for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
            for permission_code in permission_codes:
                exists = await session.scalar(
                    select(RolePermission).where(
                        RolePermission.role_id == roles[role_code].id,
                        RolePermission.permission_id == permissions[permission_code].id,
                    )
                )
                if not exists:
                    session.add(
                        RolePermission(
                            role_id=roles[role_code].id,
                            permission_id=permissions[permission_code].id,
                        )
                    )

        categories = {}
        for code, name, color, sort_order in [
            ("NETWORK", "Network", "#2563EB", 10),
            ("EMAIL", "Email", "#7C3AED", 20),
            ("PRINTER", "Printer", "#6B7280", 30),
            ("SERVER", "Server", "#DC2626", 40),
            ("APPLICATION", "Application", "#059669", 50),
            ("INTERNET", "Internet", "#0891B2", 60),
            ("ACCOUNT", "Account", "#D97706", 70),
            ("HARDWARE", "Hardware", "#4B5563", 80),
        ]:
            categories[code] = await _get_or_create(
                session,
                TicketCategory,
                code,
                name=name,
                color=color,
                sort_order=sort_order,
                is_active=True,
            )

        subcategories = {}
        for category_code, code, name, sort_order in [
            ("NETWORK", "CONNECTIVITY", "Connectivity", 10),
            ("NETWORK", "WIFI", "Wi-Fi", 20),
            ("EMAIL", "OUTLOOK", "Outlook", 10),
            ("EMAIL", "MAILBOX", "Mailbox", 20),
            ("APPLICATION", "BUSINESS_APP", "Business Application", 10),
            ("SERVER", "OPERATING_SYSTEM", "Operating System", 10),
        ]:
            existing = await session.scalar(
                select(TicketSubcategory).where(
                    TicketSubcategory.category_id == categories[category_code].id,
                    TicketSubcategory.code == code,
                )
            )
            if existing is None:
                existing = TicketSubcategory(
                    category_id=categories[category_code].id,
                    code=code,
                    name=name,
                    sort_order=sort_order,
                    is_active=True,
                )
                session.add(existing)
                await session.flush()
            subcategories[(category_code, code)] = existing

        for category_code, subcategory_code, code, name, description in [
            (
                "NETWORK",
                "CONNECTIVITY",
                "LAN",
                "LAN Connectivity",
                "Wired network access",
            ),
            (
                "NETWORK",
                "WIFI",
                "CORPORATE_WIFI",
                "Corporate Wi-Fi",
                "Corporate wireless access",
            ),
            (
                "EMAIL",
                "OUTLOOK",
                "OUTLOOK_CLIENT",
                "Outlook Client",
                "Desktop Outlook support",
            ),
            (
                "EMAIL",
                "MAILBOX",
                "MAILBOX_ACCESS",
                "Mailbox Access",
                "Mailbox access and permissions",
            ),
            (
                "APPLICATION",
                "BUSINESS_APP",
                "ERP",
                "ERP",
                "Enterprise resource planning",
            ),
            (
                "SERVER",
                "OPERATING_SYSTEM",
                "WINDOWS_SERVER",
                "Windows Server",
                "Windows server operations",
            ),
        ]:
            subcategory = subcategories[(category_code, subcategory_code)]
            existing = await session.scalar(
                select(TicketService).where(
                    TicketService.subcategory_id == subcategory.id,
                    TicketService.code == code,
                )
            )
            if existing is None:
                session.add(
                    TicketService(
                        subcategory_id=subcategory.id,
                        code=code,
                        name=name,
                        description=description,
                        is_active=True,
                    )
                )

        for code, name, color, sla_minutes, sort_order in [
            ("CRITICAL", "Critical", "#DC2626", 60, 10),
            ("HIGH", "High", "#EA580C", 240, 20),
            ("MEDIUM", "Medium", "#D97706", 480, 30),
            ("LOW", "Low", "#16A34A", 1440, 40),
        ]:
            await _get_or_create(
                session,
                TicketPriority,
                code,
                name=name,
                color=color,
                sla_minutes=sla_minutes,
                sort_order=sort_order,
                is_active=True,
            )

        statuses = {}
        for code, name, color, is_closed, sort_order in [
            ("NEW", "New", "#2563EB", False, 10),
            ("ASSIGNED", "Assigned", "#7C3AED", False, 20),
            ("IN_PROGRESS", "In Progress", "#D97706", False, 30),
            ("PENDING", "Pending", "#6B7280", False, 40),
            ("ESCALATED", "Escalated", "#B45309", False, 45),
            ("RESOLVED", "Resolved", "#16A34A", False, 50),
            ("CLOSED", "Closed", "#374151", True, 60),
            ("CANCELLED", "Cancelled", "#991B1B", True, 70),
        ]:
            statuses[code] = await _get_or_create(
                session,
                TicketStatus,
                code,
                name=name,
                color=color,
                is_closed=is_closed,
                sort_order=sort_order,
                is_active=True,
            )

        for from_code, to_code, required_permission in [
            ("NEW", "ASSIGNED", "ticket.assign"),
            ("ASSIGNED", "IN_PROGRESS", "ticket.start"),
            ("ASSIGNED", "ESCALATED", "ticket.escalate"),
            ("IN_PROGRESS", "PENDING", "ticket.pending"),
            ("PENDING", "IN_PROGRESS", "ticket.start"),
            ("IN_PROGRESS", "ESCALATED", "ticket.escalate"),
            ("ESCALATED", "IN_PROGRESS", "ticket.receive_escalated"),
            ("IN_PROGRESS", "RESOLVED", "ticket.resolve"),
            ("RESOLVED", "CLOSED", "ticket.close"),
            ("RESOLVED", "ASSIGNED", "ticket.reopen"),
            ("CLOSED", "ASSIGNED", "ticket.reopen"),
        ]:
            exists = await session.scalar(
                select(TicketStatusTransition).where(
                    TicketStatusTransition.from_status_id == statuses[from_code].id,
                    TicketStatusTransition.to_status_id == statuses[to_code].id,
                )
            )
            if exists is None:
                session.add(
                    TicketStatusTransition(
                        from_status_id=statuses[from_code].id,
                        to_status_id=statuses[to_code].id,
                        required_permission=required_permission,
                        is_active=True,
                    )
                )

        kb_statuses = {}
        for code, name, color, sort_order in [
            ("DRAFT", "Draft", "#6B7280", 10),
            ("IN_REVIEW", "In Review", "#D97706", 20),
            ("PUBLISHED", "Published", "#16A34A", 30),
            ("ARCHIVED", "Archived", "#374151", 40),
        ]:
            kb_statuses[code] = await _get_or_create(
                session,
                KBArticleStatus,
                code,
                name=name,
                color=color,
                sort_order=sort_order,
                is_active=True,
            )

        for from_code, to_code, required_permission in [
            ("DRAFT", "IN_REVIEW", "kb.submit"),
            ("IN_REVIEW", "PUBLISHED", "kb.review"),
            ("IN_REVIEW", "DRAFT", "kb.review"),
            ("PUBLISHED", "ARCHIVED", "kb.archive"),
            ("ARCHIVED", "DRAFT", "kb.restore"),
        ]:
            exists = await session.scalar(
                select(KBArticleStatusTransition).where(
                    KBArticleStatusTransition.from_status_id == kb_statuses[from_code].id,
                    KBArticleStatusTransition.to_status_id == kb_statuses[to_code].id,
                )
            )
            if exists is None:
                session.add(
                    KBArticleStatusTransition(
                        from_status_id=kb_statuses[from_code].id,
                        to_status_id=kb_statuses[to_code].id,
                        required_permission=required_permission,
                        is_active=True,
                    )
                )

        for name, sort_order in [
            ("Network", 10),
            ("Email", 20),
            ("Hardware", 30),
            ("Application", 40),
            ("Account & Access", 50),
            ("General", 60),
        ]:
            existing = await session.scalar(
                select(KBCategory).where(
                    KBCategory.name == name, KBCategory.parent_id.is_(None)
                )
            )
            if existing is None:
                session.add(
                    KBCategory(name=name, sort_order=sort_order, is_active=True)
                )

        for name, event_type, channels in [
            # "in_app" is deliberately excluded here: the ticket endpoints
            # that fire these events (assign/resolve, see app/api/v1/tickets.py)
            # already write an in-app Notification directly. These rules
            # only add the extra channels on top of that.
            ("Ticket assigned", "ticket.assigned", ["email"]),
            ("Ticket resolved", "ticket.resolved", ["email"]),
            ("SLA breach warning", "sla.warning", ["in_app", "email", "sms"]),
        ]:
            existing_rule = await session.scalar(
                select(NotificationRule).where(NotificationRule.event_type == event_type)
            )
            if existing_rule is None:
                session.add(
                    NotificationRule(
                        name=name,
                        event_type=event_type,
                        channels=channels,
                        recipient_role_ids=[],
                        recipient_user_ids=[],
                        is_active=True,
                    )
                )

        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if not admin:
            admin = User(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                first_name="IMS",
                last_name="Administrator",
                password_hash=hash_password(ADMIN_PASSWORD),
                department_id=departments["MANAGEMENT"].id,
                is_active=True,
            )
            session.add(admin)
            await session.flush()
        admin_role = await session.scalar(
            select(UserRole).where(
                UserRole.user_id == admin.id, UserRole.role_id == roles["admin"].id
            )
        )
        if not admin_role:
            session.add(UserRole(user_id=admin.id, role_id=roles["admin"].id))
        await session.commit()

    print("Seed complete")
    print(f"Admin user: {ADMIN_EMAIL}")
    print("Change the default admin password before first production use.")


if __name__ == "__main__":
    asyncio.run(seed_database())