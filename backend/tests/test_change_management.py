"""HTTP and domain tests for the persisted Change Management workflow."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.dependencies import get_db
from app.core.change_management import (
    ApprovalDecision,
    ApprovalPolicy,
    ChangeRequest as DomainChangeRequest,
    ChangeStatus,
    ChangeType,
    RiskLevel,
)
from app.core.security import hash_password
from app.db.models import (
    Base,
    Department,
    Permission,
    Role,
    RolePermission,
    TicketPriority,
    User,
    UserRole,
)
from app.main import app

PASSWORD = "Secure-password-123!"


@dataclass
class Seed:
    requester: User
    approver_one: User
    approver_two: User
    reader: User
    priority_id: str


async def _harness(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'change.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as db:
        department = Department(code="OPS", name="Operations")
        roles = [
            Role(code="change_requester", name="Change Requester"),
            Role(code="change_approver", name="Change Approver"),
            Role(code="change_reader", name="Change Reader"),
        ]
        actions = [
            "read",
            "create",
            "update",
            "assess",
            "approve",
            "implement",
            "validate",
            "rollback",
            "close",
        ]
        permissions = [
            Permission(module="change", action=action, code=f"change.{action}")
            for action in actions
        ]
        users = [
            User(
                username="change-requester",
                email="change-requester@example.com",
                first_name="Change",
                last_name="Requester",
                password_hash=hash_password(PASSWORD),
                department=department,
            ),
            User(
                username="change-approver-one",
                email="change-approver-one@example.com",
                first_name="Approver",
                last_name="One",
                password_hash=hash_password(PASSWORD),
                department=department,
            ),
            User(
                username="change-approver-two",
                email="change-approver-two@example.com",
                first_name="Approver",
                last_name="Two",
                password_hash=hash_password(PASSWORD),
                department=department,
            ),
            User(
                username="change-reader",
                email="change-reader@example.com",
                first_name="Change",
                last_name="Reader",
                password_hash=hash_password(PASSWORD),
                department=department,
            ),
        ]
        priority = TicketPriority(code="HIGH", name="High", sort_order=1)
        db.add_all([department, *roles, *permissions, *users, priority])
        await db.flush()

        by_role = {role.code: role for role in roles}
        by_permission = {permission.code: permission for permission in permissions}
        db.add_all(
            [
                UserRole(user_id=users[0].id, role_id=by_role["change_requester"].id),
                UserRole(user_id=users[1].id, role_id=by_role["change_approver"].id),
                UserRole(user_id=users[2].id, role_id=by_role["change_approver"].id),
                UserRole(user_id=users[3].id, role_id=by_role["change_reader"].id),
            ]
        )
        for code in actions:
            db.add(
                RolePermission(
                    role_id=by_role["change_requester"].id,
                    permission_id=by_permission[f"change.{code}"].id,
                )
            )
        for code in ["read", "approve"]:
            for approver_role in ["change_approver"]:
                db.add(
                    RolePermission(
                        role_id=by_role[approver_role].id,
                        permission_id=by_permission[f"change.{code}"].id,
                    )
                )
        db.add(
            RolePermission(
                role_id=by_role["change_reader"].id,
                permission_id=by_permission["change.read"].id,
            )
        )
        await db.commit()
        return engine, sessions, Seed(
            requester=users[0],
            approver_one=users[1],
            approver_two=users[2],
            reader=users[3],
            priority_id=str(priority.id),
        )


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_domain_change_lifecycle() -> None:
    policy = ApprovalPolicy()
    change = DomainChangeRequest(
        change_no="CHG-TEST-1",
        title="Database upgrade",
        change_type=ChangeType.NORMAL,
    )
    change.submit()
    change.assess_risk(
        RiskLevel.HIGH,
        "Brief failover impact",
        "Unlikely",
        "user-1",
        "Fail over before patching",
    )
    change.record_approval("user-2", ApprovalDecision.APPROVED, policy)
    assert change.status == ChangeStatus.SUBMITTED
    change.record_approval("user-3", ApprovalDecision.APPROVED, policy)
    assert change.status == ChangeStatus.APPROVED
    change.create_implementation_plan("Patch standby, fail over, patch old primary")
    change.schedule()
    change.start_implementation()
    change.complete_implementation("Completed successfully")
    change.validate("user-4", False, "Latency increased")
    change.initiate_rollback("Validation failed", "Restore previous version", "user-5")
    change.complete_rollback()
    change.close()
    assert change.status == ChangeStatus.CLOSED

    emergency = DomainChangeRequest(
        change_no="CHG-TEST-2",
        title="Emergency firewall fix",
        change_type=ChangeType.EMERGENCY,
        emergency_justification="Active security exposure requires immediate remediation.",
    )
    emergency.submit()
    emergency.assess_risk(
        RiskLevel.CRITICAL,
        "Security exposure",
        "Likely",
        "user-1",
        "Apply vendor mitigation immediately",
    )
    emergency.record_approval("user-2", ApprovalDecision.APPROVED, policy)
    assert emergency.status == ChangeStatus.APPROVED


def test_change_management_http_full_lifecycle(tmp_path) -> None:
    engine, sessions, seed = asyncio.run(_harness(tmp_path))

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            requester = _token(client, seed.requester.email)
            approver_one = _token(client, seed.approver_one.email)
            approver_two = _token(client, seed.approver_two.email)
            reader = _token(client, seed.reader.email)

            start = datetime.now(timezone.utc) + timedelta(days=1)
            end = start + timedelta(hours=2)
            forbidden = client.post(
                "/api/v1/changes",
                headers=_headers(reader),
                json={
                    "title": "Unauthorized change",
                    "description": "This should not be creatable by a reader.",
                    "change_type": "NORMAL",
                    "priority_id": seed.priority_id,
                    "planned_start": start.isoformat(),
                    "planned_end": end.isoformat(),
                },
            )
            assert forbidden.status_code == 403

            created = client.post(
                "/api/v1/changes",
                headers=_headers(requester),
                json={
                    "title": "Upgrade database cluster",
                    "description": "Patch the database cluster during maintenance.",
                    "change_type": "NORMAL",
                    "priority_id": seed.priority_id,
                    "planned_start": start.isoformat(),
                    "planned_end": end.isoformat(),
                },
            )
            assert created.status_code == 201, created.text
            change = created.json()
            change_id = change["id"]
            assert change["change_no"].startswith("CHG-")
            assert change["status"] == "DRAFT"

            assert (
                client.post(
                    f"/api/v1/changes/{change_id}/approvals",
                    headers=_headers(approver_one),
                    json={
                        "change_request_id": change_id,
                        "decision": "APPROVED",
                    },
                ).status_code
                == 409
            )

            submitted = client.post(
                f"/api/v1/changes/{change_id}/submit",
                headers=_headers(requester),
            )
            assert submitted.status_code == 200
            assert submitted.json()["status"] == "SUBMITTED"

            risk = client.post(
                f"/api/v1/changes/{change_id}/risk-assessment",
                headers=_headers(requester),
                json={
                    "change_request_id": change_id,
                    "risk_level": "HIGH",
                    "impact_description": "Short failover window.",
                    "likelihood": "Unlikely",
                    "mitigation_plan": "Validate standby before cutover.",
                },
            )
            assert risk.status_code == 200, risk.text

            first = client.post(
                f"/api/v1/changes/{change_id}/approvals",
                headers=_headers(approver_one),
                json={
                    "change_request_id": change_id,
                    "decision": "APPROVED",
                    "comments": "CAB review passed.",
                },
            )
            assert first.status_code == 200
            assert first.json()["status"] == "SUBMITTED"

            second = client.post(
                f"/api/v1/changes/{change_id}/approvals",
                headers=_headers(approver_two),
                json={
                    "change_request_id": change_id,
                    "decision": "APPROVED",
                },
            )
            assert second.status_code == 200
            assert second.json()["status"] == "APPROVED"

            planned = client.post(
                f"/api/v1/changes/{change_id}/implementation",
                headers=_headers(requester),
                json={
                    "change_request_id": change_id,
                    "implementation_plan": "Patch standby, fail over, then patch primary.",
                    "scheduled_start": start.isoformat(),
                    "scheduled_end": end.isoformat(),
                },
            )
            assert planned.status_code == 200

            scheduled = client.post(
                f"/api/v1/changes/{change_id}/schedule",
                headers=_headers(requester),
            )
            assert scheduled.status_code == 200
            assert scheduled.json()["status"] == "SCHEDULED"

            started = client.post(
                f"/api/v1/changes/{change_id}/implementation/start",
                headers=_headers(requester),
            )
            assert started.status_code == 200
            assert started.json()["status"] == "IN_PROGRESS"

            completed = client.post(
                f"/api/v1/changes/{change_id}/implementation/complete",
                headers=_headers(requester),
                json={"notes": "Implementation completed."},
            )
            assert completed.status_code == 200
            assert completed.json()["status"] == "IMPLEMENTED"

            validation = client.post(
                f"/api/v1/changes/{change_id}/validation",
                headers=_headers(requester),
                json={
                    "change_request_id": change_id,
                    "validation_result": True,
                    "notes": "Database healthy after cutover.",
                },
            )
            assert validation.status_code == 200
            assert validation.json()["status"] == "VALIDATED"

            closed = client.post(
                f"/api/v1/changes/{change_id}/close",
                headers=_headers(requester),
            )
            assert closed.status_code == 200
            assert closed.json()["status"] == "CLOSED"

            listed = client.get("/api/v1/changes", headers=_headers(reader))
            assert listed.status_code == 200
            assert listed.json()["total"] == 1

            approvals = client.get(
                f"/api/v1/changes/{change_id}/approvals",
                headers=_headers(reader),
            )
            assert approvals.status_code == 200
            assert approvals.json()["total"] == 2
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
