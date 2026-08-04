from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.db.models import TicketCategory, User
from app.db.session import get_db

router = APIRouter(tags=["Categories"])


class CategoryResponse(BaseModel):
    id: UUID
    code: str
    name: str
    color: str | None
    icon: str | None
    sort_order: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class CategoryRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=100)
    sort_order: int = 0
    is_active: bool = True


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketCategory]:
    return (
        await db.scalars(
            select(TicketCategory)
            .where(
                TicketCategory.is_deleted.is_(False), TicketCategory.is_active.is_(True)
            )
            .order_by(TicketCategory.sort_order, TicketCategory.name)
        )
    ).all()


@router.post(
    "/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCategory:
    if await db.scalar(
        select(TicketCategory).where(TicketCategory.code == payload.code)
    ):
        raise HTTPException(status_code=409, detail="Category code already exists")
    category = TicketCategory(**payload.model_dump(), created_by=current_user.id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCategory:
    category = await db.get(TicketCategory, category_id)
    if not category or category.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in payload.model_dump().items():
        setattr(category, key, value)
    category.updated_by = current_user.id
    await db.commit()
    await db.refresh(category)
    return category
