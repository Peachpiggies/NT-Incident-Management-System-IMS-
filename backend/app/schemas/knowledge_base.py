"""
Knowledge Base schemas.

Pydantic models for KB categories, articles, versioning, the
publishing workflow, and article <-> incident linking.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UserSummary


# ==========================================================
# Enums
# ==========================================================


class ArticleStatus(str, Enum):
    """Publishing workflow state of a KB article."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


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
    Updating any of title/summary/content/category_id/tags creates a new
    `KBArticleVersion` server-side; this schema only carries the new values,
    not the version bookkeeping itself.
    """

    title: str | None = Field(None, min_length=5, max_length=255)
    summary: str | None = Field(None, max_length=500)
    content: str | None = Field(None, min_length=10)
    category_id: UUID | None = None
    tags: list[str] | None = None
    change_summary: str | None = Field(
        None, max_length=500, description="Short note on what changed, stored on the new version"
    )


class KBArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    summary: str | None = None
    content: str
    category_id: UUID
    tags: list[str] = Field(default_factory=list)

    status: ArticleStatus
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
    status: ArticleStatus


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
    """Move a DRAFT article to IN_REVIEW."""

    note: str | None = Field(None, max_length=1000)


class KBArticleReviewDecision(BaseModel):
    """Reviewer approves (-> PUBLISHED) or sends back (-> DRAFT)."""

    approve: bool
    comment: str | None = Field(None, max_length=1000)


class KBArticleArchive(BaseModel):
    reason: str | None = Field(None, max_length=500)


class KBArticleStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ArticleStatus
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
