"""
Comment schemas.

Pydantic models for ticket comments and internal notes.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base
# ==========================================================


class CommentBase(BaseModel):
    """Common fields for a ticket comment."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
    )


# ==========================================================
# Create
# ==========================================================


class CommentCreate(CommentBase):
    """
    Create a comment on a ticket.

    Set `is_internal` to True when creating an internal note.
    """

    is_internal: bool = False


# ==========================================================
# Update
# ==========================================================


class CommentUpdate(BaseModel):
    """Update an existing comment."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
    )


# ==========================================================
# Author Summary
# ==========================================================


class CommentAuthor(BaseModel):
    """Minimal author information."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str


# ==========================================================
# Response
# ==========================================================


class CommentResponse(BaseModel):
    """Comment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID

    author: CommentAuthor

    content: str
    is_internal: bool

    created_at: datetime
    updated_at: datetime


# ==========================================================
# List Response
# ==========================================================


class CommentListResponse(BaseModel):
    """List of comments belonging to a ticket."""

    data: list[CommentResponse]
    total: int