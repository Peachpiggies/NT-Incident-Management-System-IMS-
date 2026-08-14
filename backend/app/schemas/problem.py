"""
Problem Management schemas.

Pydantic models for problems, known errors, problem <-> incident
linking, workarounds, and permanent fixes.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CategorySummary, PrioritySummary, UserSummary


# ==========================================================
# Enums
# ==========================================================


class ProblemStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    KNOWN_ERROR = "KNOWN_ERROR"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class WorkaroundEffectiveness(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PARTIAL = "PARTIAL"
    EFFECTIVE = "EFFECTIVE"
    INEFFECTIVE = "INEFFECTIVE"


# ==========================================================
# Problem
# ==========================================================


class ProblemBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=10)
    category_id: UUID
    priority_id: UUID
    department_id: UUID | None = None


class ProblemCreate(ProblemBase):
    pass


class ProblemUpdate(BaseModel):
    title: str | None = Field(None, min_length=5, max_length=255)
    description: str | None = Field(None, min_length=10)
    category_id: UUID | None = None
    priority_id: UUID | None = None
    department_id: UUID | None = None


class ProblemStatusUpdate(BaseModel):
    status: ProblemStatus
    remark: str | None = Field(None, max_length=2000)


class ProblemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_no: str
    title: str
    status: ProblemStatus
    priority: PrioritySummary
    created_at: datetime


class ProblemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_no: str
    title: str
    description: str

    category: CategorySummary
    priority: PrioritySummary
    status: ProblemStatus

    owner: UserSummary | None = None
    related_incident_count: int = 0

    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None


class ProblemListResponse(BaseModel):
    items: list[ProblemSummary]
    total: int
    page: int
    page_size: int


# ==========================================================
# Known Error
# ==========================================================
# A problem moves into the Known Error Database (KEDB) once its root cause
# and (usually) a workaround are documented but a permanent fix isn't in
# place yet -- see `Problem.status == KNOWN_ERROR`.


class KnownErrorBase(BaseModel):
    problem_id: UUID
    symptoms: str = Field(..., min_length=5, max_length=4000)
    root_cause_summary: str | None = Field(None, max_length=4000)
    workaround_id: UUID | None = None
    is_published_to_kb: bool = False
    kb_article_id: UUID | None = None


class KnownErrorCreate(KnownErrorBase):
    pass


class KnownErrorUpdate(BaseModel):
    symptoms: str | None = Field(None, min_length=5, max_length=4000)
    root_cause_summary: str | None = Field(None, max_length=4000)
    workaround_id: UUID | None = None
    is_published_to_kb: bool | None = None
    kb_article_id: UUID | None = None


class KnownErrorResponse(KnownErrorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class KnownErrorListResponse(BaseModel):
    items: list[KnownErrorResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Problem <-> Incident
# ==========================================================


class ProblemIncidentLinkCreate(BaseModel):
    problem_id: UUID
    ticket_id: UUID
    note: str | None = Field(None, max_length=500)


class ProblemIncidentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    ticket_id: UUID
    linked_by: UserSummary
    linked_at: datetime


class ProblemIncidentLinkListResponse(BaseModel):
    items: list[ProblemIncidentLinkResponse]
    total: int


# ==========================================================
# Workaround
# ==========================================================


class WorkaroundBase(BaseModel):
    problem_id: UUID
    description: str = Field(..., min_length=5, max_length=4000)
    steps: str | None = Field(None, description="Ordered steps to apply the workaround")
    is_temporary: bool = True
    effectiveness: WorkaroundEffectiveness = WorkaroundEffectiveness.UNVERIFIED


class WorkaroundCreate(WorkaroundBase):
    pass


class WorkaroundUpdate(BaseModel):
    description: str | None = Field(None, min_length=5, max_length=4000)
    steps: str | None = None
    is_temporary: bool | None = None
    effectiveness: WorkaroundEffectiveness | None = None


class WorkaroundResponse(WorkaroundBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UserSummary
    created_at: datetime
    updated_at: datetime


class WorkaroundListResponse(BaseModel):
    items: list[WorkaroundResponse]
    total: int


# ==========================================================
# Permanent Fix
# ==========================================================


class PermanentFixBase(BaseModel):
    problem_id: UUID
    change_request_id: UUID | None = Field(
        None, description="Change Request that delivered the fix, if one was required"
    )
    description: str = Field(..., min_length=5, max_length=4000)


class PermanentFixCreate(PermanentFixBase):
    pass


class PermanentFixUpdate(BaseModel):
    description: str | None = Field(None, min_length=5, max_length=4000)
    change_request_id: UUID | None = None
    verified_by_id: UUID | None = None
    verified_at: datetime | None = None


class PermanentFixResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    change_request_id: UUID | None = None
    description: str
    implemented_at: datetime | None = None
    verified_by: UserSummary | None = None
    verified_at: datetime | None = None
    created_at: datetime
