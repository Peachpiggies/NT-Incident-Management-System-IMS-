"""
Test suite for the complete ticket lifecycle scenario, against the actual
NT-IMS schema in app/db/models.py.

Scenario flow:
    Customer creates ticket (OPEN, tier 1, assigned to T1)
        |
    T1 works on ticket
        |
    T1 cannot solve -> TECHNICAL escalation (tier 1 -> 2, T2)
        |
    T2 investigates
        |
    T2 escalates to Manager (tier 2 -> 3)
        |
    Manager resolves -> resolution requirement enforced
        |
    Customer rejects -> reopen_count += 1
        |
    Manager resolves again
        |
    Customer confirms -> ticket CLOSED

NOTE ON SCOPE
-------------
Only app/db/models.py exists in this repo so far; the /resolve, /reopen and
/reject endpoints (and any service layer) have not been shared yet. To keep
these tests runnable today, the four workflow actions below are implemented
as small local helpers that operate directly on the ORM objects, standing in
for the future service/router logic:

    resolve_ticket(session, ticket, resolution_summary, resolution_code, status_id, performed_by)
    reject_ticket(session, ticket, status_id, performed_by, remark)
    reopen_ticket(session, ticket, status_id, performed_by, remark)
    close_ticket(session, ticket, status_id, performed_by)

Once the real /resolve, /reopen, /reject implementation is available, swap
these calls for the real service/router calls -- the fixtures, master data,
and assertions should still apply unchanged.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    Department,
    Ticket,
    TicketCategory,
    TicketEscalation,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    User,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def departments(db_session):
    """Departments involved in the escalation path."""
    depts = {
        "helpdesk": Department(code="HELPDESK", name="Helpdesk (T1)"),
        "l2_support": Department(code="L2_SUPPORT", name="Technical Support (T2)"),
        "management": Department(code="MANAGEMENT", name="Management (T3)"),
    }
    for d in depts.values():
        db_session.add(d)
    db_session.commit()
    for d in depts.values():
        db_session.refresh(d)
    return depts


@pytest.fixture
def users(db_session, departments):
    """All users needed for the scenario."""
    u = {
        "customer": User(
            username="customer1",
            password_hash="x",
            first_name="Cindy",
            last_name="Customer",
            email="customer1@example.com",
        ),
        "t1": User(
            username="tech1",
            password_hash="x",
            first_name="Tom",
            last_name="T1",
            email="tech1@example.com",
            department_id=departments["helpdesk"].id,
        ),
        "t2": User(
            username="tech2",
            password_hash="x",
            first_name="Tina",
            last_name="T2",
            email="tech2@example.com",
            department_id=departments["l2_support"].id,
        ),
        "manager": User(
            username="manager1",
            password_hash="x",
            first_name="Mira",
            last_name="Manager",
            email="manager1@example.com",
            department_id=departments["management"].id,
        ),
    }
    for user in u.values():
        db_session.add(user)
    db_session.commit()
    for user in u.values():
        db_session.refresh(user)
    return u


@pytest.fixture
def master_data(db_session):
    """Category, priority and status master data used across tests."""
    category = TicketCategory(code="NETWORK", name="Network")
    priority = TicketPriority(code="NORMAL", name="Normal", sla_minutes=240)
    statuses = {
        "open": TicketStatus(code="OPEN", name="Open", is_closed=False),
        "in_progress": TicketStatus(code="IN_PROGRESS", name="In Progress", is_closed=False),
        "escalated": TicketStatus(code="ESCALATED", name="Escalated", is_closed=False),
        "resolved": TicketStatus(code="RESOLVED", name="Resolved", is_closed=False),
        "closed": TicketStatus(code="CLOSED", name="Closed", is_closed=True),
    }
    db_session.add(category)
    db_session.add(priority)
    for s in statuses.values():
        db_session.add(s)
    db_session.commit()
    db_session.refresh(category)
    db_session.refresh(priority)
    for s in statuses.values():
        db_session.refresh(s)
    return {"category": category, "priority": priority, "statuses": statuses}


@pytest.fixture
def open_ticket(db_session, users, master_data):
    """A freshly created ticket, OPEN, tier 1, assigned to T1."""
    ticket = Ticket(
        ticket_no=f"INC-{uuid4().hex[:8].upper()}",
        title="Cannot access email system",
        description="Email system is not responding after password reset.",
        requester_id=users["customer"].id,
        category_id=master_data["category"].id,
        priority_id=master_data["priority"].id,
        status_id=master_data["statuses"]["open"].id,
        assigned_to=users["t1"].id,
        current_tier=1,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


# ---------------------------------------------------------------------------
# Local stand-ins for the future /resolve, /reopen, /reject, /close logic
# ---------------------------------------------------------------------------

def resolve_ticket(session, ticket, *, resolution_summary, status_id,
                    resolution_code=None, performed_by=None):
    """Stand-in for the /resolve endpoint: enforces the resolution
    requirement (a non-empty resolution_summary) before a ticket can move
    into a resolved state.
    """
    if not resolution_summary or not resolution_summary.strip():
        raise ValueError("resolution_summary is required to resolve a ticket")

    old_status_id = ticket.status_id
    ticket.resolution_summary = resolution_summary
    ticket.resolution_code = resolution_code
    ticket.resolved_at = datetime.now(timezone.utc)
    ticket.status_id = status_id
    session.add(
        TicketHistory(
            ticket_id=ticket.id,
            action="RESOLVE",
            field="status_id",
            old_value=str(old_status_id),
            new_value=str(status_id),
            performed_by=performed_by,
            remark=resolution_summary,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def reopen_ticket(session, ticket, *, status_id, performed_by=None, remark=None):
    """Stand-in for the /reopen endpoint: increments reopen_count and clears
    the previous resolution so the ticket can be worked again.
    """
    old_status_id = ticket.status_id
    ticket.reopen_count += 1
    ticket.resolved_at = None
    ticket.resolution_summary = None
    ticket.resolution_code = None
    ticket.status_id = status_id
    session.add(
        TicketHistory(
            ticket_id=ticket.id,
            action="REOPEN",
            field="status_id",
            old_value=str(old_status_id),
            new_value=str(status_id),
            performed_by=performed_by,
            remark=remark,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def reject_ticket(session, ticket, *, status_id, performed_by=None, remark=None):
    """Stand-in for the /reject endpoint (e.g. customer rejects the
    resolution): also counts as a reopen for reopen_count purposes.
    """
    old_status_id = ticket.status_id
    ticket.reopen_count += 1
    ticket.resolved_at = None
    ticket.resolution_summary = None
    ticket.resolution_code = None
    ticket.status_id = status_id
    session.add(
        TicketHistory(
            ticket_id=ticket.id,
            action="REJECT",
            field="status_id",
            old_value=str(old_status_id),
            new_value=str(status_id),
            performed_by=performed_by,
            remark=remark,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def close_ticket(session, ticket, *, status_id, performed_by=None):
    old_status_id = ticket.status_id
    ticket.status_id = status_id
    ticket.closed_at = datetime.now(timezone.utc)
    session.add(
        TicketHistory(
            ticket_id=ticket.id,
            action="CLOSE",
            field="status_id",
            old_value=str(old_status_id),
            new_value=str(status_id),
            performed_by=performed_by,
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


# ---------------------------------------------------------------------------
# Test 1: Full lifecycle - happy path with one reject cycle
# ---------------------------------------------------------------------------

class TestTicketLifecycleFull:
    """End-to-end test for the complete ticket lifecycle."""

    def test_full_lifecycle_scenario(self, db_session, users, master_data, open_ticket):
        statuses = master_data["statuses"]
        ticket = open_ticket
        assert ticket.status_id == statuses["open"].id
        assert ticket.current_tier == 1
        assert ticket.reopen_count == 0

        # ------------------------------------------------------------
        # T1 works on the ticket, cannot solve -> TECHNICAL escalation
        # ------------------------------------------------------------
        ticket.status_id = statuses["in_progress"].id
        db_session.commit()

        escalation_1 = TicketEscalation(
            ticket_id=ticket.id,
            escalation_type="TECHNICAL",
            from_tier=1,
            to_tier=2,
            from_user_id=users["t1"].id,
            reason_code="COMPLEXITY",
            comment="Needs deeper investigation than T1 scope allows.",
            escalated_by=users["t1"].id,
        )
        db_session.add(escalation_1)
        ticket.current_tier = 2
        ticket.assigned_to = users["t2"].id
        ticket.status_id = statuses["escalated"].id
        db_session.commit()
        db_session.refresh(ticket)

        assert ticket.current_tier == 2
        assert ticket.assigned_to == users["t2"].id

        # ------------------------------------------------------------
        # T2 investigates, escalates to Manager
        # ------------------------------------------------------------
        ticket.status_id = statuses["in_progress"].id
        db_session.commit()

        escalation_2 = TicketEscalation(
            ticket_id=ticket.id,
            escalation_type="TECHNICAL",
            from_tier=2,
            to_tier=3,
            from_user_id=users["t2"].id,
            reason_code="ACCESS_REQUIRED",
            comment="Requires manager-level system access to fix.",
            escalated_by=users["t2"].id,
        )
        db_session.add(escalation_2)
        ticket.current_tier = 3
        ticket.assigned_to = users["manager"].id
        ticket.status_id = statuses["escalated"].id
        db_session.commit()
        db_session.refresh(ticket)

        assert ticket.current_tier == 3
        assert ticket.assigned_to == users["manager"].id

        # ------------------------------------------------------------
        # Manager resolves (resolution requirement satisfied)
        # ------------------------------------------------------------
        resolve_ticket(
            db_session,
            ticket,
            resolution_summary="Manually reset password in AD and verified access.",
            resolution_code="AD_PASSWORD_RESET",
            status_id=statuses["resolved"].id,
            performed_by=users["manager"].id,
        )
        assert ticket.status_id == statuses["resolved"].id
        assert ticket.resolution_summary is not None
        assert ticket.resolved_at is not None
        assert ticket.reopen_count == 0

        # ------------------------------------------------------------
        # Customer rejects the resolution -> reopen_count increments
        # ------------------------------------------------------------
        reject_ticket(
            db_session,
            ticket,
            status_id=statuses["in_progress"].id,
            performed_by=users["customer"].id,
            remark="Still cannot log in from the mobile app.",
        )
        assert ticket.reopen_count == 1
        assert ticket.resolved_at is None
        assert ticket.resolution_summary is None

        # ------------------------------------------------------------
        # Manager resolves again
        # ------------------------------------------------------------
        resolve_ticket(
            db_session,
            ticket,
            resolution_summary="Also cleared cached credentials on the mobile client.",
            resolution_code="MOBILE_CACHE_CLEAR",
            status_id=statuses["resolved"].id,
            performed_by=users["manager"].id,
        )
        assert ticket.status_id == statuses["resolved"].id
        assert ticket.reopen_count == 1  # unchanged by a resolve

        # ------------------------------------------------------------
        # Customer confirms -> ticket CLOSED
        # ------------------------------------------------------------
        close_ticket(
            db_session,
            ticket,
            status_id=statuses["closed"].id,
            performed_by=users["customer"].id,
        )
        assert ticket.status_id == statuses["closed"].id
        assert ticket.closed_at is not None

        # ------------------------------------------------------------
        # Final verification: history + escalations recorded
        # ------------------------------------------------------------
        history = (
            db_session.query(TicketHistory)
            .filter(TicketHistory.ticket_id == ticket.id)
            .order_by(TicketHistory.performed_at)
            .all()
        )
        actions = [h.action for h in history]
        assert actions == ["RESOLVE", "REJECT", "RESOLVE", "CLOSE"]

        escalations = (
            db_session.query(TicketEscalation)
            .filter(TicketEscalation.ticket_id == ticket.id)
            .all()
        )
        assert len(escalations) == 2
        assert {e.to_tier for e in escalations} == {2, 3}


# ---------------------------------------------------------------------------
# Test 2: Resolution requirement
# ---------------------------------------------------------------------------

class TestResolutionRequirement:
    """/resolve must be given a non-empty resolution_summary."""

    def test_resolve_requires_resolution_summary(self, db_session, users, master_data, open_ticket):
        with pytest.raises(ValueError):
            resolve_ticket(
                db_session,
                open_ticket,
                resolution_summary="",
                status_id=master_data["statuses"]["resolved"].id,
                performed_by=users["t1"].id,
            )

    def test_resolve_rejects_whitespace_only_summary(self, db_session, users, master_data, open_ticket):
        with pytest.raises(ValueError):
            resolve_ticket(
                db_session,
                open_ticket,
                resolution_summary="   ",
                status_id=master_data["statuses"]["resolved"].id,
                performed_by=users["t1"].id,
            )

    def test_resolve_succeeds_with_summary(self, db_session, users, master_data, open_ticket):
        resolved = resolve_ticket(
            db_session,
            open_ticket,
            resolution_summary="Restarted the mail service; queue drained.",
            resolution_code="SERVICE_RESTART",
            status_id=master_data["statuses"]["resolved"].id,
            performed_by=users["t1"].id,
        )
        assert resolved.resolution_summary == "Restarted the mail service; queue drained."
        assert resolved.resolution_code == "SERVICE_RESTART"
        assert resolved.resolved_at is not None

    def test_resolution_fields_nullable_for_unresolved_ticket(self, open_ticket):
        """A freshly created ticket has no resolution recorded yet."""
        assert open_ticket.resolution_summary is None
        assert open_ticket.resolution_code is None
        assert open_ticket.resolved_at is None


# ---------------------------------------------------------------------------
# Test 3: reopen_count
# ---------------------------------------------------------------------------

class TestReopenCount:
    """reopen_count must be a real, persisted counter on the ticket."""

    def test_reopen_count_defaults_to_zero(self, open_ticket):
        assert open_ticket.reopen_count == 0

    def test_reopen_increments_reopen_count(self, db_session, users, master_data, open_ticket):
        statuses = master_data["statuses"]
        resolve_ticket(
            db_session, open_ticket,
            resolution_summary="Fixed once.",
            status_id=statuses["resolved"].id,
            performed_by=users["t1"].id,
        )
        reopen_ticket(
            db_session, open_ticket,
            status_id=statuses["in_progress"].id,
            performed_by=users["customer"].id,
        )
        assert open_ticket.reopen_count == 1

    def test_reject_increments_reopen_count(self, db_session, users, master_data, open_ticket):
        statuses = master_data["statuses"]
        resolve_ticket(
            db_session, open_ticket,
            resolution_summary="Fixed once.",
            status_id=statuses["resolved"].id,
            performed_by=users["t1"].id,
        )
        reject_ticket(
            db_session, open_ticket,
            status_id=statuses["in_progress"].id,
            performed_by=users["customer"].id,
        )
        assert open_ticket.reopen_count == 1

    def test_reopen_count_accumulates_across_multiple_cycles(
        self, db_session, users, master_data, open_ticket
    ):
        statuses = master_data["statuses"]
        for i in range(3):
            resolve_ticket(
                db_session, open_ticket,
                resolution_summary=f"Fix attempt {i + 1}.",
                status_id=statuses["resolved"].id,
                performed_by=users["t1"].id,
            )
            reopen_ticket(
                db_session, open_ticket,
                status_id=statuses["in_progress"].id,
                performed_by=users["customer"].id,
                remark=f"Still broken after attempt {i + 1}.",
            )
        assert open_ticket.reopen_count == 3

    def test_reopen_count_persists_after_reload(self, db_session, users, master_data, open_ticket):
        statuses = master_data["statuses"]
        resolve_ticket(
            db_session, open_ticket,
            resolution_summary="Fixed.",
            status_id=statuses["resolved"].id,
            performed_by=users["t1"].id,
        )
        reopen_ticket(
            db_session, open_ticket,
            status_id=statuses["in_progress"].id,
            performed_by=users["customer"].id,
        )
        ticket_id = open_ticket.id
        db_session.expire_all()

        reloaded = db_session.get(Ticket, ticket_id)
        assert reloaded.reopen_count == 1


# ---------------------------------------------------------------------------
# Test 4: Escalation edge cases (constraints on TicketEscalation)
# ---------------------------------------------------------------------------

class TestEscalationConstraints:
    """TECHNICAL escalations must increase tier and carry a valid reason_code."""

    def test_technical_escalation_requires_tier_increase(self, db_session, users, open_ticket):
        bad_escalation = TicketEscalation(
            ticket_id=open_ticket.id,
            escalation_type="TECHNICAL",
            from_tier=2,
            to_tier=2,  # no increase -> should violate the CHECK constraint
            reason_code="COMPLEXITY",
            escalated_by=users["t1"].id,
        )
        db_session.add(bad_escalation)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_technical_escalation_requires_known_reason_code(self, db_session, users, open_ticket):
        bad_escalation = TicketEscalation(
            ticket_id=open_ticket.id,
            escalation_type="TECHNICAL",
            from_tier=1,
            to_tier=2,
            reason_code="NOT_A_REAL_REASON",
            escalated_by=users["t1"].id,
        )
        db_session.add(bad_escalation)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_functional_escalation_requires_department(self, db_session, users, open_ticket):
        bad_escalation = TicketEscalation(
            ticket_id=open_ticket.id,
            escalation_type="FUNCTIONAL",
            from_tier=1,
            to_tier=1,
            to_department_id=None,  # required for FUNCTIONAL -> should violate CHECK
            escalated_by=users["t1"].id,
        )
        db_session.add(bad_escalation)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_functional_escalation_valid(self, db_session, users, departments, open_ticket):
        escalation = TicketEscalation(
            ticket_id=open_ticket.id,
            escalation_type="FUNCTIONAL",
            from_tier=1,
            to_tier=1,
            from_department_id=departments["helpdesk"].id,
            to_department_id=departments["l2_support"].id,
            escalated_by=users["t1"].id,
        )
        db_session.add(escalation)
        db_session.commit()
        db_session.refresh(escalation)
        assert escalation.id is not None