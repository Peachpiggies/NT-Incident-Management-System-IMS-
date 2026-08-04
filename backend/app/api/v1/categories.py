from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_roles
from app.db.models import Category
from app.db.models import User
from app.db.session import get_db
from app.domain import Role

router = APIRouter(tags=["Categories"])


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool

    model_config = ConfigDict(
        from_attributes=True
    )


class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=3)
    description: str | None = None
    is_active: bool = True


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=3)
    description: str | None = None
    is_active: bool | None = None


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Category]:
    result = await db.execute(select(Category).where(Category.is_active == True).order_by(Category.name.asc()))
    return result.scalars().all()


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: CategoryCreateRequest,
    current_user: Annotated[User, Depends(require_roles(Role.MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Category:
    existing = await db.execute(select(Category).where(Category.name == request.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category already exists")

    category = Category(
        name=request.name,
        description=request.description,
        is_active=request.is_active,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Category:
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    request: CategoryUpdateRequest,
    current_user: Annotated[User, Depends(require_roles(Role.MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Category:
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if request.name is not None:
        category.name = request.name
    if request.description is not None:
        category.description = request.description
    if request.is_active is not None:
        category.is_active = request.is_active

    await db.commit()
    await db.refresh(category)
    return category
