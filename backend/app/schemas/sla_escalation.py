"""
SLA escalation trigger schemas.

Admin-configuration side of escalation, same split as sla_policy.py: this
module is "what should happen and to whom", app/services/sla_engine.py's
evaluate_escalations() is the runtime side that actually walks timers and
fires triggers.

An SLAEscalationTrigger belongs to a policy and fires when a timer on that
policy crosses a threshold:
  - WARNING: the target's own `warning_threshold_pct` (on SLATarget, see
    sla_policy.py) is crossed while still RUNNING -- a "heads up, about to
    breach" notice.
  - BREACH: the timer actually flips to BREACHED.

A trigger can be scoped to one metric_type or left NULL to apply to both
RESPONSE and RESOLUTION targets on the policy.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.notification import NotificationChannel
from app.schemas.ticket import TicketSlaMetricType

# ==========================================================
# Enums
# ==========================================================


class SLAEscalationTriggerOn(str, Enum):
    """Which threshold crossing fires this trigger."""

    WARNING = "WARNING"
    BREACH = "BREACH"


# ==========================================================
# Base / Create / Update
# ==========================================================


class SLAEscalationTriggerBase(BaseModel):
    """Shared escalation-trigger fields."""

    policy_id: UUID

    trigger_on: SLAEscalationTriggerOn

    metric_type: TicketSlaMetricType | None = Field(
        None, description="NULL applies to both RESPONSE and RESOLUTION targets on the policy"
    )

    escalate_to_department_id: UUID | None = None
    escalate_to_tier: int | None = Field(None, ge=1, le=3)

    notify_user_ids: list[UUID] = Field(default_factory=list)
    notify_role_ids: list[UUID] = Field(default_factory=list)
    channels: list[NotificationChannel] = Field(..., min_length=1)

    is_active: bool = True

    @model_validator(mode="after")
    def _check_has_target(self) -> "SLAEscalationTriggerBase":
        if (
            self.escalate_to_department_id is None
            and self.escalate_to_tier is None
            and not self.notify_user_ids
            and not self.notify_role_ids
        ):
            raise ValueError(
                "trigger needs at least one of escalate_to_department_id, "
                "escalate_to_tier, notify_user_ids, or notify_role_ids -- "
                "otherwise it fires and reaches nobody"
            )
        return self


class SLAEscalationTriggerCreate(SLAEscalationTriggerBase):
    """Create a trigger, nested under a policy or standalone."""


class SLAEscalationTriggerUpdate(BaseModel):
    """Update a trigger. All fields optional. `policy_id`/`trigger_on` are
    immutable for the same reason SLATargetUpdate keeps metric_type
    immutable -- they're part of what makes this trigger the one that
    fires at a given moment; repointing them is really "create a new
    trigger, delete the old one".
    """

    metric_type: TicketSlaMetricType | None = None
    escalate_to_department_id: UUID | None = None
    escalate_to_tier: int | None = Field(None, ge=1, le=3)
    notify_user_ids: list[UUID] | None = None
    notify_role_ids: list[UUID] | None = None
    channels: list[NotificationChannel] | None = Field(None, min_length=1)
    is_active: bool | None = None


# ==========================================================
# Response
# ==========================================================


class SLAEscalationTriggerResponse(SLAEscalationTriggerBase):
    """Full trigger record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class SLAEscalationTriggerListResponse(BaseModel):
    """Paginated list of triggers."""

    items: list[SLAEscalationTriggerResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Firing record
# ==========================================================
# One row per trigger firing on a specific timer -- lets you answer "did
# ticket X already get warned/escalated for its RESOLUTION timer" without
# re-deriving it from TicketHistory text, and gives evaluate_escalations()
# something to check before re-firing an already-fired trigger.


class SLAEscalationEventResponse(BaseModel):
    """Record of a single trigger firing."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trigger_id: UUID
    timer_id: UUID
    ticket_id: UUID
    trigger_on: SLAEscalationTriggerOn
    fired_at: datetime


class SLAEscalationEventListResponse(BaseModel):
    items: list[SLAEscalationEventResponse]
    total: int
