from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePath
from typing import Annotated
from unicodedata import normalize
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    require_ticket_read,
    user_has_permission,
)
from app.core.config import settings
from app.core.storage import delete_file_object, get_download_url, upload_file_object
from app.db.models import Ticket, TicketAttachment, User
from app.db.session import get_db
from app.services.virus_scan import submit_attachment_for_scan

router = APIRouter(tags=["Attachments"])
ALLOWED_TYPES = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        ".docx"
    },

    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},

}
MAX_FILENAME_LENGTH = 128
MAX_DOCX_UNCOMPRESSED_BYTES = 50_000_000
PREVIEWABLE_TYPES = {"image/jpeg", "image/png", "application/pdf"}
SCAN_STATUSES = {"PENDING", "CLEAN", "INFECTED", "FAILED"}


class AttachmentResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    filename: str
    mime_type: str
    file_size: int
    storage_path: str
    is_internal: bool
    scan_status: str
    scanned_at: datetime | None
    scan_detail: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ScanResultRequest(BaseModel):
    status: str
    detail: str | None = None


async def _ticket(ticket_id: UUID, user: User, db: AsyncSession) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted:
        raise HTTPException(404, "Ticket not found")
    await require_ticket_read(db, user, ticket)
    return ticket


async def _attachment_for_ticket(
    ticket_id: UUID, attachment_id: UUID, user: User, db: AsyncSession
) -> TicketAttachment:
    await _ticket(ticket_id, user, db)
    attachment = await db.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.ticket_id != ticket_id or attachment.is_deleted:
        raise HTTPException(404, "Attachment not found")
    if attachment.is_internal and not await user_has_permission(
        db, user.id, "ticket.internal_note"
    ):
        raise HTTPException(403, "Forbidden")
    return attachment


def _sanitize_filename(filename: str | None, content_type: str) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filename is required",
        )
    name = PurePath(filename.replace("\\", "/")).name
    name = normalize("NFKC", name)
    safe_name = "".join(
        character if character.isalnum() or character in {".", "-", "_"} else "_"
        for character in name
    ).strip("._")
    extension = PurePath(safe_name).suffix.lower()
    if not safe_name or extension not in ALLOWED_TYPES[content_type]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Filename extension does not match content type",
        )
    stem = PurePath(safe_name).stem[: MAX_FILENAME_LENGTH - len(extension)]
    if not stem:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid filename"
        )
    return f"{stem}{extension}"


def _validate_file_signature(content: bytes, content_type: str) -> None:
    valid = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "application/pdf": content.startswith(b"%PDF-"),
    }
    if content_type in{

        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

    }:
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
                uncompressed_size = sum(
                    member.file_size for member in archive.infolist()
                )

            required_document = (

                "word/document.xml"
                if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                else "xl/workbook.xml"

            )

            valid[content_type] = (
                "[Content_Types].xml" in names
                and required_document in names
                and uncompressed_size <= MAX_DOCX_UNCOMPRESSED_BYTES
            )
        except BadZipFile:
            valid[content_type] = False
    if not valid.get(content_type, False):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content does not match declared type",
        )


@router.get("/tickets/{ticket_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketAttachment]:
    await _ticket(ticket_id, current_user, db)
    statement = select(TicketAttachment).where(
        TicketAttachment.ticket_id == ticket_id,
        TicketAttachment.is_deleted.is_(False),
    )
    if not await user_has_permission(db, current_user.id, "ticket.internal_note"):
        statement = statement.where(TicketAttachment.is_internal.is_(False))
    return (await db.scalars(statement)).all()


@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    ticket_id: UUID,
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(require_permission("ticket.attachment_add"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketAttachment:
    ticket = await _ticket(ticket_id, current_user, db)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type",
        )
    await db.execute(select(Ticket.id).where(Ticket.id == ticket.id).with_for_update())
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
            status_code=status.HTTP_409_CONFLICT, detail="Attachment limit reached"
        )
    content = await file.read(settings.max_attachment_bytes + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file"
        )
    if len(content) > settings.max_attachment_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )
    _validate_file_signature(content, file.content_type)
    filename = _sanitize_filename(file.filename, file.content_type)
    path = upload_file_object(
        f"ticket-{ticket.id}/{uuid4().hex}-{filename}",
        content,
        file.content_type,
    )
    attachment = TicketAttachment(
        ticket_id=ticket.id,
        filename=filename,
        storage_path=path,
        mime_type=file.content_type,
        file_size=len(content),
        uploaded_by=current_user.id,
    )
    submission = await submit_attachment_for_scan(attachment)
    attachment.scan_status = submission.status
    attachment.scan_detail = submission.detail
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


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
    attachment = await _attachment_for_ticket(
        ticket_id, attachment_id, current_user, db
    )
    data = AttachmentResponse.model_validate(attachment)
    data.storage_path = get_download_url(attachment.storage_path)
    return data


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}/preview")
async def preview_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    attachment = await _attachment_for_ticket(
        ticket_id, attachment_id, current_user, db
    )
    if attachment.mime_type not in PREVIEWABLE_TYPES:
        raise HTTPException(status_code=415, detail="Preview is not supported for this file type")
    if attachment.scan_status != "CLEAN":
        raise HTTPException(
            status_code=423,
            detail="Attachment is quarantined pending a clean virus scan",
        )
    if settings.aws_s3_bucket:
        return RedirectResponse(get_download_url(attachment.storage_path))
    return FileResponse(
        attachment.storage_path,
        media_type=attachment.mime_type,
        content_disposition_type="inline",
    )


@router.delete(
    "/tickets/{ticket_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    attachment = await _attachment_for_ticket(
        ticket_id, attachment_id, current_user, db
    )
    can_manage = await user_has_permission(
        db, current_user.id, "ticket.attachment_manage"
    )
    if attachment.uploaded_by != current_user.id and not can_manage:
        raise HTTPException(status_code=403, detail="Forbidden")
    attachment.is_deleted = True
    attachment.deleted_at = datetime.now(timezone.utc)
    attachment.deleted_by = current_user.id
    attachment.updated_by = current_user.id
    await db.commit()
    try:
        delete_file_object(attachment.storage_path)
    except RuntimeError:
        pass


@router.post(
    "/attachments/{attachment_id}/scan-result", response_model=AttachmentResponse
)
async def record_scan_result(
    attachment_id: UUID,
    payload: ScanResultRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketAttachment:
    scan_status = payload.status.upper()
    if scan_status not in SCAN_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid scan status")
    attachment = await db.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.is_deleted:
        raise HTTPException(status_code=404, detail="Attachment not found")
    attachment.scan_status = scan_status
    attachment.scan_detail = payload.detail
    attachment.scanned_at = datetime.now(timezone.utc)
    attachment.updated_by = current_user.id
    await db.commit()
    await db.refresh(attachment)
    return attachment
