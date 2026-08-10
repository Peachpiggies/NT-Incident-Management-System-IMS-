"""
Attachment schemas.

Pydantic models for ticket file attachments.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Constants
# ==========================================================

MAX_FILENAME_LENGTH = 255
MAX_CONTENT_TYPE_LENGTH = 100


# ==========================================================
# Base
# ==========================================================


class AttachmentBase(BaseModel):
    """Common attachment fields."""

    filename: str = Field(
        ...,
        min_length=1,
        max_length=MAX_FILENAME_LENGTH,
    )

    content_type: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CONTENT_TYPE_LENGTH,
    )

    size: int = Field(
        ...,
        ge=0,
    )


# ==========================================================
# Upload
# ==========================================================


class AttachmentUpload(BaseModel):
    """
    Attachment upload metadata.

    The actual file is handled by FastAPI UploadFile.
    This schema contains metadata only.
    """

    filename: str = Field(
        ...,
        min_length=1,
        max_length=MAX_FILENAME_LENGTH,
    )

    content_type: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CONTENT_TYPE_LENGTH,
    )


# ==========================================================
# Response
# ==========================================================


class AttachmentResponse(BaseModel):
    """Attachment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID

    filename: str
    content_type: str
    size: int

    uploaded_by: UUID

    created_at: datetime


# ==========================================================
# Attachment Summary
# ==========================================================


class AttachmentSummary(BaseModel):
    """Minimal attachment information."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str
    file_size: int
    is_internal: bool


# ==========================================================
# List Response
# ==========================================================


class AttachmentListResponse(BaseModel):
    """List of attachments belonging to a ticket."""

    data: list[AttachmentResponse]
    total: int