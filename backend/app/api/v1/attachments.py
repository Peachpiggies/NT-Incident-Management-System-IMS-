from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_any_role
from app.core.storage import get_download_url, upload_file_object
from app.db.models import Attachment, Ticket, User
from app.db.session import get_db
from app.domain import Role

router = APIRouter(tags=["Attachments"])


class AttachmentResponse(BaseModel):
    id: int
    ticket_id: int
    uploader_id: int
    file_name: str
    content_type: str
    size_bytes: int
    object_key: str
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


@router.get("/tickets/{ticket_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(
    ticket_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Attachment]:
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(select(Attachment).where(Attachment.ticket_id == ticket_id))
    return result.scalars().all()


@router.post("/tickets/{ticket_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    ticket_id: int,
    *,
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(require_any_role([Role.TIER1, Role.TIER2, Role.MANAGER, Role.CUSTOMER]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Attachment:
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(contents) > 10_000_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    object_key = f"ticket-{ticket.id}/{int(datetime.now(timezone.utc).timestamp())}-{file.filename}"
    object_path = upload_file_object(object_key, contents, file.content_type or "application/octet-stream")

    attachment = Attachment(
        ticket_id=ticket.id,
        uploader_id=current_user.id,
        file_name=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(contents),
        object_key=object_path,
        is_internal=current_user.role != Role.CUSTOMER,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    ticket_id: int,
    attachment_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Attachment:
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if current_user.role == Role.CUSTOMER and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    attachment = await db.get(Attachment, attachment_id)
    if not attachment or attachment.ticket_id != ticket.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    download_url = get_download_url(attachment.object_key)
    attachment.object_key = download_url
    return attachment
