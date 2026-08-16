"""
Root Cause Analysis schemas.

Pydantic models for root causes, contributing factors, impact
analysis, and the resulting RCA report.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import UserSummary

# ==========================================================
# Enums
# ==========================================================


class RCAReportStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"


class BusinessImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


# ==========================================================
# Root Cause
# ==========================================================
# A root cause analysis is anchored to either a ticket (incident-level RCA)
# or a problem (problem-level RCA covering multiple related incidents).


class RootCauseBase(BaseModel):
    ticket_id: UUID | None = None
    problem_id: UUID | None = None
    category: str = Field(..., min_length=2, max_length=100, description="e.g. 'Human Error', 'Hardware Failure'")
    description: str = Field(..., min_length=10)

    @model_validator(mode="after")
    def _check_anchor(self) -> "RootCauseBase":
        if not self.ticket_id and not self.problem_id:
            raise ValueError("one of ticket_id or problem_id is required")
        return self


class RootCauseCreate(RootCauseBase):
    pass


class RootCauseUpdate(BaseModel):
    category: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, min_length=10)


class RootCauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID | None = None
    problem_id: UUID | None = None
    category: str
    description: str
    identified_by: UserSummary
    created_at: datetime
    updated_at: datetime


# ==========================================================
# Contributing Factors
# ==========================================================


class ContributingFactorBase(BaseModel):
    root_cause_id: UUID
    factor_type: str = Field(..., min_length=2, max_length=100, description="e.g. 'Process Gap', 'Monitoring Gap'")
    description: str = Field(..., min_length=5, max_length=2000)


class ContributingFactorCreate(ContributingFactorBase):
    pass


class ContributingFactorUpdate(BaseModel):
    factor_type: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, min_length=5, max_length=2000)


class ContributingFactorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    root_cause_id: UUID
    factor_type: str
    description: str
    created_at: datetime


# ==========================================================
# Impact Analysis
# ==========================================================


class ImpactAnalysisBase(BaseModel):
    root_cause_id: UUID
    affected_service_ids: list[UUID] = Field(default_factory=list)
    affected_users_count: int = Field(0, ge=0)
    downtime_minutes: int = Field(0, ge=0)
    business_impact: BusinessImpactLevel = BusinessImpactLevel.LOW
    financial_impact: float | None = Field(None, ge=0, description="Estimated cost in local currency")
    notes: str | None = Field(None, max_length=2000)


class ImpactAnalysisCreate(ImpactAnalysisBase):
    pass


class ImpactAnalysisUpdate(BaseModel):
    affected_service_ids: list[UUID] | None = None
    affected_users_count: int | None = Field(None, ge=0)
    downtime_minutes: int | None = Field(None, ge=0)
    business_impact: BusinessImpactLevel | None = None
    financial_impact: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)


class ImpactAnalysisResponse(ImpactAnalysisBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


# ==========================================================
# RCA Report
# ==========================================================


class RCAReportBase(BaseModel):
    ticket_id: UUID | None = None
    problem_id: UUID | None = None
    root_cause_id: UUID
    title: str = Field(..., min_length=5, max_length=255)
    summary: str = Field(..., min_length=10)
    timeline: str | None = Field(None, description="Narrative or structured timeline of events")
    corrective_actions: str | None = Field(None, max_length=4000)
    preventive_actions: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def _check_anchor(self) -> "RCAReportBase":
        if not self.ticket_id and not self.problem_id:
            raise ValueError("one of ticket_id or problem_id is required")
        return self


class RCAReportCreate(RCAReportBase):
    pass


class RCAReportUpdate(BaseModel):
    title: str | None = Field(None, min_length=5, max_length=255)
    summary: str | None = Field(None, min_length=10)
    timeline: str | None = None
    corrective_actions: str | None = Field(None, max_length=4000)
    preventive_actions: str | None = Field(None, max_length=4000)


class RCAReportApprove(BaseModel):
    comment: str | None = Field(None, max_length=1000)


class RCAReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID | None = None
    problem_id: UUID | None = None
    root_cause: RootCauseResponse
    title: str
    summary: str
    timeline: str | None = None
    corrective_actions: str | None = None
    preventive_actions: str | None = None
    status: RCAReportStatus

    prepared_by: UserSummary
    approved_by: UserSummary | None = None
    approved_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


class RCAReportListResponse(BaseModel):
    items: list[RCAReportResponse]
    total: int
    page: int
    page_size: int
