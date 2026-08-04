from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    user_has_permission,
)
from app.core.storage import get_download_url, upload_file_object
from app.db.models import Ticket, TicketAttachment, User
from app.db.session import get_db

router = APIRouter(tags=["Attachments"])
ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class AttachmentResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    filename: str
    mime_type: str
    file_size: int
    storage_path: str
    is_internal: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


async def _ticket(ticket_id: UUID, user: User, db: AsyncSession) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted:
        raise HTTPException(404, "Ticket not found")
    if ticket.requester_id != user.id and not await user_has_permission(
        db, user.id, "ticket.read_all"
    ):
        raise HTTPException(403, "Forbidden")
    return ticket


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
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    if len(content) > 10_000_000:
        raise HTTPException(413, "File too large")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported file type")
    path = upload_file_object(
        f"ticket-{ticket.id}/{int(datetime.now(timezone.utc).timestamp())}-{file.filename}",
        content,
        file.content_type,
    )
    attachment = TicketAttachment(
        ticket_id=ticket.id,
        filename=file.filename or "upload",
        storage_path=path,
        mime_type=file.content_type,
        file_size=len(content),
        uploaded_by=current_user.id,
    )
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
    await _ticket(ticket_id, current_user, db)
    attachment = await db.get(TicketAttachment, attachment_id)
    if not attachment or attachment.ticket_id != ticket_id or attachment.is_deleted:
        raise HTTPException(404, "Attachment not found")
    if attachment.is_internal and not await user_has_permission(
        db, current_user.id, "ticket.internal_note"
    ):
        raise HTTPException(403, "Forbidden")
    data = AttachmentResponse.model_validate(attachment)
    data.storage_path = get_download_url(attachment.storage_path)
    return data
