"""
Attachment API endpoints.

Handles ticket attachment upload, listing, retrieval and deletion.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Annotated
from unicodedata import normalize
from uuid import UUID, uuid4
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    require_ticket_read,
    user_has_permission,
)
from app.core.config import settings
from app.core.storage import (
    delete_file,
    get_download_url,
    upload_file_object,
)
from app.core.virus_scan import (
    VirusDetectedError,
    VirusScannerUnavailableError,
    scan_bytes,
)
from app.db.models import Ticket, TicketAttachment, User
from app.db.session import get_db
from app.schemas.attachments import AttachmentResponse


router = APIRouter(tags=["Attachments"])


# ==========================================================
# File Validation
# ==========================================================


ALLOWED_TYPES: dict[str, set[str]] = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        ".docx"
    },
}

MAX_FILENAME_LENGTH = 128
MAX_DOCX_UNCOMPRESSED_BYTES = 50_000_000


# ==========================================================
# Helpers
# ==========================================================


async def _get_ticket(
    ticket_id: UUID,
    user: User,
    db: AsyncSession,
) -> Ticket:
    """Get a visible ticket and enforce ticket read permission."""

    ticket = await db.get(Ticket, ticket_id)

    if not ticket or ticket.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    await require_ticket_read(db, user, ticket)

    return ticket


def _sanitize_filename(
    filename: str | None,
    content_type: str,
) -> str:
    """Sanitize and validate the uploaded filename."""

    if not filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filename is required",
        )

    name = PurePath(filename.replace("\\", "/")).name
    name = normalize("NFKC", name)

    safe_name = "".join(
        character
        if character.isalnum() or character in {".", "-", "_"}
        else "_"
        for character in name
    ).strip("._")

    extension = PurePath(safe_name).suffix.lower()

    if not safe_name or extension not in ALLOWED_TYPES[content_type]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Filename extension does not match content type",
        )

    stem = PurePath(safe_name).stem[
        : MAX_FILENAME_LENGTH - len(extension)
    ]

    if not stem:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid filename",
        )

    return f"{stem}{extension}"


def _validate_file_signature(
    content: bytes,
    content_type: str,
) -> None:
    """Validate file bytes against the declared MIME type."""

    valid = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "application/pdf": content.startswith(b"%PDF-"),
    }

    if (
        content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())

                uncompressed_size = sum(
                    member.file_size
                    for member in archive.infolist()
                )

            valid[content_type] = (
                "[Content_Types].xml" in names
                and "word/document.xml" in names
                and uncompressed_size <= MAX_DOCX_UNCOMPRESSED_BYTES
            )

        except BadZipFile:
            valid[content_type] = False

    if not valid.get(content_type, False):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content does not match declared type",
        )


async def _cleanup_storage_file(path: str) -> None:
    """
    Remove an uploaded storage object after database failure.

    Storage implementation is responsible for handling the actual
    filesystem/object-storage deletion.
    """

    try:
        delete_file(path)
    except Exception:
        # Do not replace the original database error with a cleanup error.
        # Production logging can be added here later.
        return


# ==========================================================
# List
# ==========================================================


@router.get(
    "/tickets/{ticket_id}/attachments",
    response_model=list[AttachmentResponse],
)
async def list_attachments(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketAttachment]:
    """List attachments visible to the current user."""

    await _get_ticket(ticket_id, current_user, db)

    statement = (
        select(TicketAttachment)
        .where(
            TicketAttachment.ticket_id == ticket_id,
            TicketAttachment.is_deleted.is_(False),
        )
        .order_by(TicketAttachment.created_at.asc())
    )

    # Internal attachments are visible only to users with
    # the internal-note permission.
    if not await user_has_permission(
        db,
        current_user.id,
        "ticket.internal_note",
    ):
        statement = statement.where(
            TicketAttachment.is_internal.is_(False)
        )

    return (await db.scalars(statement)).all()


# ==========================================================
# Upload
# ==========================================================


@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    ticket_id: UUID,
    file: Annotated[UploadFile, File()],
    is_internal: Annotated[bool, Form()] = False,
    current_user: Annotated[
        User,
        Depends(require_permission("ticket.attachment_add")),
    ] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> TicketAttachment:
    """Upload an attachment to a ticket."""

    ticket = await _get_ticket(
        ticket_id,
        current_user,
        db,
    )

    # ------------------------------------------------------
    # MIME type
    # ------------------------------------------------------

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type",
        )

    # ------------------------------------------------------
    # Internal attachment permission
    # ------------------------------------------------------

    if is_internal and not await user_has_permission(
        db,
        current_user.id,
        "ticket.internal_note",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required for internal attachments",
        )

    # ------------------------------------------------------
    # Lock ticket row before checking attachment count
    # ------------------------------------------------------

    await db.execute(
        select(Ticket.id)
        .where(Ticket.id == ticket.id)
        .with_for_update()
    )

    attachment_count = await db.scalar(
        select(func.count())
        .select_from(TicketAttachment)
        .where(
            TicketAttachment.ticket_id == ticket.id,
            TicketAttachment.is_deleted.is_(False),
        )
    )

    if (attachment_count or 0) >= settings.max_attachments_per_ticket:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment limit reached",
        )

    # ------------------------------------------------------
    # Read with size limit
    # ------------------------------------------------------

    content = await file.read(
        settings.max_attachment_bytes + 1
    )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    if len(content) > settings.max_attachment_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    # ------------------------------------------------------
    # Validate file
    # ------------------------------------------------------

    _validate_file_signature(
        content,
        file.content_type,
    )

    filename = _sanitize_filename(
        file.filename,
        file.content_type,
    )

    # ------------------------------------------------------
    # Virus scan
    # ------------------------------------------------------

    try:
        await scan_bytes(
            content,
            host=settings.clamav_host,
            port=settings.clamav_port,
            timeout=settings.clamav_timeout,
        )

    except VirusDetectedError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Malicious file detected",
        )

    except VirusScannerUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File security scanner is unavailable",
        )

    # ------------------------------------------------------
    # Storage
    # ------------------------------------------------------

    storage_path: str | None = None

    try:
        storage_path = upload_file_object(
            f"ticket-{ticket.id}/{uuid4().hex}-{filename}",
            content,
            file.content_type,
        )

        # --------------------------------------------------
        # Database
        # --------------------------------------------------

        attachment = TicketAttachment(
            ticket_id=ticket.id,
            filename=filename,
            storage_path=storage_path,
            mime_type=file.content_type,
            file_size=len(content),
            uploaded_by=current_user.id,
            is_internal=is_internal,
        )

        db.add(attachment)

        await db.commit()
        await db.refresh(attachment)

        return attachment

    except Exception:
        await db.rollback()

        if storage_path:
            await _cleanup_storage_file(storage_path)

        raise


# ==========================================================
# Get Attachment
# ==========================================================


@router.get(
    "/tickets/{ticket_id}/attachments/{attachment_id}",
    response_model=AttachmentResponse,
)
async def get_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttachmentResponse:
    """Get attachment metadata and a download URL."""

    await _get_ticket(
        ticket_id,
        current_user,
        db,
    )

    attachment = await db.get(
        TicketAttachment,
        attachment_id,
    )

    if (
        not attachment
        or attachment.ticket_id != ticket_id
        or attachment.is_deleted
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    if attachment.is_internal and not await user_has_permission(
        db,
        current_user.id,
        "ticket.internal_note",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    data = AttachmentResponse.model_validate(attachment)

    data.download_url = get_download_url(
        attachment.storage_path
    )

    return data


# ==========================================================
# Delete
# ==========================================================


@router.delete(
    "/tickets/{ticket_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_permission("ticket.attachment_delete")),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft-delete a ticket attachment."""

    await _get_ticket(
        ticket_id,
        current_user,
        db,
    )

    attachment = await db.get(
        TicketAttachment,
        attachment_id,
    )

    if (
        not attachment
        or attachment.ticket_id != ticket_id
        or attachment.is_deleted
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    if attachment.is_internal and not await user_has_permission(
        db,
        current_user.id,
        "ticket.internal_note",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    attachment.is_deleted = True

    await db.commit()