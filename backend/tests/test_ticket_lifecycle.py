"""
Test suite for the complete ticket lifecycle scenario.

Scenario flow:
    Customer creates incident
        ↓
    T1 receives ticket
        ↓
    T1 works on ticket
        ↓
    T1 cannot solve
        ↓
    Technical/Functional escalation
        ↓
    T2 receives ticket
        ↓
    T2 investigates
        ↓
    T2 escalates to Manager
        ↓
    Manager resolves
        ↓
    Resolution recorded
        ↓
    Customer confirms
        ↓
    Ticket CLOSED
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base, User, Incident, Ticket, TicketChange,
    Resolution, CustomerConfirmation, Escalation, Comment
)
from app.services.ticket_workflow import TicketWorkflowService
from app.services.escalation import EscalationService
from app.services.incident_tracking import IncidentTrackingService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
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
def mock_current_user():
    """Mock the current user dependency."""
    user = User(
        id="user-customer-1",
        username="customer1",
        email="customer1@example.com",
        role="customer",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    return MagicMock(return_value=user)


@pytest.fixture
def mock_t1_user():
    """Mock Tier-1 support user."""
    user = User(
        id="user-t1-1",
        username="tech1",
        email="tech1@example.com",
        role="technician",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    return MagicMock(return_value=user)


@pytest.fixture
def mock_t2_user():
    """Mock Tier-2 support user."""
    user = User(
        id="user-t2-1",
        username="tech2",
        email="tech2@example.com",
        role="technician",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    return MagicMock(return_value=user)


@pytest.fixture
def mock_manager_user():
    """Mock manager user."""
    user = User(
        id="user-mgr-1",
        username="manager1",
        email="manager1@example.com",
        role="manager",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    return MagicMock(return_value=user)


@pytest.fixture
def workflow_service(db_session):
    """Create a TicketWorkflowService instance with the test database session."""
    return TicketWorkflowService(db_session)


@pytest.fixture
def escalation_service(db_session):
    """Create an EscalationService instance with the test database session."""
    return EscalationService(db_session)


# ---------------------------------------------------------------------------
# Helper: create test users
# ---------------------------------------------------------------------------

def _create_users(session):
    """Create all users needed for the scenario in a single helper."""
    users = {
        "customer": User(
            id="cust-1",
            username="customer1",
            email="customer1@example.com",
            role="customer",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ),
        "t1": User(
            id="t1-1",
            username="tech1",
            email="tech1@example.com",
            role="technician",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ),
        "t2": User(
            id="t2-1",
            username="tech2",
            email="tech2@example.com",
            role="technician",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ),
        "manager": User(
            id="mgr-1",
            username="manager1",
            email="manager1@example.com",
            role="manager",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ),
    }
    for u in users.values():
        session.add(u)
    session.commit()
    # Refresh to ensure IDs are populated
    for u in users.values():
        session.refresh(u)
    return users


# ---------------------------------------------------------------------------
# Test 1: Full Lifecycle — happy path
# ---------------------------------------------------------------------------

class TestTicketLifecycleFull:
    """End-to-end test for the complete ticket lifecycle."""

    def test_full_lifecycle_scenario(
        self,
        db_session,
        workflow_service,
        escalation_service,
    ):
        """
        Scenario:
            1. Customer creates incident
            2. T1 receives ticket
            3. T1 works on ticket
            4. T1 cannot solve → escalate
            5. T2 receives ticket
            6. T2 investigates
            7. T2 escalates to Manager
            8. Manager resolves
            9. Resolution recorded
            10. Customer confirms
            11. Ticket CLOSED
        """
        # Step 0 — create all users
        users = _create_users(db_session)

        # ------------------------------------------------------------------
        # Step 1: Customer creates incident
        # ------------------------------------------------------------------
        incident = workflow_service.create_incident(
            title="Cannot access email system",
            description="Email system is not responding after password reset.",
            incident_type="technical",
            severity="medium",
            reporter_id=users["customer"].id,
        )
        assert incident is not None
        assert incident.title == "Cannot access email system"
        assert incident.status == "open"
        incident_id = incident.id

        # ------------------------------------------------------------------
        # Step 2: T1 receives ticket (auto-assigned)
        # ------------------------------------------------------------------
        ticket = workflow_service.create_ticket(
            incident_id=incident_id,
            assigned_to_id=users["t1"].id,
            priority="normal",
            requester_id=users["customer"].id,
        )
        assert ticket is not None
        assert ticket.status == "open"
        assert ticket.assigned_to_id == users["t1"].id
        ticket_id = ticket.id

        # ------------------------------------------------------------------
        # Step 3: T1 works on ticket — transition to investigating
        # ------------------------------------------------------------------
        updated_ticket = workflow_service.transition_ticket(
            ticket_id=ticket_id,
            new_status="investigating",
            performed_by=users["t1"].id,
            notes="T1开始调查",
        )
        assert updated_ticket.status == "investigating"

        # Verify the ticket change was recorded
        changes = workflow_service.get_ticket_history(ticket_id=ticket_id)
        assert len(changes) >= 1
        assert any(c.new_status == "investigating" for c in changes)

        # ------------------------------------------------------------------
        # Step 4: T1 cannot solve → escalate (peer/technical escalation)
        # ------------------------------------------------------------------
        escalation = escalation_service.create_escalation(
            ticket_id=ticket_id,
            escalated_by=users["t1"].id,
            reason="T1无法解决，需要升级处理",
            escalation_level="technical",
        )
        assert escalation is not None
        assert escalation.status == "pending"
        escalation_id = escalation.id

        # Transition ticket to escalated status
        escalated_ticket = workflow_service.transition_ticket(
            ticket_id=ticket_id,
            new_status="escalated",
            performed_by=users["t1"].id,
            notes="Escalated to T2 for further investigation",
        )
        assert escalated_ticket.status == "escalated"

        # ------------------------------------------------------------------
        # Step 5: T2 receives ticket
        # ------------------------------------------------------------------
        # Reassign ticket to T2
        reassigned_ticket = workflow_service.assign_ticket(
            ticket_id=ticket_id,
            assigned_to_id=users["t2"].id,
            performed_by=users["t1"].id,
            reason="Escalated to T2",
        )
        assert reassigned_ticket.assigned_to_id == users["t2"].id

        # ------------------------------------------------------------------
        # Step 6: T2 investigates
        # ------------------------------------------------------------------
        investigating_ticket = workflow_service.transition_ticket(
            ticket_id=ticket_id,
            new_status="investigating",
            performed_by=users["t2"].id,
            notes="T2开始深入调查",
        )
        assert investigating_ticket.status == "investigating"

        # ------------------------------------------------------------------
        # Step 7: T2 escalates to Manager
        # ------------------------------------------------------------------
        mgr_escalation = escalation_service.create_escalation(
            ticket_id=ticket_id,
            escalated_by=users["t2"].id,
            reason="T2需要Manager批准解决方案",
            escalation_level="manager",
        )
        assert mgr_escalation is not None

        # Transition to awaiting_response (manager approval)
        awaiting_ticket = workflow_service.transition_ticket(
            ticket_id=ticket_id,
            new_status="awaiting_response",
            performed_by=users["t2"].id,
            notes="Escalated to Manager for resolution approval",
        )
        assert awaiting_ticket.status == "awaiting_response"

        # ------------------------------------------------------------------
        # Step 8: Manager resolves
        # ------------------------------------------------------------------
        resolved_ticket = workflow_service.transition_ticket(
            ticket_id=ticket_id,
            new_status="resolved",
            performed_by=users["manager"].id,
            notes="Manager resolved the issue — password reset completed manually",
        )
        assert resolved_ticket.status == "resolved"

        # ------------------------------------------------------------------
        # Step 9: Record resolution
        # ------------------------------------------------------------------
        resolution = workflow_service.record_resolution(
            ticket_id=ticket_id,
            resolved_by=users["manager"].id,
            resolution_type="fix",
            resolution_notes="Manually reset password in AD and verified access.",
            resolution_code="AD_PASSWORD_RESET",
        )
        assert resolution is not None
        assert resolution.resolution_type == "fix"
        assert resolution.resolved_by == users["manager"].id
        resolution_id = resolution.id

        # ------------------------------------------------------------------
        # Step 10: Customer confirms resolution
        # ------------------------------------------------------------------
        confirmation = workflow_service.record_customer_confirmation(
            ticket_id=ticket_id,
            confirmed_by=users["customer"].id,
            is_confirmed=True,
            feedback="The issue is resolved. Thank you!",
        )
        assert confirmation is not None
        assert confirmation.is_confirmed is True

        # ------------------------------------------------------------------
        # Step 11: Close the ticket
        # ------------------------------------------------------------------
        closed_ticket = workflow_service.transition_ticket(
            ticket_id=ticket_id,
            new_status="closed",
            performed_by=users["manager"].id,
            notes="Customer confirmed resolution — closing ticket.",
        )
        assert closed_ticket.status == "closed"

        # ------------------------------------------------------------------
        # Final verification
        # ------------------------------------------------------------------
        # Verify the incident was updated with the resolved ticket count
        db_session.refresh(incident)
        assert incident.status == "resolved"

        # Verify ticket history contains all transitions
        history = workflow_service.get_ticket_history(ticket_id=ticket_id)
        statuses_in_history = [h.new_status for h in history if h.new_status]
        assert "open" in statuses_in_history
        assert "investigating" in statuses_in_history
        assert "escalated" in statuses_in_history
        assert "resolved" in statuses_in_history
        assert "closed" in statuses_in_history

        # Verify escalation history
        escalations = escalation_service.get_escalations_for_ticket(ticket_id=ticket_id)
        assert len(escalations) >= 2  # technical + manager escalations

        # Verify the audit log
        audit_log = workflow_service.get_ticket_history(ticket_id=ticket_id)
        assert len(audit_log) >= 5  # multiple status transitions


# ---------------------------------------------------------------------------
# Test 2: Individual step tests
# ---------------------------------------------------------------------------

class TestIndividualSteps:
    """Test each step of the lifecycle individually."""

    def test_customer_creates_incident(self, db_session, workflow_service):
        """Step 1: Customer creates an incident."""
        users = _create_users(db_session)

        incident = workflow_service.create_incident(
            title="Network connectivity issue",
            description="Unable to connect to VPN.",
            incident_type="technical",
            severity="high",
            reporter_id=users["customer"].id,
        )

        assert incident.id is not None
        assert incident.title == "Network connectivity issue"
        assert incident.status == "open"
        assert incident.severity == "high"
        assert incident.reporter_id == users["customer"].id

    def test_t1_receives_ticket(self, db_session, workflow_service):
        """Step 2: T1 is assigned a ticket for an incident."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Software license expired",
            description="Adobe Creative Suite license has expired.",
            incident_type="service_request",
            severity="low",
            reporter_id=users["customer"].id,
        )

        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="low",
            requester_id=users["customer"].id,
        )

        assert ticket.status == "open"
        assert ticket.assigned_to_id == users["t1"].id
        assert ticket.incident_id == incident.id

    def test_t1_works_on_ticket(self, db_session, workflow_service):
        """Step 3: T1 starts working on the ticket."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Printer not responding",
            description="Network printer is offline.",
            incident_type="technical",
            severity="medium",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="normal",
            requester_id=users["customer"].id,
        )

        work_ticket = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="investigating",
            performed_by=users["t1"].id,
            notes="Checking printer queue and network connection.",
        )

        assert work_ticket.status == "investigating"

    def test_t1_escalates(self, db_session, escalation_service, workflow_service):
        """Step 4-5: T1 escalates because they cannot solve."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Database corruption detected",
            description="Primary database showing index corruption.",
            incident_type="technical",
            severity="critical",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="high",
            requester_id=users["customer"].id,
        )

        # Create escalation
        escalation = escalation_service.create_escalation(
            ticket_id=ticket.id,
            escalated_by=users["t1"].id,
            reason="Requires DBA expertise beyond T1 scope.",
            escalation_level="technical",
        )

        assert escalation.ticket_id == ticket.id
        assert escalation.escalated_by == users["t1"].id
        assert escalation.escalation_level == "technical"
        assert escalation.status == "pending"

        # Transition to escalated
        escalated = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="escalated",
            performed_by=users["t1"].id,
            notes="Escalating to specialist team.",
        )
        assert escalated.status == "escalated"

    def test_t2_investigates(self, db_session, workflow_service):
        """Step 6: T2 receives and investigates the escalated ticket."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="API gateway timeout",
            description="External API calls timing out after 30s.",
            incident_type="technical",
            severity="high",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t2"].id,
            priority="high",
            requester_id=users["customer"].id,
        )

        investigating = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="investigating",
            performed_by=users["t2"].id,
            notes="Analyzing API gateway logs and performance metrics.",
        )

        assert investigating.status == "investigating"
        assert investigating.assigned_to_id == users["t2"].id

    def test_t2_escalates_to_manager(self, db_session, escalation_service):
        """Step 7: T2 escalates to Manager for approval."""
        users = _create_users(db_session)
        incident = MagicMock()
        incident.id = "inc-mgr-test"
        db_session.add(incident)

        ticket = Ticket(
            id="tkt-mgr-test",
            incident_id=incident.id,
            assigned_to_id=users["t2"].id,
            status="investigating",
            priority="high",
            created_by=users["t2"].id,
        )
        db_session.add(ticket)
        db_session.commit()

        mgr_escalation = escalation_service.create_escalation(
            ticket_id=ticket.id,
            escalated_by=users["t2"].id,
            reason="需要Manager批准预算采购新license",
            escalation_level="manager",
        )

        assert mgr_escalation.escalation_level == "manager"
        assert mgr_escalation.status == "pending"

    def test_manager_resolves(self, db_session, workflow_service):
        """Step 8: Manager resolves the ticket."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Server capacity expansion needed",
            description="CPU utilization consistently above 90%.",
            incident_type="technical",
            severity="high",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["manager"].id,
            priority="high",
            requester_id=users["customer"].id,
        )

        resolved = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="resolved",
            performed_by=users["manager"].id,
            notes="Server expanded from 4 to 16 vCPUs and verified performance.",
        )

        assert resolved.status == "resolved"
        assert resolved.resolved_by == users["manager"].id

    def test_resolution_recorded(self, db_session, workflow_service):
        """Step 9: Resolution details are recorded."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="SSL certificate expired",
            description="Website showing security warning to users.",
            incident_type="technical",
            severity="critical",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["manager"].id,
            priority="high",
            requester_id=users["customer"].id,
        )

        # Resolve first
        workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="resolved",
            performed_by=users["manager"].id,
            notes="Certificate renewed and installed.",
        )

        # Record resolution details
        resolution = workflow_service.record_resolution(
            ticket_id=ticket.id,
            resolved_by=users["manager"].id,
            resolution_type="fix",
            resolution_notes="Renewed SSL certificate via Let's Encrypt and reloaded nginx.",
            resolution_code="SSL_RENEWAL",
        )

        assert resolution is not None
        assert resolution.resolution_type == "fix"
        assert resolution.resolution_code == "SSL_RENEWAL"
        assert resolution.ticket_id == ticket.id

    def test_customer_confirms(self, db_session, workflow_service):
        """Step 10: Customer confirms the resolution."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Email forwarding not working",
            description="Emails forwarded to mobile are not arriving.",
            incident_type="technical",
            severity="medium",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="normal",
            requester_id=users["customer"].id,
        )

        workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="resolved",
            performed_by=users["t1"].id,
            notes="Fixed email forwarding rule configuration.",
        )

        confirmation = workflow_service.record_customer_confirmation(
            ticket_id=ticket.id,
            confirmed_by=users["customer"].id,
            is_confirmed=True,
            feedback="Email forwarding is working now!",
        )

        assert confirmation.is_confirmed is True
        assert confirmation.ticket_id == ticket.id
        assert confirmation.confirmed_by == users["customer"].id
        assert "working" in confirmation.feedback.lower()

    def test_ticket_closed(self, db_session, workflow_service):
        """Step 11: Ticket is closed after customer confirmation."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Desk phone not working",
            description="VoIP phone showing no network connection.",
            incident_type="technical",
            severity="low",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="low",
            requester_id=users["customer"].id,
        )

        # Resolve and confirm
        workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="resolved",
            performed_by=users["t1"].id,
            notes="Replaced Ethernet cable and configured POE switch port.",
        )

        workflow_service.record_customer_confirmation(
            ticket_id=ticket.id,
            confirmed_by=users["customer"].id,
            is_confirmed=True,
            feedback="Phone is working.",
        )

        # Close the ticket
        closed = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="closed",
            performed_by=users["t1"].id,
            notes="Closed per confirmation.",
        )

        assert closed.status == "closed"


# ---------------------------------------------------------------------------
# Test 3: Edge cases — escalation service
# ---------------------------------------------------------------------------

class TestEscalationService:
    """Test EscalationService methods used in the lifecycle."""

    def test_create_escalation(self, db_session, escalation_service):
        """Test creating a new escalation record."""
        users = _create_users(db_session)

        ticket = Ticket(
            id="tkt-esc-1",
            incident_id="inc-esc-1",
            assigned_to_id=users["t1"].id,
            status="open",
            created_by=users["t1"].id,
        )
        db_session.add(ticket)
        db_session.commit()

        esc = escalation_service.create_escalation(
            ticket_id=ticket.id,
            escalated_by=users["t1"].id,
            reason="Cannot resolve independently.",
            escalation_level="technical",
        )

        assert esc.id is not None
        assert esc.ticket_id == ticket.id
        assert esc.status == "pending"

    def test_get_escalations_for_ticket(self, db_session, escalation_service):
        """Test retrieving all escalations for a ticket."""
        users = _create_users(db_session)

        ticket = Ticket(
            id="tkt-esc-2",
            incident_id="inc-esc-2",
            assigned_to_id=users["t1"].id,
            status="open",
            created_by=users["t1"].id,
        )
        db_session.add(ticket)
        db_session.commit()

        escalation_service.create_escalation(
            ticket_id=ticket.id,
            escalated_by=users["t1"].id,
            reason="Level 1 issue.",
            escalation_level="technical",
        )
        escalation_service.create_escalation(
            ticket_id=ticket.id,
            escalated_by=users["t2"].id,
            reason="Level 2 issue.",
            escalation_level="manager",
        )

        escalations = escalation_service.get_escalations_for_ticket(ticket_id=ticket.id)
        assert len(escalations) == 2

    def test_update_escalation_status(self, db_session, escalation_service):
        """Test updating escalation status to resolved."""
        users = _create_users(db_session)

        ticket = Ticket(
            id="tkt-esc-3",
            incident_id="inc-esc-3",
            assigned_to_id=users["t1"].id,
            status="open",
            created_by=users["t1"].id,
        )
        db_session.add(ticket)
        db_session.commit()

        esc = escalation_service.create_escalation(
            ticket_id=ticket.id,
            escalated_by=users["t1"].id,
            reason="Needs review.",
            escalation_level="manager",
        )

        updated = escalation_service.update_escalation_status(
            escalation_id=esc.id,
            new_status="resolved",
            updated_by=users["manager"].id,
        )

        assert updated.status == "resolved"
        assert updated.updated_by == users["manager"].id


# ---------------------------------------------------------------------------
# Test 4: Edge cases — workflow transitions
# ---------------------------------------------------------------------------

class TestWorkflowTransitions:
    """Test edge cases for ticket workflow transitions."""

    def test_ticket_status_sequence(self, db_session, workflow_service):
        """Verify a valid status transition sequence."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Valid sequence test",
            description="Testing valid status transitions.",
            incident_type="technical",
            severity="low",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="low",
            requester_id=users["customer"].id,
        )

        # open → investigating → escalated → resolved → closed
        t1 = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="investigating",
            performed_by=users["t1"].id,
        )
        assert t1.status == "investigating"

        t2 = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="escalated",
            performed_by=users["t1"].id,
        )
        assert t2.status == "escalated"

        t3 = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="resolved",
            performed_by=users["manager"].id,
        )
        assert t3.status == "resolved"

        t4 = workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="closed",
            performed_by=users["t1"].id,
        )
        assert t4.status == "closed"

    def test_get_ticket_history(self, db_session, workflow_service):
        """Verify ticket history captures all changes."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="History test",
            description="Checking that history is recorded.",
            incident_type="service_request",
            severity="low",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="low",
            requester_id=users["customer"].id,
        )

        workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="investigating",
            performed_by=users["t1"].id,
            notes="First note.",
        )
        workflow_service.transition_ticket(
            ticket_id=ticket.id,
            new_status="resolved",
            performed_by=users["t1"].id,
            notes="Second note.",
        )

        history = workflow_service.get_ticket_history(ticket_id=ticket.id)
        assert len(history) >= 2
        notes = [h.notes for h in history if h.notes]
        assert "First note." in notes
        assert "Second note." in notes

    def test_record_resolution(self, db_session, workflow_service):
        """Verify resolution is recorded with all details."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Resolution test",
            description="Testing resolution recording.",
            incident_type="technical",
            severity="medium",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="normal",
            requester_id=users["customer"].id,
        )

        resolution = workflow_service.record_resolution(
            ticket_id=ticket.id,
            resolved_by=users["t1"].id,
            resolution_type="workaround",
            resolution_notes="Temporary workaround applied.",
            resolution_code="TMP_FIX",
        )

        assert resolution.ticket_id == ticket.id
        assert resolution.resolved_by == users["t1"].id
        assert resolution.resolution_type == "workaround"
        assert resolution.resolution_code == "TMP_FIX"
        assert resolution.resolved_at is not None

    def test_customer_confirmation_not_confirmed(self, db_session, workflow_service):
        """Test customer confirmation with negative feedback."""
        users = _create_users(db_session)
        incident = workflow_service.create_incident(
            title="Not confirmed test",
            description="Customer did not confirm.",
            incident_type="technical",
            severity="low",
            reporter_id=users["customer"].id,
        )
        ticket = workflow_service.create_ticket(
            incident_id=incident.id,
            assigned_to_id=users["t1"].id,
            priority="low",
            requester_id=users["customer"].id,
        )

        confirmation = workflow_service.record_customer_confirmation(
            ticket_id=ticket.id,
            confirmed_by=users["customer"].id,
            is_confirmed=False,
            feedback="Still not working.",
        )

        assert confirmation.is_confirmed is False