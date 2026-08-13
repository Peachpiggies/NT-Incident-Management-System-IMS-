"""
Comment schemas.

Pydantic models for ticket comments and internal notes.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Enums
# ==========================================================


class CommentUpdateType(str, Enum):
    """Distinguishes a general internal note from an investigation /
    technical-update entry (TicketComment.update_type). Technical updates are
    what the T2/T3 investigation timeline filters on.
    """

    NOTE = "NOTE"
    TECHNICAL_UPDATE = "TECHNICAL_UPDATE"


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

    Set `is_internal` to True when creating an internal note. Set
    `update_type` to TECHNICAL_UPDATE for investigation/diagnosis progress
    entries that should surface on the T2/T3 investigation timeline; defaults
    to a general NOTE otherwise.
    """

    is_internal: bool = False

    update_type: CommentUpdateType = CommentUpdateType.NOTE


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

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    ticket_id: UUID

    author: CommentAuthor

    # ORM column is `TicketComment.comment`, not `content` -- alias bridges
    # the naming difference so `from_attributes` reads the right attribute
    # while the API still exposes `content`.
    content: str = Field(validation_alias="comment", serialization_alias="content")
    is_internal: bool
    update_type: CommentUpdateType = CommentUpdateType.NOTE

    created_at: datetime
    updated_at: datetime


# ==========================================================
# List Response
# ==========================================================


class CommentListResponse(BaseModel):
    """List of comments belonging to a ticket."""

    data: list[CommentResponse]
    total: int