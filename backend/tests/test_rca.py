"""HTTP-level contract for Root Cause Analysis: root causes, contributing
factors, impact analysis, and the RCA report workflow
(submit -> approve / reject)."""

import asyncio
from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.dependencies import get_db
from app.core.security import hash_password
from app.db.models import (
    Base,
    Department,
    Permission,
    Role,
    RolePermission,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.main import app

PASSWORD = "Secure-password-123!"


@dataclass
class Seed:
    investigator: User
    approver: User
    other_investigator: User
    ticket_id: str


async def _create_harness(tmp_path) -> tuple[object, async_sessionmaker[AsyncSession], Seed]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rca.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as db:
        investigator_role = Role(code="investigator", name="Investigator", is_system=True)
        approver_role = Role(code="approver", name="Approver", is_system=True)

        permissions = [
            Permission(module="rca", action=action, code=f"rca.{action}")
            for action in ["create", "update", "delete", "submit", "approve"]
        ]

        department = Department(code="OPS", name="Operations")

        investigator = User(
            username="rca-investigator",
            email="rca-investigator@example.com",
            first_name="Investigator",
            last_name="One",
            password_hash=hash_password(PASSWORD),
            department=department,
        )
        other_investigator = User(
            username="rca-investigator-2",
            email="rca-investigator-2@example.com",
            first_name="Investigator",
            last_name="Two",
            password_hash=hash_password(PASSWORD),
            department=department,
        )
        approver = User(
            username="rca-approver",
            email="rca-approver@example.com",
            first_name="Approver",
            last_name="One",
            password_hash=hash_password(PASSWORD),
            department=department,
        )

        db.add_all(
            [
                investigator_role,
                approver_role,
                *permissions,
                department,
                investigator,
                other_investigator,
                approver,
            ]
        )
        await db.flush()

        db.add_all(
            [
                UserRole(user_id=investigator.id, role_id=investigator_role.id),
                UserRole(user_id=other_investigator.id, role_id=investigator_role.id),
                UserRole(user_id=approver.id, role_id=approver_role.id),
            ]
        )
        by_code = {p.code: p for p in permissions}
        for code in ("rca.create", "rca.update", "rca.submit"):
            db.add(
                RolePermission(role_id=investigator_role.id, permission_id=by_code[code].id)
            )
        for code in ("rca.approve", "rca.delete"):
            db.add(RolePermission(role_id=approver_role.id, permission_id=by_code[code].id))

        category = TicketCategory(code="NETWORK", name="Network")
        priority = TicketPriority(code="HIGH", name="High", sort_order=1)
        status = TicketStatus(code="RESOLVED", name="Resolved", sort_order=1)
        db.add_all([category, priority, status])
        await db.flush()

        ticket = Ticket(
            ticket_no="INC-0001",
            title="Core switch outage",
            description="Regional core switch went down, network-wide impact.",
            requester_id=investigator.id,
            category_id=category.id,
            priority_id=priority.id,
            status_id=status.id,
        )
        db.add(ticket)
        await db.flush()

        await db.commit()
        return (
            engine,
            sessions,
            Seed(investigator, approver, other_investigator, str(ticket.id)),
        )


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_rca_full_lifecycle_and_approval_workflow(tmp_path) -> None:
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            investigator_token = _token(client, seed.investigator.email)
            other_investigator_token = _token(client, seed.other_investigator.email)
            approver_token = _token(client, seed.approver.email)

            # Root cause, anchored to the ticket
            root_cause = client.post(
                "/api/v1/rca/root-causes",
                headers=_headers(investigator_token),
                json={
                    "ticket_id": seed.ticket_id,
                    "category": "Hardware Failure",
                    "description": "Core switch power supply failed under load.",
                },
            )
            assert root_cause.status_code == 201, root_cause.text
            root_cause_id = root_cause.json()["id"]

            # A root cause anchored to neither ticket nor problem is rejected (422 - schema validator)
            bad_anchor = client.post(
                "/api/v1/rca/root-causes",
                headers=_headers(investigator_token),
                json={"category": "Human Error", "description": "No anchor supplied here."},
            )
            assert bad_anchor.status_code == 422, bad_anchor.text

            # Contributing factor
            factor = client.post(
                f"/api/v1/rca/root-causes/{root_cause_id}/contributing-factors",
                headers=_headers(investigator_token),
                json={
                    "root_cause_id": root_cause_id,
                    "factor_type": "Monitoring Gap",
                    "description": "No alert fired on redundant PSU failure.",
                },
            )
            assert factor.status_code == 201, factor.text

            factors = client.get(
                f"/api/v1/rca/root-causes/{root_cause_id}/contributing-factors",
                headers=_headers(investigator_token),
            )
            assert factors.status_code == 200
            assert factors.json()["total"] == 1

            # Impact analysis
            impact = client.post(
                f"/api/v1/rca/root-causes/{root_cause_id}/impact-analyses",
                headers=_headers(investigator_token),
                json={
                    "root_cause_id": root_cause_id,
                    "affected_users_count": 450,
                    "downtime_minutes": 90,
                    "business_impact": "HIGH",
                    "financial_impact": 12000.50,
                    "notes": "Regional outage during business hours.",
                },
            )
            assert impact.status_code == 201, impact.text
            assert impact.json()["business_impact"] == "HIGH"

            # RCA report -> DRAFT
            report = client.post(
                "/api/v1/rca/reports",
                headers=_headers(investigator_token),
                json={
                    "ticket_id": seed.ticket_id,
                    "root_cause_id": root_cause_id,
                    "title": "Core switch outage postmortem",
                    "summary": "Redundant PSU failed silently, taking down the core switch.",
                    "corrective_actions": "Replaced PSU, added redundant alerting.",
                    "preventive_actions": "Quarterly PSU health checks.",
                },
            )
            assert report.status_code == 201, report.text
            report_id = report.json()["id"]
            assert report.json()["status"] == "DRAFT"

            # A different investigator cannot see this draft
            assert (
                client.get(
                    f"/api/v1/rca/reports/{report_id}",
                    headers=_headers(other_investigator_token),
                ).status_code
                == 404
            )

            # Cannot approve straight from DRAFT
            skip_to_approve = client.post(
                f"/api/v1/rca/reports/{report_id}/approve",
                headers=_headers(approver_token),
                json={"comment": "Too fast"},
            )
            assert skip_to_approve.status_code == 409

            # A non-preparer (even with rca.submit via role) cannot submit someone else's report
            # -- submit as the actual preparer instead
            submitted = client.post(
                f"/api/v1/rca/reports/{report_id}/submit",
                headers=_headers(investigator_token),
                json={"comment": "Ready for review"},
            )
            assert submitted.status_code == 200, submitted.text
            assert submitted.json()["status"] == "IN_REVIEW"

            # Now visible to the approver even though not yet approved
            visible_to_approver = client.get(
                f"/api/v1/rca/reports/{report_id}", headers=_headers(approver_token)
            )
            assert visible_to_approver.status_code == 200

            # Reject back to DRAFT
            rejected = client.post(
                f"/api/v1/rca/reports/{report_id}/reject",
                headers=_headers(approver_token),
                json={"comment": "Add more detail to the timeline"},
            )
            assert rejected.status_code == 200, rejected.text
            assert rejected.json()["status"] == "DRAFT"

            # Edit while back in DRAFT
            edited = client.put(
                f"/api/v1/rca/reports/{report_id}",
                headers=_headers(investigator_token),
                json={"timeline": "14:02 outage detected. 14:10 root cause identified."},
            )
            assert edited.status_code == 200, edited.text

            # Resubmit and approve
            resubmitted = client.post(
                f"/api/v1/rca/reports/{report_id}/submit",
                headers=_headers(investigator_token),
                json={},
            )
            assert resubmitted.status_code == 200
            approved = client.post(
                f"/api/v1/rca/reports/{report_id}/approve",
                headers=_headers(approver_token),
                json={"comment": "Looks good"},
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "APPROVED"
            assert approved.json()["approved_by"]["id"] == str(seed.approver.id)

            # APPROVED reports are visible to anyone authenticated
            now_visible = client.get(
                f"/api/v1/rca/reports/{report_id}",
                headers=_headers(other_investigator_token),
            )
            assert now_visible.status_code == 200

            # Ticket-scoped listing surfaces it
            ticket_reports = client.get(
                f"/api/v1/tickets/{seed.ticket_id}/rca-reports",
                headers=_headers(other_investigator_token),
            )
            assert ticket_reports.status_code == 200
            assert ticket_reports.json()["total"] == 1

            # An investigator without rca.approve cannot approve, even on an
            # already-DRAFT report they're not blocked from reading for any
            # other reason
            another_root_cause = client.post(
                "/api/v1/rca/root-causes",
                headers=_headers(investigator_token),
                json={
                    "ticket_id": seed.ticket_id,
                    "category": "Process Gap",
                    "description": "Change was deployed outside the maintenance window.",
                },
            ).json()
            another_report = client.post(
                "/api/v1/rca/reports",
                headers=_headers(investigator_token),
                json={
                    "ticket_id": seed.ticket_id,
                    "root_cause_id": another_root_cause["id"],
                    "title": "Second postmortem",
                    "summary": "A second, unrelated draft report.",
                },
            ).json()
            client.post(
                f"/api/v1/rca/reports/{another_report['id']}/submit",
                headers=_headers(investigator_token),
                json={},
            )
            no_permission = client.post(
                f"/api/v1/rca/reports/{another_report['id']}/approve",
                headers=_headers(investigator_token),
                json={},
            )
            assert no_permission.status_code == 403
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
