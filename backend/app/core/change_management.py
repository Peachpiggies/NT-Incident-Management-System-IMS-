"""
Change Management - End-to-End Flow
=====================================

Implements the six-stage change lifecycle:

    Change Management
    ├── Change Request        <-- Requester opens the change (DRAFT -> SUBMITTED)
    ├── Risk Assessment       <-- Risk level, impact, likelihood, mitigation plan
    ├── Approval               <-- CAB quorum sized by risk level / change type
    ├── Implementation          <-- Plan -> Scheduled -> In Progress -> Implemented
    ├── Validation              <-- Confirms the change achieved its intended outcome
    └── Rollback                <-- Only reachable if Validation fails

State diagram:

    DRAFT
      |
      v (submit)
    SUBMITTED --assess_risk()--> SUBMITTED (risk_assessment attached)
      |
      | record_approval() x N   (quorum depends on risk_level / change_type)
      |------------------------------+
      v                              v
    APPROVED                      REJECTED  (terminal)
      |
      v (create_implementation_plan + schedule)
    SCHEDULED
      |
      v (start_implementation)
    IN_PROGRESS
      |
      v (complete_implementation)
    IMPLEMENTED
      |
      v (validate)
      +---------------------+
      v                     v
    VALIDATED             FAILED
      |                     |
      |                     v (rollback)
      |                 ROLLED_BACK
      |                     |
      +----------+----------+
                 v (close)
               CLOSED

Design goals:
  - Approval cannot be recorded before Risk Assessment is attached, so a
    change can never reach the CAB without a documented risk profile.
  - Approval quorum scales with risk: LOW/MEDIUM need 1 approver, HIGH needs
    2, CRITICAL needs 3 - unless the change is EMERGENCY, which always uses
    a single-approver fast path (documented after the fact via
    `emergency_justification`).
  - A single REJECTED decision short-circuits the whole approval stage.
  - Rollback is only reachable from a FAILED validation - a VALIDATED
    change goes straight to CLOSED.

No third-party dependencies - stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# ---------------------------------------------------------------------------
# States / enums
# ---------------------------------------------------------------------------


class ChangeType(str, Enum):
    STANDARD = "STANDARD"
    NORMAL = "NORMAL"
    EMERGENCY = "EMERGENCY"


class ChangeStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    IMPLEMENTED = "IMPLEMENTED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CLOSED = "CLOSED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class ApprovalPolicy:
    """Business rules for how many approvals a change needs before it can
    move past the Approval stage."""

    quorum_by_risk: dict[RiskLevel, int] = field(
        default_factory=lambda: {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
    )
    emergency_quorum: int = 1  # EMERGENCY changes always use the fast path

    def required_approvals(self, change_type: ChangeType, risk_level: RiskLevel) -> int:
        if change_type == ChangeType.EMERGENCY:
            return self.emergency_quorum
        return self.quorum_by_risk[risk_level]


# ---------------------------------------------------------------------------
# Stage records
# ---------------------------------------------------------------------------


@dataclass
class RiskAssessment:
    risk_level: RiskLevel
    impact_description: str
    likelihood: str
    mitigation_plan: str | None
    assessed_by: str
    assessed_at: datetime


@dataclass
class Approval:
    approver: str
    decision: ApprovalDecision
    comments: str | None
    decided_at: datetime


@dataclass
class Implementation:
    implementation_plan: str
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None


@dataclass
class ValidationResult:
    validated_by: str
    validation_result: bool
    notes: str | None
    validated_at: datetime


@dataclass
class Rollback:
    reason: str
    rollback_plan: str
    initiated_by: str
    rolled_back_at: datetime | None = None


# ---------------------------------------------------------------------------
# Change Request (aggregate root)
# ---------------------------------------------------------------------------


@dataclass
class ChangeRequest:
    change_no: str
    title: str
    change_type: ChangeType
    status: ChangeStatus = ChangeStatus.DRAFT

    risk_assessment: RiskAssessment | None = None
    approvals: list[Approval] = field(default_factory=list)
    implementation: Implementation | None = None
    validation: ValidationResult | None = None
    rollback: Rollback | None = None

    emergency_justification: str | None = None

    # --------------------------------------------------------------
    # 1. Change Request
    # --------------------------------------------------------------

    def submit(self) -> None:
        if self.status != ChangeStatus.DRAFT:
            raise ValueError(f"Cannot submit from state {self.status}")
        self.status = ChangeStatus.SUBMITTED

    # --------------------------------------------------------------
    # 2. Risk Assessment
    # --------------------------------------------------------------

    def assess_risk(
        self,
        risk_level: RiskLevel,
        impact_description: str,
        likelihood: str,
        assessed_by: str,
        mitigation_plan: str | None = None,
    ) -> RiskAssessment:
        if self.status != ChangeStatus.SUBMITTED:
            raise ValueError(f"Cannot assess risk from state {self.status}")
        self.risk_assessment = RiskAssessment(
            risk_level=risk_level,
            impact_description=impact_description,
            likelihood=likelihood,
            mitigation_plan=mitigation_plan,
            assessed_by=assessed_by,
            assessed_at=datetime.now(timezone.utc),
        )
        return self.risk_assessment

    # --------------------------------------------------------------
    # 3. Approval
    # --------------------------------------------------------------

    def record_approval(
        self,
        approver: str,
        decision: ApprovalDecision,
        policy: ApprovalPolicy,
        comments: str | None = None,
        emergency_justification: str | None = None,
    ) -> Approval:
        if self.status != ChangeStatus.SUBMITTED:
            raise ValueError(f"Cannot record approval from state {self.status}")
        if self.risk_assessment is None:
            raise ValueError("Risk assessment must be attached before approval")
        if decision == ApprovalDecision.PENDING:
            raise ValueError("decision must be APPROVED or REJECTED")

        if self.change_type == ChangeType.EMERGENCY and emergency_justification:
            self.emergency_justification = emergency_justification

        approval = Approval(
            approver=approver,
            decision=decision,
            comments=comments,
            decided_at=datetime.now(timezone.utc),
        )
        self.approvals.append(approval)

        if decision == ApprovalDecision.REJECTED:
            self.status = ChangeStatus.REJECTED
            return approval

        required = policy.required_approvals(self.change_type, self.risk_assessment.risk_level)
        granted = sum(1 for a in self.approvals if a.decision == ApprovalDecision.APPROVED)
        if granted >= required:
            self.status = ChangeStatus.APPROVED

        return approval

    # --------------------------------------------------------------
    # 4. Implementation
    # --------------------------------------------------------------

    def create_implementation_plan(
        self,
        implementation_plan: str,
        scheduled_start: datetime | None = None,
        scheduled_end: datetime | None = None,
    ) -> Implementation:
        if self.status != ChangeStatus.APPROVED:
            raise ValueError(f"Cannot plan implementation from state {self.status}")
        self.implementation = Implementation(
            implementation_plan=implementation_plan,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )
        return self.implementation

    def schedule(self) -> None:
        if self.status != ChangeStatus.APPROVED:
            raise ValueError(f"Cannot schedule from state {self.status}")
        if self.implementation is None:
            raise ValueError("Implementation plan must be created before scheduling")
        self.status = ChangeStatus.SCHEDULED

    def start_implementation(self) -> None:
        if self.status != ChangeStatus.SCHEDULED:
            raise ValueError(f"Cannot start implementation from state {self.status}")
        self.implementation.started_at = datetime.now(timezone.utc)
        self.status = ChangeStatus.IN_PROGRESS

    def complete_implementation(self, notes: str | None = None) -> None:
        if self.status != ChangeStatus.IN_PROGRESS:
            raise ValueError(f"Cannot complete implementation from state {self.status}")
        self.implementation.completed_at = datetime.now(timezone.utc)
        self.implementation.notes = notes
        self.status = ChangeStatus.IMPLEMENTED

    # --------------------------------------------------------------
    # 5. Validation
    # --------------------------------------------------------------

    def validate(self, validated_by: str, success: bool, notes: str | None = None) -> ValidationResult:
        if self.status != ChangeStatus.IMPLEMENTED:
            raise ValueError(f"Cannot validate from state {self.status}")
        self.validation = ValidationResult(
            validated_by=validated_by,
            validation_result=success,
            notes=notes,
            validated_at=datetime.now(timezone.utc),
        )
        self.status = ChangeStatus.VALIDATED if success else ChangeStatus.FAILED
        return self.validation

    # --------------------------------------------------------------
    # 6. Rollback (only reachable after a failed validation)
    # --------------------------------------------------------------

    def initiate_rollback(self, reason: str, rollback_plan: str, initiated_by: str) -> Rollback:
        if self.status != ChangeStatus.FAILED:
            raise ValueError(f"Cannot roll back from state {self.status}")
        self.rollback = Rollback(
            reason=reason,
            rollback_plan=rollback_plan,
            initiated_by=initiated_by,
        )
        return self.rollback

    def complete_rollback(self) -> None:
        if self.status != ChangeStatus.FAILED or self.rollback is None:
            raise ValueError("Rollback must be initiated before it can complete")
        self.rollback.rolled_back_at = datetime.now(timezone.utc)
        self.status = ChangeStatus.ROLLED_BACK

    # --------------------------------------------------------------
    # Closure
    # --------------------------------------------------------------

    def close(self) -> None:
        if self.status not in (ChangeStatus.VALIDATED, ChangeStatus.ROLLED_BACK):
            raise ValueError(f"Cannot close from state {self.status}")
        self.status = ChangeStatus.CLOSED


# ---------------------------------------------------------------------------
# Demo / example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    policy = ApprovalPolicy()

    # --- Happy path: NORMAL change, HIGH risk, needs 2 approvals ---
    change = ChangeRequest(change_no="CHG-00042", title="Upgrade DB cluster", change_type=ChangeType.NORMAL)
    change.submit()
    change.assess_risk(
        risk_level=RiskLevel.HIGH,
        impact_description="Brief downtime during failover",
        likelihood="Unlikely",
        assessed_by="risk.analyst.mint",
        mitigation_plan="Failover to standby before patching primary",
    )
    change.record_approval("cab.member.ann", ApprovalDecision.APPROVED, policy)
    print(f"[1] status={change.status} (1/2 approvals)")
    change.record_approval("cab.member.beam", ApprovalDecision.APPROVED, policy)
    print(f"[2] status={change.status} (2/2 approvals)")

    change.create_implementation_plan("Apply patch to standby, failover, patch former primary")
    change.schedule()
    change.start_implementation()
    change.complete_implementation(notes="Failover completed without incident")
    print(f"[3] status={change.status}")

    change.validate(validated_by="qa.nott", success=True, notes="Cluster healthy post-patch")
    change.close()
    print(f"[4] status={change.status}  <-- validated, no rollback needed")

    # --- Unhappy path: validation fails -> rollback ---
    change2 = ChangeRequest(change_no="CHG-00043", title="New routing rule", change_type=ChangeType.STANDARD)
    change2.submit()
    change2.assess_risk(
        risk_level=RiskLevel.LOW,
        impact_description="Routing table update only",
        likelihood="Rare",
        assessed_by="risk.analyst.mint",
    )
    change2.record_approval("cab.member.ann", ApprovalDecision.APPROVED, policy)
    change2.create_implementation_plan("Push new routing rule to edge nodes")
    change2.schedule()
    change2.start_implementation()
    change2.complete_implementation()
    change2.validate(validated_by="qa.nott", success=False, notes="Increased latency observed")
    print(f"\n[5] status={change2.status}  <-- validation failed")

    change2.initiate_rollback(
        reason="Increased latency observed after cutover",
        rollback_plan="Revert edge nodes to previous routing table",
        initiated_by="oncall.engineer.beam",
    )
    change2.complete_rollback()
    change2.close()
    print(f"[6] status={change2.status}  <-- rolled back and closed")