"""
Knowledge Base schemas.

Pydantic models for KB categories, articles, versioning, the
publishing workflow, and article <-> incident linking.

Publishing status is configurable master data (`KBArticleStatus` /
`KBArticleStatusTransition`, mirroring the ticket workflow tables), not a
Python enum, so administrators can adapt the workflow without a deployment.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UserSummary

# ==========================================================
# Status (configurable master data, not a Python enum)
# ==========================================================


class KBArticleStatusSummary(BaseModel):
    """Lightweight status reference for nested display, mirroring
    `StatusSummary` for tickets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    color: str | None = None


# ==========================================================
# Categories
# ==========================================================


class KBCategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    parent_id: UUID | None = None
    sort_order: int = 0
    is_active: bool = True


class KBCategoryCreate(KBCategoryBase):
    pass


class KBCategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=150)
    parent_id: UUID | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class KBCategoryResponse(KBCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class KBCategoryListResponse(BaseModel):
    items: list[KBCategoryResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Articles
# ==========================================================


class KBArticleBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    summary: str | None = Field(None, max_length=500)
    content: str = Field(..., min_length=10)
    category_id: UUID
    tags: list[str] = Field(default_factory=list)


class KBArticleCreate(KBArticleBase):
    pass


class KBArticleUpdate(BaseModel):
    """
    Plain edits (this schema) update the article in place and do NOT create a
    new `KBArticleVersion` -- versions are only snapshotted at
    submit-for-review and at publish time (see
    app/services/knowledge_base.py). There is therefore no `change_summary`
    field here; that field lives on the workflow-transition schemas below
    and is stored on the version snapshot they create.
    """

    title: str | None = Field(None, min_length=5, max_length=255)
    summary: str | None = Field(None, max_length=500)
    content: str | None = Field(None, min_length=10)
    category_id: UUID | None = None
    tags: list[str] | None = None


class KBArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    summary: str | None = None
    content: str
    category_id: UUID
    tags: list[str] = Field(default_factory=list)

    status: KBArticleStatusSummary
    current_version_no: int

    author: UserSummary
    view_count: int = 0

    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class KBArticleSummary(BaseModel):
    """Lightweight article reference, e.g. for search results or linking."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    summary: str | None = None
    status: KBArticleStatusSummary


class KBArticleListResponse(BaseModel):
    items: list[KBArticleSummary]
    total: int
    page: int
    page_size: int


# ==========================================================
# Versioning
# ==========================================================


class KBArticleVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID
    version_no: int
    title: str
    content: str
    change_summary: str | None = None
    changed_by: UserSummary
    created_at: datetime


class KBArticleVersionListResponse(BaseModel):
    items: list[KBArticleVersionResponse]
    total: int


# ==========================================================
# Publishing Workflow
# ==========================================================


class KBArticleSubmitForReview(BaseModel):
    """Move a DRAFT article to IN_REVIEW. Snapshots a version."""

    note: str | None = Field(None, max_length=1000)


class KBArticleReviewDecision(BaseModel):
    """Reviewer approves (-> PUBLISHED, snapshots a version) or sends back
    (-> DRAFT, no version snapshot)."""

    approve: bool
    comment: str | None = Field(None, max_length=1000)


class KBArticleArchive(BaseModel):
    reason: str | None = Field(None, max_length=500)


class KBArticleRestore(BaseModel):
    """Move an ARCHIVED article back to DRAFT."""

    reason: str | None = Field(None, max_length=500)


class KBArticleStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: KBArticleStatusSummary
    published_at: datetime | None = None


# ==========================================================
# Article <-> Incident
# ==========================================================


class KBArticleIncidentLinkCreate(BaseModel):
    article_id: UUID
    ticket_id: UUID
    note: str | None = Field(None, max_length=500)


class KBArticleIncidentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article: KBArticleSummary
    ticket_id: UUID
    linked_by: UserSummary
    linked_at: datetime


class KBArticleIncidentLinkListResponse(BaseModel):
    items: list[KBArticleIncidentLinkResponse]
    total: int
