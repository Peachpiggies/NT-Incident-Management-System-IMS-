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
    """
    Attachment response.

    Field names mirror the `TicketAttachment` ORM model exactly
    (`mime_type` / `file_size`, not `content_type` / `size`) so that
    `AttachmentResponse.model_validate(attachment)` — used with
    `from_attributes=True` in `app.api.v1.attachments` — can populate
    every field via plain attribute access. A previous version of this
    schema used `content_type`/`size`, which don't exist on the model
    and raised a `ValidationError` on every upload/list call.

    `download_url` is optional and unset by `model_validate`: only
    `get_attachment` fills it in afterwards (a presigned URL isn't
    stored on the model), so it must have a default.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID

    filename: str
    mime_type: str
    file_size: int
    is_internal: bool

    uploaded_by: UUID

    created_at: datetime

    download_url: str | None = None


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