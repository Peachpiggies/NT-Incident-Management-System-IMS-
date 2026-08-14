"""
SLA policy schemas.

This module contains all request/response schemas for administering SLA
policies and their RESPONSE/RESOLUTION targets (sla_policies / sla_targets).
Ticket-facing SLA status (the running timers) lives in app.schemas.ticket
(TicketSlaStatus / TicketSlaTimerSummary) instead — this module is the
admin-configuration side, that one is the runtime side.
"""

from collections import Counter
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import StatusSummary
from app.schemas.ticket import TicketSlaMetricType


# ==========================================================
# Target — Base / Create / Update / Response
# ==========================================================


class SLATargetBase(BaseModel):
    """Shared target fields."""

    metric_type: TicketSlaMetricType
    target_minutes: int = Field(..., ge=1)
    warning_threshold_pct: int = Field(80, ge=1, le=100)


class SLATargetCreate(SLATargetBase):
    """Create a target, nested under SLAPolicyCreate."""


class SLATargetUpdate(BaseModel):
    """Update a target. metric_type is immutable (it's half of the
    policy_id + metric_type unique key) — create a new target instead of
    trying to repoint an existing one at a different metric.
    """

    target_minutes: int | None = Field(None, ge=1)
    warning_threshold_pct: int | None = Field(None, ge=1, le=100)


class SLATargetResponse(SLATargetBase):
    """Full target record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    created_at: datetime
    updated_at: datetime


# ==========================================================
# Policy — Base
# ==========================================================


class SLAPolicyBase(BaseModel):
    """Shared policy fields.

    The department/category/subcategory/service/priority filters are all
    optional: NULL means "matches any" at that dimension. When more than
    one active policy matches a ticket, the one with the lowest
    match_priority wins — e.g. a priority-specific policy (match_priority=10)
    should outrank a department-wide fallback (match_priority=100).
    """

    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = None

    department_id: UUID | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    service_id: UUID | None = None
    priority_id: UUID | None = None

    match_priority: int = Field(100, ge=0, description="Lower wins when multiple policies match")
    business_hours_only: bool = False
    is_active: bool = True


# ==========================================================
# Policy — Create / Update
# ==========================================================


class SLAPolicyCreate(SLAPolicyBase):
    """Create a policy along with its RESPONSE/RESOLUTION targets."""

    targets: list[SLATargetCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_unique_metric_types(self) -> "SLAPolicyCreate":
        counts = Counter(t.metric_type for t in self.targets)
        duplicates = [metric for metric, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(
                f"duplicate target metric_type(s): {', '.join(m.value for m in duplicates)}"
            )
        return self


class SLAPolicyUpdate(BaseModel):
    """Update policy metadata. All fields optional. Targets are managed via
    their own create/update endpoints, not through this schema — a policy
    already in use by running timers shouldn't have its targets silently
    swapped out from under them.
    """

    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = None

    department_id: UUID | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    service_id: UUID | None = None
    priority_id: UUID | None = None

    match_priority: int | None = Field(None, ge=0)
    business_hours_only: bool | None = None
    is_active: bool | None = None


# ==========================================================
# Policy — Response
# ==========================================================


class SLAPolicyResponse(SLAPolicyBase):
    """Full policy record, with its targets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    targets: list[SLATargetResponse] = []


class SLAPolicyListResponse(BaseModel):
    """Paginated list of policies."""

    items: list[SLAPolicyResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Summary
# ==========================================================


class SLAPolicySummary(BaseModel):
    """Lightweight policy reference for nested display (e.g. on a ticket_sla_timer)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


# ==========================================================
# Pause Rule — Base / Create / Update / Response
# ==========================================================
# A status that, while a ticket sits in it, automatically pauses every
# RUNNING timer on this policy (e.g. "pause while Awaiting Customer").
# Runtime side: app.services.sla_engine.apply_status_pause_rules, called
# after a status transition commits. Manual pause/resume of an individual
# timer doesn't go through this table at all -- see SLATimerPause /
# SLATimerResume in app.schemas.ticket.


class SLAPauseRuleBase(BaseModel):
    """Shared pause-rule fields."""

    policy_id: UUID
    status_id: UUID
    reason: str | None = Field(None, max_length=255)
    is_active: bool = True


class SLAPauseRuleCreate(SLAPauseRuleBase):
    """Create a pause rule. (policy_id, status_id) must be unique --
    creating a second rule for the same pair is a 409, not a silent upsert.
    """


class SLAPauseRuleUpdate(BaseModel):
    """Update a pause rule. `policy_id`/`status_id` are immutable -- they
    define which rule this is; repoint by deleting and creating a new one.
    """

    reason: str | None = Field(None, max_length=255)
    is_active: bool | None = None


class SLAPauseRuleResponse(BaseModel):
    """Full pause-rule record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    status: StatusSummary
    reason: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SLAPauseRuleListResponse(BaseModel):
    """List of pause rules (unpaginated -- a policy has at most a handful)."""

    items: list[SLAPauseRuleResponse]