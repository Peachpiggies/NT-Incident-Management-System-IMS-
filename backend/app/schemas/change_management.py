"""
Change Management schemas.

Pydantic models for change requests, risk assessment, approvals,
implementation, validation, and rollback.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import UserSummary


# ==========================================================
# Enums
# ==========================================================


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


# ==========================================================
# Change Request
# ==========================================================


class ChangeRequestBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=10)
    change_type: ChangeType
    priority_id: UUID
    service_id: UUID | None = None
    problem_id: UUID | None = Field(None, description="Problem this change resolves, if any")
    planned_start: datetime
    planned_end: datetime

    @model_validator(mode="after")
    def _check_window(self) -> "ChangeRequestBase":
        if self.planned_end <= self.planned_start:
            raise ValueError("planned_end must be after planned_start")
        return self


class ChangeRequestCreate(ChangeRequestBase):
    pass


class ChangeRequestUpdate(BaseModel):
    title: str | None = Field(None, min_length=5, max_length=255)
    description: str | None = Field(None, min_length=10)
    change_type: ChangeType | None = None
    priority_id: UUID | None = None
    service_id: UUID | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None


class ChangeRequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_no: str
    title: str
    change_type: ChangeType
    status: ChangeStatus
    risk_level: RiskLevel | None = None
    planned_start: datetime
    created_at: datetime


class ChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_no: str
    title: str
    description: str
    change_type: ChangeType
    status: ChangeStatus
    risk_level: RiskLevel | None = None

    service_id: UUID | None = None
    problem_id: UUID | None = None

    requested_by: UserSummary
    planned_start: datetime
    planned_end: datetime

    created_at: datetime
    updated_at: datetime


class ChangeRequestListResponse(BaseModel):
    items: list[ChangeRequestSummary]
    total: int
    page: int
    page_size: int


# ==========================================================
# Risk Assessment
# ==========================================================


class RiskAssessmentBase(BaseModel):
    change_request_id: UUID
    risk_level: RiskLevel
    impact_description: str = Field(..., min_length=5, max_length=4000)
    likelihood: str = Field(..., min_length=2, max_length=100, description="e.g. 'Rare', 'Likely'")
    mitigation_plan: str | None = Field(None, max_length=4000)


class RiskAssessmentCreate(RiskAssessmentBase):
    pass


class RiskAssessmentUpdate(BaseModel):
    risk_level: RiskLevel | None = None
    impact_description: str | None = Field(None, min_length=5, max_length=4000)
    likelihood: str | None = Field(None, min_length=2, max_length=100)
    mitigation_plan: str | None = Field(None, max_length=4000)


class RiskAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_request_id: UUID
    risk_level: RiskLevel
    impact_description: str
    likelihood: str
    mitigation_plan: str | None = None
    assessed_by: UserSummary
    created_at: datetime


# ==========================================================
# Approval
# ==========================================================


class ChangeApprovalCreate(BaseModel):
    """Record an approver's decision on a change request."""

    change_request_id: UUID
    decision: ApprovalDecision
    comments: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check_decision(self) -> "ChangeApprovalCreate":
        if self.decision == ApprovalDecision.PENDING:
            raise ValueError("decision must be APPROVED or REJECTED")
        return self


class ChangeApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_request_id: UUID
    approver: UserSummary
    decision: ApprovalDecision
    comments: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class ChangeApprovalListResponse(BaseModel):
    items: list[ChangeApprovalResponse]
    total: int


# ==========================================================
# Implementation
# ==========================================================


class ChangeImplementationCreate(BaseModel):
    change_request_id: UUID
    implementation_plan: str = Field(..., min_length=5)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None


class ChangeImplementationUpdate(BaseModel):
    """Mark implementation progress: start it, complete it, or add notes."""

    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = Field(None, max_length=4000)


class ChangeImplementationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_request_id: UUID
    implementation_plan: str
    implemented_by: UserSummary | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None
    created_at: datetime


# ==========================================================
# Validation
# ==========================================================


class ChangeValidationCreate(BaseModel):
    change_request_id: UUID
    validation_result: bool = Field(..., description="True if the change achieved its intended outcome")
    notes: str | None = Field(None, max_length=4000)


class ChangeValidationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_request_id: UUID
    validated_by: UserSummary
    validation_result: bool
    notes: str | None = None
    validated_at: datetime


# ==========================================================
# Rollback
# ==========================================================


class ChangeRollbackCreate(BaseModel):
    change_request_id: UUID
    reason: str = Field(..., min_length=5, max_length=2000)
    rollback_plan: str = Field(..., min_length=5)


class ChangeRollbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_request_id: UUID
    reason: str
    rollback_plan: str
    initiated_by: UserSummary
    rolled_back_at: datetime | None = None
    created_at: datetime
