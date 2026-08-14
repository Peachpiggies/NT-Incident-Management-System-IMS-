"""
SLA Engine schemas.

Pydantic models for SLA policies/targets, response & resolution timers,
pause/resume rules, breach detection, and escalation triggers.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import DepartmentSummary, PrioritySummary, StatusSummary


# ==========================================================
# Enums
# ==========================================================


class SlaMetricType(str, Enum):
    """Which clock a target/timer applies to."""

    RESPONSE = "RESPONSE"
    RESOLUTION = "RESOLUTION"


class SlaTimerState(str, Enum):
    """Current state of a running SLA timer."""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class SlaBreachStatus(str, Enum):
    """Where a timer stands relative to its target."""

    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"


# ==========================================================
# SLA Policy
# ==========================================================


class SLAPolicyBase(BaseModel):
    """Shared SLA policy fields."""

    name: str = Field(..., min_length=3, max_length=150)
    description: str | None = Field(None, max_length=2000)
    category_id: UUID | None = None
    service_id: UUID | None = None
    department_id: UUID | None = None
    is_active: bool = True


class SLAPolicyCreate(SLAPolicyBase):
    pass


class SLAPolicyUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=150)
    description: str | None = Field(None, max_length=2000)
    category_id: UUID | None = None
    service_id: UUID | None = None
    department_id: UUID | None = None
    is_active: bool | None = None


class SLAPolicyResponse(SLAPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    targets: list["SLATargetResponse"] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SLAPolicyListResponse(BaseModel):
    items: list[SLAPolicyResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# SLA Target
# ==========================================================


class SLATargetBase(BaseModel):
    """A single response/resolution target for a priority under a policy."""

    policy_id: UUID
    priority_id: UUID
    metric_type: SlaMetricType
    duration_minutes: int = Field(..., gt=0)
    business_hours_only: bool = True


class SLATargetCreate(SLATargetBase):
    pass


class SLATargetUpdate(BaseModel):
    duration_minutes: int | None = Field(None, gt=0)
    business_hours_only: bool | None = None


class SLATargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    priority: PrioritySummary
    metric_type: SlaMetricType
    duration_minutes: int
    business_hours_only: bool
    created_at: datetime


SLAPolicyResponse.model_rebuild()


# ==========================================================
# Pause / Resume Rules
# ==========================================================
# NOTE: pause rules are policy-level config (e.g. "pause the clock while a
# ticket sits in Awaiting Customer"); the actual pause/resume *events* for a
# specific ticket timer are `SLATimerPause` / `SLATimerResume` below.


class SLAPauseRuleBase(BaseModel):
    """Statuses that automatically pause an SLA timer while active."""

    policy_id: UUID
    status_id: UUID
    reason: str | None = Field(None, max_length=255)


class SLAPauseRuleCreate(SLAPauseRuleBase):
    pass


class SLAPauseRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    status: StatusSummary
    reason: str | None = None
    created_at: datetime


# ==========================================================
# Response / Resolution Timer
# ==========================================================


class SLATimerResponse(BaseModel):
    """Live state of a ticket's response or resolution timer."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID
    target_id: UUID
    metric_type: SlaMetricType
    state: SlaTimerState

    started_at: datetime
    due_at: datetime
    paused_at: datetime | None = None
    resumed_at: datetime | None = None
    stopped_at: datetime | None = None

    elapsed_minutes: int = Field(..., ge=0)
    remaining_minutes: int | None = None
    breach_status: SlaBreachStatus = SlaBreachStatus.ON_TRACK


class SLATimerPause(BaseModel):
    """Manually pause a running timer."""

    reason: str = Field(..., min_length=1, max_length=500)


class SLATimerResume(BaseModel):
    """Resume a paused timer."""

    reason: str | None = Field(None, max_length=500)


# ==========================================================
# Breach Detection
# ==========================================================


class SLABreachResponse(BaseModel):
    """Record of a detected (or pending) breach for a ticket timer."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID
    target_id: UUID
    metric_type: SlaMetricType
    due_at: datetime
    breached_at: datetime | None = None
    breach_status: SlaBreachStatus
    minutes_over: int | None = Field(None, ge=0)


class SLABreachListResponse(BaseModel):
    items: list[SLABreachResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Escalation Trigger
# ==========================================================


class SLAEscalationTriggerBase(BaseModel):
    """
    Fires when a timer crosses `trigger_at_percent` of its target duration
    (e.g. 80% elapsed) or upon breach itself (100%+).
    """

    policy_id: UUID
    trigger_at_percent: int = Field(..., ge=1, le=200, description="% of target duration elapsed")
    escalate_to_department_id: UUID | None = None
    escalate_to_tier: int | None = Field(None, ge=1, le=3)
    notify_user_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def _check_target(self) -> "SLAEscalationTriggerBase":
        if self.escalate_to_department_id is None and self.escalate_to_tier is None:
            raise ValueError(
                "at least one of escalate_to_department_id or escalate_to_tier is required"
            )
        return self


class SLAEscalationTriggerCreate(SLAEscalationTriggerBase):
    pass


class SLAEscalationTriggerUpdate(BaseModel):
    trigger_at_percent: int | None = Field(None, ge=1, le=200)
    escalate_to_department_id: UUID | None = None
    escalate_to_tier: int | None = Field(None, ge=1, le=3)
    notify_user_ids: list[UUID] | None = None
    is_active: bool | None = None


class SLAEscalationTriggerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    trigger_at_percent: int
    escalate_to_department: DepartmentSummary | None = None
    escalate_to_tier: int | None = None
    notify_user_ids: list[UUID] = Field(default_factory=list)
    is_active: bool
    created_at: datetime


class SLAEscalationTriggerListResponse(BaseModel):
    items: list[SLAEscalationTriggerResponse]
    total: int
    page: int
    page_size: int
